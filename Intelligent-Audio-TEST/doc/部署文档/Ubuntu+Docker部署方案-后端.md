# Ubuntu + Docker 部署方案（后端）

## 概述

本文档介绍如何在Ubuntu服务器上使用Docker部署智能语音测试系统后端服务。

## 服务器环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04 LTS |
| CPU | 4核及以上 |
| 内存 | 8GB及以上 |
| 磁盘 | 50GB SSD |
| Python | 3.12 |
| Docker | 24.0+ |

---

## 第一步：服务器初始化

### 1.1 更新系统

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### 1.2 安装Python和依赖

```bash
sudo apt-get install -y python3.12 python3.12-venv python3-pip
sudo apt-get install -y ffmpeg sqlite3
```

### 1.3 安装Docker

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
mkdir -p backend/logs backend/static backend/data
```

---

## 第三步：创建配置文件

### 3.1 环境变量文件

在 `backend/` 目录下创建 `.env` 文件：

```env
# Flask配置
FLASK_ENV=production
FLASK_CONFIG=production
SECRET_KEY=your-secure-secret-key-change-this-in-production

# 数据库配置
DATABASE_URL=sqlite:///data.db
SQLALCHEMY_DATABASE_URI=sqlite:///data.db

# 日志配置
LOG_LEVEL=INFO

# FFmpeg配置
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe

# 执行引擎配置
EXECUTION_ENGINE_SCHEDULER_INTERVAL=3
EXECUTION_ENGINE_MAX_QUEUE_SIZE=100
```

### 3.2 后端 Dockerfile

创建 `backend/Dockerfile`：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "run.py"]
```

### 3.3 检查 requirements.txt

确保 `backend/requirements.txt` 存在且包含所有依赖：

```bash
# 如果不存在，创建requirements.txt
cd backend
pip freeze > requirements.txt
```

---

## 第四步：构建并运行

### 4.1 构建Docker镜像

```bash
cd /opt/intelligent-audio-test/backend
docker build -t ia-backend .
```

### 4.2 运行容器

```bash
docker run -d \
  --name ia-backend \
  -p 5000:5000 \
  -v $(pwd)/data.db:/app/data.db \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/static:/app/static \
  --restart unless-stopped \
  ia-backend
```

### 4.3 查看日志

```bash
docker logs -f ia-backend
```

### 4.4 验证服务

```bash
curl http://localhost:5000/health
```

预期响应：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ok"
  }
}
```

---

## 第五步：Docker Compose 方式（推荐）

### 5.1 创建 docker-compose.yml

在 `backend/` 目录下创建：

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ia-backend
    ports:
      - "5000:5000"
    volumes:
      - ./data.db:/app/data.db
      - ./logs:/app/logs
      - ./static:/app/static
    environment:
      - FLASK_ENV=production
      - FLASK_CONFIG=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 5.2 使用Docker Compose管理

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart
```

---

## 第六步：开机自启配置

### 6.1 使用systemd

创建 `/etc/systemd/system/ia-backend.service`：

```ini
[Unit]
Description=Intelligent Audio Test Backend
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/intelligent-audio-test/backend
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ia-backend
```

---

## 常用命令

### 服务管理

```bash
# 启动
docker start ia-backend
docker-compose -f backend/docker-compose.yml start

# 停止
docker stop ia-backend

# 重启
docker restart ia-backend

# 查看日志
docker logs -f ia-backend
docker logs --tail 100 ia-backend

# 进入容器（调试）
docker exec -it ia-backend /bin/bash
```

### 资源监控

```bash
# 查看容器状态
docker stats ia-backend

# 查看容器信息
docker inspect ia-backend
```

---

## 数据备份

```bash
# 备份数据库
cp backend/data.db backup/data_$(date +%Y%m%d).db

# 备份配置
cp backend/.env backup/.env_$(date +%Y%m%d)
```

---

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| 容器启动失败 | 端口被占用 | 检查5000端口：`lsof -i :5000` |
| 数据库连接失败 | 数据卷挂载失败 | 检查文件权限 |
| FFmpeg不可用 | 未安装 | 确保Dockerfile中已安装ffmpeg |
| 健康检查失败 | 服务未正常启动 | 查看日志：`docker logs ia-backend` |

### 查看日志

```bash
# 容器日志
docker logs ia-backend

# 实时日志
docker logs -f ia-backend

# 应用日志
tail -f backend/logs/app.log
```

---

## 更新升级

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建
docker-compose build

# 3. 重启
docker-compose up -d

# 4. 检查
docker-compose ps
curl http://localhost:5000/health
```
