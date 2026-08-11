# Ubuntu + Docker + Nginx 部署方案

## 概述

本文档介绍如何在Ubuntu服务器上使用Docker和Nginx部署智能语音测试系统的前后端服务。

## 服务器环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04 LTS |
| CPU | 4核及以上 |
| 内存 | 8GB及以上 |
| 磁盘 | 50GB SSD |
| Docker | 24.0+ |
| Docker Compose | 2.0+ |

## 目录结构

```
/opt/intelligent-audio-test/
├── backend/
│   ├── app.py
│   ├── config/
│   ├── blueprints/
│   ├── models/
│   ├── utils/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── dist/
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── .env
```

---

## 第一步：服务器初始化

### 1.1 更新系统

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### 1.2 安装Docker

```bash
# 安装依赖
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# 添加Docker官方GPG密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 添加Docker仓库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动Docker
sudo systemctl start docker
sudo systemctl enable docker

# 添加当前用户到docker组
sudo usermod -aG docker $USER
```

### 1.3 安装Nginx

```bash
sudo apt-get install -y nginx
sudo systemctl enable nginx
```

---

## 第二步：准备项目文件

### 2.1 上传项目代码

```bash
cd /opt
git clone <项目仓库地址> intelligent-audio-test
cd intelligent-audio-test
```

### 2.2 创建必要目录

```bash
mkdir -p backend/logs backend/static
mkdir -p frontend/dist
```

---

## 第三步：创建配置文件

### 3.1 环境变量文件 .env

在项目根目录创建 `.env` 文件：

```env
# Flask配置
FLASK_ENV=production
FLASK_CONFIG=production
SECRET_KEY=your-secure-secret-key-here

# 数据库配置
DATABASE_URL=PostgreSql:///data.db

# 服务端口
BACKEND_PORT=5000
FRONTEND_PORT=80
```

### 3.2 前端 Dockerfile

创建 `frontend/Dockerfile`：

```dockerfile
FROM node:18-slim AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 3.3 前端 Nginx 配置

创建 `frontend/nginx.conf`：

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_min_length 1000;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://host.docker.internal:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /socket.io/ {
        proxy_pass http://host.docker.internal:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 3.4 后端 Dockerfile

创建 `backend/Dockerfile`：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "run.py"]
```

### 3.5 Docker Compose 配置

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: ia-backend
    ports:
      - "5000:5000"
    volumes:
      - ./backend/data.db:/app/data.db
      - ./backend/logs:/app/logs
      - ./backend/static:/app/static
    env_file:
      - .env
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
    networks:
      - ia-network

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: ia-frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - ia-network

networks:
  ia-network:
    driver: bridge
```

---

## 第四步：部署执行

### 4.1 构建镜像

```bash
cd /opt/intelligent-audio-test
docker-compose build
```

### 4.2 启动服务

```bash
docker-compose up -d
```

### 4.3 查看服务状态

```bash
docker-compose ps
docker-compose logs -f
```

### 4.4 验证服务

```bash
# 检查后端健康状态
curl http://localhost:5000/health

# 检查前端
curl http://localhost:80
```

---

## 第五步：Nginx反向代理（可选）

如果需要通过域名访问或配置SSL，使用独立Nginx作为反向代理。

### 5.1 创建Nginx配置文件

```bash
sudo nano /etc/nginx/sites-available/intelligent-audio-test
```

添加以下内容：

```nginx
upstream backend {
    server 127.0.0.1:5000;
}

upstream frontend {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name your-domain.com;

    access_log /var/log/nginx/ia-access.log;
    error_log /var/log/nginx/ia-error.log;

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 5.2 启用配置

```bash
sudo ln -s /etc/nginx/sites-available/intelligent-audio-test /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5.3 修改Docker Compose

将前端端口映射到8080：

```yaml
frontend:
  ports:
    - "8080:80"
```

---

## 第六步：SSL配置（可选）

使用Let's Encrypt免费SSL证书：

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

---

## 运维管理

### 常用命令

```bash
# 查看日志
docker-compose logs -f backend
docker-compose logs -f frontend

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新代码后重新部署
docker-compose up -d --build

# 查看资源使用
docker stats
```

### 开机自启

创建systemd服务文件 `/etc/systemd/system/intelligent-audio-test.service`：

```ini
[Unit]
Description=Intelligent Audio Test System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/intelligent-audio-test
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable intelligent-audio-test
```

---

## 故障排查

### 常见问题

| 问题 | 解决方法 |
|------|----------|
| 容器启动失败 | `docker-compose logs` 查看日志 |
| 前端无法访问后端API | 检查网络配置和API地址 |
| 静态资源加载失败 | 检查Nginx配置和文件路径 |
| 数据库连接失败 | 检查数据卷挂载和文件权限 |

### 日志位置

- Docker容器日志：`docker-compose logs`
- Nginx访问日志：`/var/log/nginx/ia-access.log`
- Nginx错误日志：`/var/log/nginx/ia-error.log`

---

## 更新升级

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建镜像
docker-compose build

# 3. 重启服务
docker-compose up -d

# 4. 检查状态
docker-compose ps
```
