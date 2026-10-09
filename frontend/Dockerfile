# Estima3D web app: the production Vite build served by nginx, which proxies
# /api and /upload to the backend service (nginx.conf). docker-compose.yml
# passes the same SOURCE_REVISION / BUILD_ID as to the backend image.
FROM node:24.15.0-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The build embeds them for the frontend/backend pairing check (devIdentity.js).
# No credentials here: the access key is entered in the browser at runtime.
ARG SOURCE_REVISION=unknown
ARG BUILD_ID=unknown
ENV SOURCE_REVISION=${SOURCE_REVISION} \
    BUILD_ID=${BUILD_ID}
RUN npm run build \
    && printf '{"revision":"%s","build_id":"%s"}\n' "$SOURCE_REVISION" "$BUILD_ID" > dist/version.json

FROM nginx:1.27-alpine
ARG SOURCE_REVISION=unknown
ARG BUILD_ID=unknown
LABEL org.opencontainers.image.title="estima3d-web" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${BUILD_ID}"
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
