FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_URL=/api
ARG VITE_PUBLIC_API_KEY=
ARG VITE_PUBLIC_CLIENT_ID=

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_PUBLIC_API_KEY=$VITE_PUBLIC_API_KEY
ENV VITE_PUBLIC_CLIENT_ID=$VITE_PUBLIC_CLIENT_ID

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
