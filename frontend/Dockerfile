FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_URL=/api
ARG VITE_TENANT_TOKEN=
ARG VITE_PUBLIC_API_KEY=
ARG VITE_PUBLIC_CLIENT_ID=

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_TENANT_TOKEN=$VITE_TENANT_TOKEN
ENV VITE_PUBLIC_API_KEY=$VITE_PUBLIC_API_KEY
ENV VITE_PUBLIC_CLIENT_ID=$VITE_PUBLIC_CLIENT_ID

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/30-write-config.sh /docker-entrypoint.d/30-write-config.sh
# Strip any CRLF the host may have introduced (git autocrlf on Windows) so the
# `#!/bin/sh` shebang resolves — a trailing `\r` makes the kernel look for `/bin/sh\r` (exit 127).
RUN sed -i 's/\r$//' /docker-entrypoint.d/30-write-config.sh && chmod +x /docker-entrypoint.d/30-write-config.sh
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
