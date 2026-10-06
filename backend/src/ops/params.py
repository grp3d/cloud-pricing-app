"""Read SSM parameters (018-app-cloud-deployment, FR-024, FR-037, FR-041).

One small wrapper so tests can stub every secret read in one place. Values are never logged.
"""

from __future__ import annotations


def get_parameter(name: str) -> str:
    """The decrypted value of an SSM parameter (SecureString or String)."""
    import boto3

    response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]
