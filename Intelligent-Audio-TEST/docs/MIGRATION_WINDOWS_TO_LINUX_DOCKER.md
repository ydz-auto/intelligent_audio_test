# PostgreSQL 迁移文档 (Windows -> Linux Docker)

## 前提条件

- Windows 上已安装 PostgreSQL 并运行正常
- Linux 服务器已安装 Docker
- 有权限访问 Windows 和 Linux 服务器

---

## 第一部分：Windows 上导出数据

### 1.1 检查 PostgreSQL 服务状态

确保 Windows 上的 PostgreSQL 正在运行：

```powershell
& "C:\S2TT\environment\pgsql\bin\pg_isready.exe" -p 5432
```

### 1.2 导出数据库

使用 `pg_dump` 导出数据库（压缩格式减少传输大小）：

```powershell
# 切换到 PostgreSQL bin 目录
cd C:\S2TT\environment\pgsql\bin

# 导出数据库（压缩）
.\pg_dump.exe -U postgres -d intelligent_audio_test | gzip > C:\temp\backup.sql.gz

# 或者不压缩版本
.\pg_dump.exe -U postgres -d intelligent_audio_test > C:\temp\backup.sql
```

### 1.3 验证导出文件

```powershell
# 检查文件大小
dir C:\temp\backup.sql.gz

# 如果文件很大，可以分割成多个小文件
# Windows 下使用 PowerShell 分割
$content = Get-Content C:\temp\backup.sql -Encoding UTF8
$partSize = 100MB
for ($i = 0; $i -lt $content.Count; $i += $partSize) {
    $part = $content[$i..($i + $partSize - 1)]
    $part | Out-File -FilePath "C:\temp\backup_part_$($i / $partSize).sql" -Encoding UTF8
}
```

### 1.4 传输文件到 Linux

使用 `scp`、`rsync` 或其他文件传输工具：

```bash
# 使用 scp 传输（单文件）
scp C:\temp\backup.sql.gz user@linux_server:/tmp/

# 使用 psftp/pscp（Windows 原生）
pscp -P 22 C:\temp\backup.sql.gz user@linux_server:/tmp/

# 如果是大文件，建议使用 rsync
rsync -avz --progress C:\temp\backup.sql.gz user@linux_server:/tmp/
```

---

## 第二部分：Linux Docker 安装

### 2.1 安装 Docker

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
```

### 2.2 创建数据目录

```bash
# 创建 PostgreSQL 数据目录（指定位置）
sudo mkdir -p /home/user/postgresql/data
sudo mkdir -p /home/user/postgresql/logs

# 设置权限
sudo chown -R 999:999 /home/user/postgresql/data
sudo chmod -R 755 /home/user/postgresql
```

### 2.3 创建 Docker 容器

```bash
# 创建 PostgreSQL 容器（指定数据目录）
docker run -d \
  --name intelligent_audio_postgres \
  -e POSTGRES_PASSWORD=postgres123 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=postgres \
  -v /home/user/postgresql/data:/var/lib/postgresql/data \
  -v /home/user/postgresql/logs:/var/log/postgresql \
  -p 5432:5432 \
  --restart unless-stopped \
  postgres:16

# 参数说明：
# -d: 后台运行
# --name: 容器名称
# -e POSTGRES_PASSWORD: postgres 用户密码
# -e POSTGRES_USER: 创建超级用户
# -e POSTGRES_DB: 创建默认数据库
# -v /home/user/postgresql/data: 数据卷映射（指定目录）
# -p 5432:5432: 端口映射
# --restart unless-stopped: 开机自启
```

### 2.4 验证容器状态

```bash
# 检查容器是否运行
docker ps

# 检查容器日志
docker logs intelligent_audio_postgres

# 测试 PostgreSQL 连接
docker exec -it intelligent_audio_postgres psql -U postgres
```

### 2.5 常用 Docker 命令

```bash
# 启动容器
docker start intelligent_audio_postgres

# 停止容器
docker stop intelligent_audio_postgres

# 重启容器
docker restart intelligent_audio_postgres

# 进入容器
docker exec -it intelligent_audio_postgres bash

# 查看容器内 PostgreSQL 版本
docker exec intelligent_audio_postgres psql --version
```

---

## 第三部分：恢复数据到 Docker PostgreSQL

### 3.1 复制备份文件到容器

```bash
# 方法1：直接复制到容器数据卷
cp /tmp/backup.sql.gz /home/user/postgresql/data/

# 方法2：使用 docker cp
docker cp /tmp/backup.sql.gz intelligent_audio_postgres:/tmp/

# 方法3：如果使用命名卷
docker volume create pgdata
docker run -d --name postgres_tmp -v pgdata:/var/lib/postgresql/data postgres:16
docker cp backup.sql.gz postgres_tmp:/tmp/
docker stop postgres_tmp
docker rm postgres_tmp
```

### 3.2 创建目标数据库

```bash
# 进入容器
docker exec -it intelligent_audio_postgres bash

# 创建 intelligent_audio_test 数据库
su - postgres
psql -c "CREATE USER intelligent_audio_test WITH PASSWORD 'intelligent_audio_test666'"
psql -c "CREATE DATABASE intelligent_audio_test WITH OWNER intelligent_audio_test"
psql -c "GRANT ALL PRIVILEGES ON DATABASE intelligent_audio_test TO intelligent_audio_test"

# 退出
exit
```

### 3.3 恢复数据

```bash
# 进入容器
docker exec -it intelligent_audio_postgres bash

# 解压并恢复（压缩格式）
gunzip -c /tmp/backup.sql.gz | psql -U postgres -d intelligent_audio_test

# 或直接恢复（未压缩格式）
psql -U postgres -d intelligent_audio_test -f /tmp/backup.sql

# 如果有分割文件，按顺序恢复
cat /tmp/backup_part_*.sql | psql -U postgres -d intelligent_audio_test
```

### 3.4 验证恢复结果

```bash
# 进入容器
docker exec -it intelligent_audio_postgres psql -U postgres -d intelligent_audio_test

# 检查数据库
\list

# 检查表
\dt

# 检查记录数
SELECT COUNT(*) FROM logs;
SELECT COUNT(*) FROM test_tasks;

# 退出
\q
exit
```

---

## 第四部分：验证应用配置

### 4.1 修改应用数据库连接

确保 Linux 上的应用连接字符串正确：

```python
# config.py 或环境变量
SQLALCHEMY_DATABASE_URI = 'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
```

### 4.2 测试连接

```bash
# 测试从宿主机连接（如果需要远程访问）
psql -h localhost -p 5432 -U intelligent_audio_test -d intelligent_audio_test

# 或使用 Docker 网络
docker network ls
docker network inspect bridge
```

---

## 注意事项

### 编码问题

```bash
# 确保数据库编码是 UTF-8
docker exec intelligent_audio_postgres psql -U postgres -c "SHOW server_encoding;"

# 如果不是 UTF-8，需要重建数据库
docker exec intelligent_audio_postgres psql -U postgres -c "UPDATE pg_database SET encoding = 6 WHERE datname = 'intelligent_audio_test'"
```

### 权限问题

```bash
# 如果恢复后出现权限问题
docker exec intelligent_audio_postgres bash -c "chown -R postgres:postgres /var/lib/postgresql/data"

# 修复序列权限
docker exec intelligent_audio_postgres psql -U postgres -d intelligent_audio_test -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO intelligent_audio_test"
```

### Docker 数据持久化

```bash
# 查看数据卷位置
docker inspect intelligent_audio_postgres --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'

# 备份数据卷
docker run --rm -v /home/user/postgresql/data:/data -v /tmp:/backup ubuntu tar czf /backup/postgres_backup.tar.gz /data

# 恢复数据卷
docker run --rm -v /home/user/postgresql/data:/data -v /tmp:/backup ubuntu tar xzf /backup/postgres_backup.tar.gz -C /
```

---

## 故障排除

### 问题：pg_dump 导出时报错 "no password supplied"

```powershell
# 解决：设置 PGPASSWORD 环境变量
$env:PGPASSWORD = 'postgres123'
.\pg_dump.exe -U postgres -d intelligent_audio_test | gzip > backup.sql.gz
```

### 问题：恢复时出现编码错误

```bash
# 解决：设置客户端编码
export PGCLIENTENCODING=UTF8
gunzip -c /tmp/backup.sql.gz | psql -U postgres -d intelligent_audio_test
```

### 问题：容器无法启动

```bash
# 查看日志
docker logs intelligent_audio_postgres

# 常见问题：数据目录权限
sudo chown -R 999:999 /home/user/postgresql/data

# 或者重新创建容器
docker stop intelligent_audio_postgres
docker rm intelligent_audio_postgres
docker run -d --name intelligent_audio_postgres ...
```
