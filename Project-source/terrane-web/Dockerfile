# 多阶段:node 构建静态 → nginx 托管(SPA + 反代后端)。纯静态,无 GPU。
FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY . .
RUN npm run build
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=4s CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
