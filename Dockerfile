# Sketchmaker: one process on one port, as an unprivileged user, on a read-only image.
# Use docker-compose.yml, which adds the rest of the sandbox. No secret is ever in the
# image: the entrypoint creates them in the /config volume on first start.
#
# Base images are pinned by digest, so a rebuild cannot silently pull something else.
# To update one, look up the new tag's digest and change it here. uv is at least 0.13.4,
# because older versions bundle compromised eMudhra roots (GHSA-hq85-5cpj-mr62).

FROM node:22.23.4-trixie-slim@sha256:2117f713a417f3aff682ac8f5bc2ebbdf1beed51f36e67ab1e0fd3866b6d2d8f AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# --ignore-scripts: no dependency gets to run code at install time.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.12.16-slim-trixie@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS backend
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12.16-slim-trixie@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
# ffmpeg for video tools and renders. Everything else ships in the wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 sketchmaker \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin sketchmaker \
    && install -d -o sketchmaker -g sketchmaker -m 0700 /data /config \
    && { find / -xdev -type f -perm /6000 -exec chmod a-s {} + || true; }

COPY --from=backend /app/backend/.venv /app/backend/.venv
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic
COPY backend/app /app/backend/app
COPY --from=frontend /app/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
# Owned by root and only readable by the app, so it cannot change its own code.
RUN /app/backend/.venv/bin/python -m compileall -q /app/backend/app /app/backend/alembic \
    && chown -R root:root /app && chmod -R a+rX,go-w /app && chmod 0555 /app/docker/entrypoint.sh

# HOST and DATA_DIR come from here because /config/.env holds only the secrets, and the
# file would win. SKETCHMAKER_CONTAINER quiets the warning about listening on every
# address: that is the container's own network, and compose publishes it on 127.0.0.1.
ENV PATH=/app/backend/.venv/bin:$PATH \
    PYTHONPATH=/app/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    SKETCHMAKER_ENV_FILE=/config/.env \
    SKETCHMAKER_CONTAINER=1 \
    DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000

USER 10001:10001
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
ENTRYPOINT ["/app/docker/entrypoint.sh"]
