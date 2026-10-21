# Test runner only; Python base matches backend/Dockerfile.
FROM python@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4
RUN apk upgrade --no-cache && apk add --no-cache docker-cli docker-cli-compose restic
COPY deployment/backup/requirements.txt /tmp/backup-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backup-requirements.txt
RUN apk add --no-cache docker-cli-buildx
WORKDIR /workspace
CMD ["python", "scripts/verify-production-backup.py"]
