# node:22-alpine (Alpine 3.24)
FROM node@sha256:e961046fec20896e8904f2b4a8b4c7e5ca91826d84d8d33d83dbaa61f942069e AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# nginxinc/nginx-unprivileged:1.30.4-alpine3.24
FROM nginxinc/nginx-unprivileged@sha256:5961e0cdaabc43fea28b3bc9228c1ee7e6bd2c47bd93d79e2a2399bb67fc924a

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# nginxinc/nginx-unprivileged runs as uid 101; make this invariant explicit.
USER 101

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]
