# Backend image (018-app-cloud-deployment, FR-018, FR-053; research.md R5, R9).
# Runs the API (default command) and the ops CLI (`python -m src.ops …`). Every base image is
# pinned by digest; upgrade them as described in docs/deployment.md ("Pinned versions").

FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

# PostgreSQL Global Development Group signing key; the build fails if the downloaded key's
# fingerprint differs. pg_dump must be at least the server's major version (18), which Debian
# bookworm doesn't ship.
ARG PGDG_FINGERPRINT=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/pgdg.asc; \
    fingerprint="$(gpg --show-keys --with-colons /tmp/pgdg.asc | awk -F: '/^fpr:/ {print $10; exit}')"; \
    test "$fingerprint" = "$PGDG_FINGERPRINT" || { echo "PGDG key fingerprint mismatch: $fingerprint" >&2; exit 1; }; \
    gpg --dearmor -o /usr/share/keyrings/pgdg.gpg /tmp/pgdg.asc; \
    echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/* /tmp/pgdg.asc /root/.gnupg

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY alembic.ini ./
COPY src ./src

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /run/app /var/lib/app/pricing-cache /tls \
    && chown -R app:app /run/app /var/lib/app /tls
USER app

ARG GIT_SHA=unknown
ARG RELEASE=dev
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.version=$RELEASE
ENV APP_RELEASE=$RELEASE

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
