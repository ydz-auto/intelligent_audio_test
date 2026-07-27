# 本地数据迁移到 S3/MinIO 操作指南

## 迁移脚本

脚本位置：`scripts/migrate_local_to_s3.py`

## 前置条件

1. **OSS/MinIO 已就绪**
   - 开发环境：`docker-compose up -d minio`（端口 9000/9001）
   - 生产环境：S3 已创建好 6 个 bucket（audios/case-result/ref-params/reports/archives/temp）

2. **环境变量已配置**（参考 `.env.example`）
   ```
   OSS_ENDPOINT=https://s3.amazonaws.com         # 生产 S3
   OSS_ACCESS_KEY=AKIAxxxxxx
   OSS_SECRET_KEY=xxxxxxxxxxxx
   OSS_REGION=us-east-1
   LOCAL_STATIC_PATH=/data/static                 # 本地静态文件根目录
   LOCAL_ARCHIVE_PATH=/data/archives              # 本地归档目录
   DATABASE_URL=postgresql://user:pass@host:5432/db  # --update-db 时需要
   ```

## 迁移步骤

### 第 1 步：干跑预览（不实际上传）

```bash
python scripts/migrate_local_to_s3.py --dry-run
```

查看输出，确认：
- 扫描到的文件数量
- 各 bucket 对应的文件数
- 无遗漏

### 第 2 步：上传文件到 OSS

```bash
# 全量迁移
python scripts/migrate_local_to_s3.py

# 只迁移音频
python scripts/migrate_local_to_s3.py --only audios

# 只迁移设备结果
python scripts/migrate_local_to_s3.py --only case_result

# 跳过交互确认（自动化）
python scripts/migrate_local_to_s3.py --no-confirm
```

脚本特性：
- **幂等**：已存在于 OSS 的文件会跳过
- **--force**：强制重新上传（覆盖）
- **进度**：每 100 个文件输出一次进度
- **日志**：所有操作记录到 `migration.log`

### 第 3 步：更新数据库路径

文件上传完后，更新 DB 中存储的本地路径为 OSS key：

```bash
python scripts/migrate_local_to_s3.py --update-db
```

更新字段：
- `audios.file_path`：`/data/static/audios/audio_123.wav` → `audio_123.wav`
- `test_results.result_data_path`：`/data/static/case_result/1/2/dev1/result.json` → `1/2/dev1/result.json`
- `test_results.reference_params_path`：同上

### 第 4 步：验证

1. **上传完整性检查**
   ```bash
   # 对比本地文件数和 OSS 文件数
   find /data/static/audios -type f | wc -l
   # 应等于 OSS 中 audios bucket 的对象数
   ```

2. **DB 路径验证**
   ```sql
   -- 检查是否还有本地路径残留
   SELECT COUNT(*) FROM audios WHERE file_path LIKE '/%';
   -- 应为 0

   SELECT COUNT(*) FROM test_results WHERE result_data_path LIKE '/%';
   -- 应为 0
   ```

3. **功能验证**
   - 上传新音频 → 检查 OSS `audios` bucket
   - 运行 E2E 测试 → 检查 OSS `case-result` bucket
   - 下载报告 → 检查 OSS `reports` bucket

### 第 5 步：清理本地文件（可选，确认无误后）

```bash
# 备份后再删除
tar -czf static_backup_$(date +%Y%m%d).tar.gz /data/static
rm -rf /data/static/audios /data/static/case_result /data/static/ref_params
```

## 迁移数据量参考

| 类别 | 本地目录 | OSS Bucket | 预估文件数 |
|---|---|---|---|
| 音频 | static/audios/ | audios | 数百～数千 |
| 设备结果 | static/case_result/ | case-result | 数千 |
| 参考参数 | static/ref_params/ | ref-params | 数百 |
| 报告 | static/reports/ | reports | 数十 |
| 归档 | archives/ | archives | 数百 |
| 临时 | static/temp_uploads/ | temp | 数十 |

## 故障排除

### Q: 迁移中断了怎么办？
A: 脚本是幂等的，重新运行即可，已上传的文件会跳过。

### Q: 某些文件上传失败？
A: 查看 `migration.log` 中的 ERROR 行，手动重传：
```bash
python scripts/migrate_local_to_s3.py --only audios --force
```

### Q: 数据库更新失败？
A: 检查 DATABASE_URL 环境变量，确保 DB 可连接。可以只重跑 DB 更新：
```bash
# 先上传所有文件
python scripts/migrate_local_to_s3.py --no-confirm
# 再更新 DB
python scripts/migrate_local_to_s3.py --update-db --no-confirm
```

### Q: 想回退？
A: 不要删除本地文件。DB 可以用备份恢复。OSS 中的数据可以清空 bucket。
