# Test-only replacement for discontinued upstream registry images.
# golang:1.26-alpine (manifest resolved 2026-10-05)
FROM golang@sha256:8ac98ca534ac3f51e1f420a1dd2c15e74c75cfa0f23f3ad27eb5d7236c349a0c AS build

ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOSUMDB=sum.golang.org GODEBUG=http2client=0
# Use HTTP/1.1 for Go downloads to avoid transient HTTP/2 sumdb stream errors.
# Retry each install up to five times, retaining the verified module/build cache.
# MinIO RELEASE.2025-10-15T17-29-55Z includes the session-policy bypass fix.
RUN set -eu; \
    retry() { \
        attempt=1; \
        while :; do \
            if "$@"; then return 0; else status=$?; fi; \
            if [ "$attempt" -ge 5 ]; then return "$status"; fi; \
            echo "Go command failed (attempt $attempt/5); retrying in $((attempt * 5))s" >&2; \
            sleep "$((attempt * 5))"; \
            attempt=$((attempt + 1)); \
        done; \
    }; \
    retry go install -trimpath -ldflags="-s -w" github.com/minio/minio@9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a; \
    retry go install -trimpath -ldflags="-s -w" github.com/minio/mc@7394ce0dd2a80935aded936b09fa12cbb3cb8096; \
    mkdir /licenses; \
    minio_dir="$(retry go list -m -f '{{.Dir}}' github.com/minio/minio@9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a)"; \
    mc_dir="$(retry go list -m -f '{{.Dir}}' github.com/minio/mc@7394ce0dd2a80935aded936b09fa12cbb3cb8096)"; \
    cp "$minio_dir/LICENSE" /licenses/MinIO-LICENSE; \
    cp "$mc_dir/LICENSE" /licenses/mc-LICENSE

# alpine:3.24 (manifest resolved 2026-10-05)
FROM alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN apk add --no-cache ca-certificates curl \
    && addgroup -g 10001 minio \
    && adduser -D -u 10001 -G minio minio \
    && mkdir /data \
    && chown minio:minio /data
COPY --from=build /go/bin/minio /go/bin/mc /usr/local/bin/
COPY --from=build /licenses/ /usr/share/licenses/minio/
USER 10001:10001
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
