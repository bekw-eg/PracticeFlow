# node:22-alpine (Alpine 3.24)
FROM node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# nginxinc/nginx-unprivileged:1.30.4-alpine3.24
FROM nginxinc/nginx-unprivileged@sha256:929e1d5e610e8aa89a1715ba44dce5edb4d42c172a208c171233292f472560c5

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# nginxinc/nginx-unprivileged runs as uid 101; make this invariant explicit.
USER 101

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]
