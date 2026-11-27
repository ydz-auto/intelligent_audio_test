# 隔离环境迁移包（无 Docker / 自建 RustFS）

导出时间：2026-11-26　来源：生产栈 `intelligent-audio-test`（网关 :15000）

## 一、包内容

```
iai_migrate/
├─ db/
│  ├─ intelligent_audio_test.dump      # 整库备份 129.6MB（pg_dump -Fc，TOC 2105 项）
│  └─ fix_audio_paths.sql              # 122 条 Windows 本地路径 → oss://audios/...
├─ bucket/
│  ├─ upload_manifest.csv              # 2101 条音频：audio_id / object_key / size
│  ├─ missing_from_cos.txt             # 26 条原本只存在于旧 COS 的音频（已补拉）
│  └─ test/intelligent_audio_test/     # 直接对应桶内 key 前缀
│     ├─ audios/       2101 个（1.43GB，含 direct/26 个）
│     └─ ref_params/   4835 个（算法参考参数，约 1MB）
├─ env/.env.template                   # RustFS + 原生 PG/Redis 配置模板
└─ scripts/
   ├─ 01_restore_db.sh                 # 还原数据库
   ├─ 03_upload_objects.py             # 桶目录 → RustFS（自动建桶、跳过已存在）
   ├─ 04_fix_audio_paths.sh            # 执行路径修正 SQL
   └─ 05_verify.py                     # 包完整性 / 还原后引用校验
```

合计 6945 个文件、1.6GB。数据库里已包含：646 条在用用例（今天导入）、602 条软删用例、2101 条音频率、标注、标签、用户与权限、API Key、报告与历史评测结果。

**未包含**：`case_result`（19.5GB 历史评测原始响应）、`archives`（日志归档）、`case_pcm`、`case_result` 等本地缓存目录。这些只影响“回看老报告的原始报文/日志”，不影响用例编辑与重新评测；需要时再按同样方式从旧 COS 补拉。

## 二、迁移步骤

### 1. 基础设施

- PostgreSQL 14+、Redis，原生安装（不依赖 Docker）
- RustFS 启动后确认 S3 API 可达，例如 `http://<host>:9000`
- 服务代码与 Python 依赖按仓库 `README.md` 的原生部署方式准备

### 2. 还原数据库

```bash
createdb -U postgres intelligent_audio_test
DATABASE_URL=postgresql://intelligent_audio_test:intelligent_audio_test666@127.0.0.1:5432/intelligent_audio_test \
  bash scripts/01_restore_db.sh
```

### 3. 上传桶数据

```bash
pip install boto3
export OSS_ENDPOINT=http://127.0.0.1:9000
export OSS_ACCESS_KEY=... OSS_SECRET_KEY=...
export OSS_BUCKET_NAME=intelligent-audio-test
export OSS_KEY_PREFIX=test/intelligent_audio_test
python scripts/03_upload_objects.py --dry-run   # 先看数量
python scripts/03_upload_objects.py             # 实际上传（重复执行会跳过同大小对象）
```

真实对象 key = `{OSS_KEY_PREFIX}/audios/<...>`，与库内 `file_path`（`oss://audios/<...>`）一一对应；**前缀必须与库中记录一致**，否则音频全部 404。

### 4. 修正 122 条本地路径音频

```bash
DATABASE_URL=... bash scripts/04_fix_audio_paths.sh
```

这一步把这些音频的 `file_path` 从 `D:\00_static\...` 改为 `oss://audios/import_9000000xx.wav`，对应文件已在包内。

### 5. 配置 .env

复制 `env/.env.template` 为服务根目录 `.env`，重点：

- `STORAGE_BACKEND=rustfs`、`OSS_ENDPOINT/OSS_PUBLIC_ENDPOINT`、`OSS_BUCKET_NAME/OSS_KEY_PREFIX`
- `DATABASE_URL`、`REDIS_URL`
- `JWT_SECRET`、`EVAL_CONFIG_MASTER_KEY`（评估密钥解密依赖，必须与旧环境一致或迁移后重录评估密钥）
- 执行机分离时把 `E2E_TEST_SERVICE_HOST / AUDIO_SERVICE_HOST / DEVICE_SERVICE_HOST` 改成执行机 IP

### 6. 执行机（播放/录音机）

- 部署 `audio_service`、`device_service`、`e2e_test_service` 宿主进程（需 pyaudio/真实声卡），端口 50052 / 50053 / 50051
- `LOCAL_STORAGE_ROOT` 指向执行机本地静态根；若执行机与存储机分离，保持 `AUDIO_STREAM_VIA_GATEWAY=true`，由网关代理取流

### 7. 启动与验收

```bash
python native_bootstrap.py          # 原生引导（建表/种子；已还原的库可只跑校验）
python scripts/05_verify.py --db    # 期望：清单 0 问题、库内引用缺失 0、本地路径残留 0
```

再手工抽 3 条用例确认音频可播放、标注正确，最后跑 1 条端到端用例。

## 三、注意事项

1. **不要改 `OSS_KEY_PREFIX`**（现网是 `test/intelligent_audio_test`），改了就与库内 `file_path` 对不上。
2. 软删的 602 条用例随库还原，报表历史不受影响；如需清理再单独跑 SQL。
3. 若新环境只迁移部分分组，直接删 `bucket/test/intelligent_audio_test/` 下多余对象即可，但库内对应音频会失效。
4. RustFS 需允许 path 寻址（代码 `STORAGE_BACKEND=rustfs` 已按 path 寻址初始化客户端）。
