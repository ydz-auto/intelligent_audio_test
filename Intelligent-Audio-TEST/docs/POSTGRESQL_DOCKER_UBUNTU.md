# Ubuntu Docker 安装 PostgreSQL 到指定目录

## 环境说明

- **操作系统**: Ubuntu 20.04/22.04/24.04
- **Docker 版本**: 20.10+
- **PostgreSQL 版本**: 16 (可自定义)
- **安装目录**: `/home/user/postgresql` (可自定义)

---

## 目录结构

```
/home/user/postgresql/
├── data/           # PostgreSQL 数据目录
├── backups/        # 备份文件存放
├── logs/           # PostgreSQL 日志
├── scripts/        # 运维脚本
└── config/         # 配置文件（可选）
```

---

## 第一部分：基础环境准备

### 1.1 更新系统

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 1.2 安装必要工具

```bash
sudo apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    ca-certificates \
    gnupg \
    lsb-release
```

### 1.3 安装 Docker

```bash
# 安装 Docker（如果未安装）
curl -fsSL https://get.docker.com | sh

# 或使用 apt 安装
sudo apt-get install -y docker.io docker-compose

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 添加当前用户到 docker 组（免 sudo）
sudo usermod -aG docker $USER

# 验证安装
docker --version
docker-compose --version
```

---

## 第二部分：创建目录结构

### 2.1 创建目录

```bash
# 创建主目录
sudo mkdir -p /home/user/postgresql/data
sudo mkdir -p /home/user/postgresql/backups
sudo mkdir -p /home/user/postgresql/logs
sudo mkdir -p /home/user/postgresql/scripts

# 设置目录权限
# Docker 容器内 postgres 用户 UID 为 999
sudo chown -R 999:999 /home/user/postgresql/data
sudo chown -R 999:999 /home/user/postgresql/logs
sudo chmod -R 755 /home/user/postgresql
```

### 2.2 创建备份脚本目录

```bash
mkdir -p /home/user/postgresql/scripts
chmod +x /home/user/postgresql/scripts/*.sh
```

---

## 第三部分：创建 PostgreSQL 容器

### 3.1 基本容器创建

```bash
docker run -d \
  --name postgresql \
  -e POSTGRES_PASSWORD=postgres123 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=postgres \
  -v /home/user/postgresql/data:/var/lib/postgresql/data \
  -v /home/user/postgresql/logs:/var/log/postgresql \
  -p 5432:5432 \
  --restart unless-stopped \
  --health-cmd="pg_isready -U postgres" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=5 \
  postgres:16
```

### 3.2 完整版本（带自定义配置）

```bash
docker run -d \
  --name postgresql \
  -e POSTGRES_PASSWORD=postgres123 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=postgres \
  -v /home/user/postgresql/data:/var/lib/postgresql/data \
  -v /home/user/postgresql/logs:/var/log/postgresql \
  -p 5432:5432 \
  -e POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C" \
  --restart unless-stopped \
  --memory=4g \
  --memory-swap=8g \
  --cpus=2 \
  --cpuset-cpus="0,1" \
  postgres:16
```

### 3.3 参数说明

| 参数 | 说明 |
|------|------|
| `--name postgresql` | 容器名称 |
| `-e POSTGRES_PASSWORD` | postgres 用户密码 |
| `-e POSTGRES_USER` | 超级用户名称 |
| `-e POSTGRES_DB` | 默认数据库名称 |
| `-v /home/user/postgresql/data` | 数据卷映射（指定目录） |
| `-v /home/user/postgresql/logs` | 日志目录映射 |
| `-p 5432:5432` | 端口映射（宿主机:容器） |
| `--restart unless-stopped` | 开机自启 |
| `--memory=4g` | 内存限制 |
| `--cpus=2` | CPU 核心数限制 |

---

## 第四部分：配置 PostgreSQL

### 4.1 进入容器配置

```bash
# 进入容器
docker exec -it postgresql bash

# 切换到 postgres 用户
su - postgres

# 编辑配置
vim /var/lib/postgresql/data/postgresql.conf
```

### 4.2 常用配置项

```bash
# postgresql.conf 常用配置

# 连接配置
listen_addresses = '*'
port = 5432
max_connections = 200

# 内存配置
shared_buffers = 1GB
effective_cache_size = 3GB
work_mem = 64MB

# 写入配置
wal_buffers = 64MB
checkpoint_completion_target = 0.9

# 日志配置
logging_collector = on
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '

# 慢查询日志
log_min_duration_statement = 1000
log_connections = on
log_disconnections = on

# 编码配置
datestyle = 'iso, mdy'
timezone = 'Asia/Shanghai'
lc_messages = 'C.UTF-8'
lc_monetary = 'C.UTF-8'
lc_numeric = 'C.UTF-8'
lc_time = 'C.UTF-8'
default_text_search_config = 'pg_catalog.english'
```

### 4.3 配置访问权限

```bash
# 编辑 pg_hba.conf
vim /var/lib/postgresql/data/pg_hba.conf

# 添加以下内容（允许远程连接）
# IPv4 本地连接
host    all     all     127.0.0.1/32    md5
# IPv4 远程连接（根据需要调整 IP 段）
host    all     all     0.0.0.0/0       md5
# IPv6 本地连接
host    all     all     ::1/128         md5
```

### 4.4 重启 PostgreSQL

```bash
# 退出容器
exit
exit

# 重启容器
docker restart postgresql

# 检查状态
docker ps
docker logs postgresql
```

---

## 第五部分：创建应用数据库

### 5.1 创建数据库和用户

```bash
# 进入容器
docker exec -it postgresql psql -U postgres

# 创建数据库
CREATE DATABASE intelligent_audio_test;

# 创建用户
CREATE USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666';

# 设置用户权限
GRANT ALL PRIVILEGES ON DATABASE intelligent_audio_test TO intelligent_audio_test;

# 切换到目标数据库
\c intelligent_audio_test

# 授予 schema 权限
GRANT ALL PRIVILEGES ON SCHEMA public TO intelligent_audio_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO intelligent_audio_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO intelligent_audio_test;

# 退出
\q
exit
```

### 5.2 验证连接

```bash
# 从容器内连接
docker exec -it postgresql psql -U intelligent_audio_test -d intelligent_audio_test

# 从宿主机连接（需要安装客户端）
psql -h localhost -p 5432 -U intelligent_audio_test -d intelligent_audio_test
```

---

## 第六部分：运维脚本

### 6.1 备份脚本

```bash
# 创建备份脚本
cat > /home/user/postgresql/scripts/backup.sh << 'EOF'
#!/bin/bash

# 配置
BACKUP_DIR="/home/user/postgresql/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="intelligent_audio_test"
DB_USER="postgres"
DB_PASS="postgres123"
KEEP_DAYS=7

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
export PGPASSWORD=$DB_PASS
pg_dump -h localhost -p 5432 -U $DB_USER -d $DB_NAME -F c -f "$BACKUP_DIR/backup_${DATE}.dump"

# 删除旧备份
find $BACKUP_DIR -name "backup_*.dump" -mtime +$KEEP_DAYS -delete

# 清理
unset PGPASSWORD

echo "Backup completed: backup_${DATE}.dump"
EOF

chmod +x /home/user/postgresql/scripts/backup.sh
```

### 6.2 恢复脚本

```bash
# 创建恢复脚本
cat > /home/user/postgresql/scripts/restore.sh << 'EOF'
#!/bin/bash

# 配置
BACKUP_DIR="/home/user/postgresql/backups"
DB_NAME="intelligent_audio_test"
DB_USER="postgres"
DB_PASS="postgres123"

# 检查参数
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo "Available backups:"
    ls -1 $BACKUP_DIR/backup_*.dump
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# 执行恢复
export PGPASSWORD=$DB_PASS

# 终止所有连接到目标数据库
docker exec postgresql psql -U $DB_USER -c "
    SELECT pg_terminate_backend(pid) 
    FROM pg_stat_activity 
    WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
"

# 删除并重建数据库
docker exec postgresql psql -U $DB_USER -c "DROP DATABASE IF EXISTS $DB_NAME"
docker exec postgresql psql -U $DB_USER -c "CREATE DATABASE $DB_NAME"

# 恢复数据
pg_restore -h localhost -p 5432 -U $DB_USER -d $DB_NAME -F c -v "$BACKUP_FILE"

unset PGPASSWORD

echo "Restore completed from: $BACKUP_FILE"
EOF

chmod +x /home/user/postgresql/scripts/restore.sh
```

### 6.3 自动备份定时任务

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每天凌晨 3 点备份）
0 3 * * * /home/user/postgresql/scripts/backup.sh >> /home/user/postgresql/logs/backup.log 2>&1
```

---

## 第七部分：常用命令

### 7.1 容器管理

```bash
# 启动
docker start postgresql

# 停止
docker stop postgresql

# 重启
docker restart postgresql

# 查看状态
docker ps -a | grep postgresql

# 查看日志
docker logs -f postgresql
docker logs --tail 100 postgresql
```

### 7.2 数据库连接

```bash
# 进入容器
docker exec -it postgresql bash

# 连接数据库（作为 postgres）
docker exec -it postgresql psql -U postgres

# 连接数据库（作为应用用户）
docker exec -it postgresql psql -U intelligent_audio_test -d intelligent_audio_test

# 执行 SQL 文件
docker exec -i postgresql psql -U postgres -d intelligent_audio_test < backup.sql
```

### 7.3 数据管理

```bash
# 查看数据库大小
docker exec postgresql psql -U postgres -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database ORDER BY pg_database_size(pg_database.datname) DESC;"

# 查看表大小
docker exec postgresql psql -U postgres -d intelligent_audio_test -c "SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# 查看连接数
docker exec postgresql psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## 第八部分：故障排除

### 问题 1：容器无法启动

```bash
# 检查日志
docker logs postgresql

# 常见原因：数据目录权限
sudo chown -R 999:999 /home/user/postgresql/data

# 常见原因：端口被占用
netstat -tlnp | grep 5432
lsof -i:5432

# 解决方法：更换端口
docker stop postgresql
docker rm postgresql
docker run -d ... -p 5433:5432 ...
```

### 问题 2：无法远程连接

```bash
# 检查防火墙
sudo ufw status
sudo ufw allow 5432/tcp

# 检查 Docker 端口映射
docker port postgresql

# 检查 PostgreSQL 监听地址
docker exec postgresql psql -U postgres -c "SHOW listen_addresses;"
```

### 问题 3：内存不足

```bash
# 监控容器资源使用
docker stats

# 限制容器内存
docker stop postgresql
docker rm postgresql
docker run -d \
  --name postgresql \
  --memory=2g \
  --memory-swap=4g \
  ...其他参数...
```

### 问题 4：数据损坏

```bash
# 检查数据完整性
docker exec postgresql psql -U postgres -c "SELECT * FROM pg_database WHERE datname='intelligent_audio_test';"

# 修复序列
docker exec postgresql psql -U postgres -d intelligent_audio_test -c "SELECT setval('id_seq', COALESCE(MAX(id), 1), true) FROM table_name;"
```

---

## 附录：docker-compose.yml 示例

```yaml
version: '3.8'

services:
  postgresql:
    image: postgres:16
    container_name: postgresql
    environment:
      POSTGRES_PASSWORD: postgres123
      POSTGRES_USER: postgres
      POSTGRES_DB: postgres
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
    volumes:
      - /home/user/postgresql/data:/var/lib/postgresql/data
      - /home/user/postgresql/logs:/var/log/postgresql
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 10s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 1G
```

启动方式：
```bash
# 创建容器
docker-compose up -d

# 停止容器
docker-compose down

# 查看状态
docker-compose ps
```
