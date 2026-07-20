# AI Quant Trade — Frontend Dockerfile
# M5 + N6 修复：output:'export' 静态导出 + nginx 提供静态文件
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

COPY . .

# 构建时注入 API URL（M5: 环境变量外部注入）
ARG NEXT_PUBLIC_API_URL=http://localhost
ARG NEXT_PUBLIC_WS_URL=ws://localhost/ws/ticker
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

# 生成静态导出 → out/ 目录（需要 next.config.js 的 output:'export'）
RUN npm run build

# 运行阶段：nginx 提供静态文件
FROM nginx:alpine

# 复制静态导出文件到 nginx html 目录
COPY --from=builder /app/out /usr/share/nginx/html

# 简单的 nginx 配置（SPA fallback for client-side routing）
RUN echo 'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    location / { try_files $uri $uri/ /index.html; }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
