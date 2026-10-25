FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock requirements-build.lock ./
RUN python -m pip install --no-cache-dir -r requirements-build.lock -r requirements.lock
COPY pyproject.toml LICENSE NOTICE THIRD_PARTY.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation . \
    && groupadd --gid 10001 garmin-sync \
    && useradd --uid 10001 --gid 10001 --no-create-home garmin-sync \
    && mkdir /data /music /scratch && chown 10001:10001 /data /scratch
USER 10001:10001
ENV GARMIN_SYNC_DATA=/data GARMIN_SYNC_MUSIC=/music GARMIN_SYNC_BIND=0.0.0.0 TMPDIR=/scratch
CMD ["python", "-m", "garmin_sync.cli", "serve-admin"]
