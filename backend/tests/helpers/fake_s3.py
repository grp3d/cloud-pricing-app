"""An in-memory stand-in for the boto3 S3 client (018-app-cloud-deployment, T010).

Implements only the calls the app makes, with botocore's real error shapes, so the storage,
cache and backup code is tested with no network. `deny_missing=True` mimics the pipeline's
read-only policy, under which S3 reports a missing key as `AccessDenied` (FR-008).
"""

from __future__ import annotations

import base64
import hashlib
import io
from collections.abc import Callable

from botocore.exceptions import ClientError


def _error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class FakeS3Client:
    def __init__(self, *, deny_missing: bool = False) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.deny_missing = deny_missing
        self.calls: list[tuple[str, str]] = []
        # Hooks tests can set to inject failures: called with (operation, key) before each call.
        self.before_call: Callable[[str, str], None] | None = None

    # --- test setup ---------------------------------------------------------------------------

    def put(self, bucket: str, key: str, body: bytes) -> None:
        self.objects[(bucket, key)] = body

    def keys(self, bucket: str) -> list[str]:
        return sorted(k for b, k in self.objects if b == bucket)

    # --- client API ---------------------------------------------------------------------------

    def _enter(self, operation: str, key: str) -> None:
        self.calls.append((operation, key))
        if self.before_call is not None:
            self.before_call(operation, key)

    def _missing(self, operation: str) -> ClientError:
        if self.deny_missing:
            return _error("AccessDenied", 403, operation)
        if operation in ("HeadObject",):
            return _error("404", 404, operation)
        return _error("NoSuchKey", 404, operation)

    def get_object(self, *, Bucket: str, Key: str, **_: object) -> dict:  # noqa: N803
        self._enter("GetObject", Key)
        if (Bucket, Key) not in self.objects:
            raise self._missing("GetObject")
        body = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}

    def head_object(self, *, Bucket: str, Key: str, **_: object) -> dict:  # noqa: N803
        self._enter("HeadObject", Key)
        if (Bucket, Key) not in self.objects:
            raise self._missing("HeadObject")
        body = self.objects[(Bucket, Key)]
        return {
            "ContentLength": len(body),
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        }

    def put_object(  # noqa: N803
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        Body: bytes | io.IOBase,  # noqa: N803
        IfNoneMatch: str | None = None,  # noqa: N803
        **_: object,
    ) -> dict:
        self._enter("PutObject", Key)
        if IfNoneMatch == "*" and (Bucket, Key) in self.objects:
            raise _error("PreconditionFailed", 412, "PutObject")
        data = Body if isinstance(Body, bytes) else Body.read()
        self.objects[(Bucket, Key)] = data
        return {"ChecksumSHA256": base64.b64encode(hashlib.sha256(data).digest()).decode()}

    def delete_object(self, *, Bucket: str, Key: str, **_: object) -> dict:  # noqa: N803
        self._enter("DeleteObject", Key)
        self.objects.pop((Bucket, Key), None)
        return {}

    def download_fileobj(self, Bucket: str, Key: str, Fileobj: io.IOBase, **_: object) -> None:  # noqa: N803
        self._enter("DownloadFileobj", Key)
        if (Bucket, Key) not in self.objects:
            raise self._missing("HeadObject")
        Fileobj.write(self.objects[(Bucket, Key)])

    def list_objects_v2(  # noqa: N803
        self,
        *,
        Bucket: str,  # noqa: N803
        Prefix: str = "",  # noqa: N803
        Delimiter: str | None = None,  # noqa: N803
        ContinuationToken: str | None = None,  # noqa: N803
        **_: object,
    ) -> dict:
        self._enter("ListObjectsV2", Prefix)
        keys = [k for b, k in sorted(self.objects) if b == Bucket and k.startswith(Prefix)]
        if Delimiter is None:
            return {
                "Contents": [{"Key": k, "Size": len(self.objects[(Bucket, k)])} for k in keys],
                "IsTruncated": False,
            }
        prefixes = sorted(
            {Prefix + k[len(Prefix):].split(Delimiter)[0] + Delimiter
             for k in keys if Delimiter in k[len(Prefix):]}
        )
        contents = [
            {"Key": k, "Size": len(self.objects[(Bucket, k)])}
            for k in keys if Delimiter not in k[len(Prefix):]
        ]
        return {
            "CommonPrefixes": [{"Prefix": p} for p in prefixes],
            "Contents": contents,
            "IsTruncated": False,
        }
