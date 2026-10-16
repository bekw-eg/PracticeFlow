# node:22-alpine (Alpine 3.24)
FROM node@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# nginxinc/nginx-unprivileged:1.30.4-alpine3.24 — reviewed Nginx binary/config.
FROM nginxinc/nginx-unprivileged@sha256:ce1317316e272062981736063d4a7eed7d80b0d2a53da1305d0752aa4aee7a48 AS nginx

# alpine:3.24 (manifest resolved 2026-10-05)
# A fresh runtime installs fixed libraries without carrying stale APK packages
# from the otherwise current upstream Nginx image.
FROM alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates pcre2 zlib libssl3 libcrypto3 \
    && addgroup -g 101 nginx && adduser -D -u 101 -G nginx nginx \
    && mkdir -p /var/cache/nginx /var/log/nginx /usr/share/nginx/html \
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && chown -R nginx:nginx /var/cache/nginx /usr/share/nginx/html
COPY --from=nginx /usr/sbin/nginx /usr/sbin/nginx
COPY --from=nginx /etc/nginx/ /etc/nginx/
RUN nginx -V

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Keep the reviewed unprivileged Nginx configuration and uid 101.
USER 101

EXPOSE 8080
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]
CMD ["nginx", "-g", "daemon off;"]
