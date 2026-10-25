# INT-1799 取证探针（B1 后端实施）

`docker` 真实栈 `:15000` 只跑 V9.7.31 分支、未部署本卡分支，按 devloop 的
「未部署时代替口径」用**主库只读副本 + 进程内真实服务/回归 gRPC**取证。

## 前置：造一个不带新列的 apis 库副本

```bash
# 1) 建库
docker exec intelligent-audio-test-postgres-1 psql -U intelligent_audio_test \
  -d postgres -c "DROP DATABASE IF EXISTS int1799_equiv" \
  -c "CREATE DATABASE int1799_equiv"
# 2) 克隆主库 apis 表（旧形态：无 protocol / streaming 列）
docker exec intelligent-audio-test-postgres-1 pg_dump -U intelligent_audio_test \
  --no-owner --no-privileges -t apis intelligent_audio_test \
  | docker exec -i intelligent-audio-test-postgres-1 psql -U intelligent_audio_test \
      -d int1799_equiv -q
# 3) 补 3 行 legacy websocket_api 存量行（主库 websocket_api 为 0 行，B0 §2.2）
python _int1799_probe/make_equiv_db.py int1799_equiv
```

## 迁移脚本（加列 → 回填 → 收紧 → 删 meta.protocol）

```bash
export DATABASE_URL=postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:15432/int1799_equiv
python scripts/migrations/202610/add_api_protocol_streaming_int1798.py          # dry-run：扫描/待改/冲突
python scripts/migrations/202610/add_api_protocol_streaming_int1798.py --apply  # 执行
python scripts/migrations/202610/add_api_protocol_streaming_int1798.py --apply  # 幂等复核：全 SKIP
```

非法/冲突库（预期 ABORT、退出码 1、DDL 与数据全部回滚）：
把副本里任一行改成 `device_type='physical'`，或给 `http_api` 行塞
`meta.protocol='ws'`，再 `--apply`。

## 三个探针

```bash
export OSS_ACCESS_KEY=test OSS_SECRET_KEY=test
# CRUD 读写/筛选/拒绝规则（真 Postgres）
python _int1799_probe/crud_probe.py
# 跨服务接线：真 gRPC server（本卡 servicer）↔ 真 ACL（task_service 亲和域派生）
python _int1799_probe/affinity_probe.py
# 存量等价性：迁移后逐行「老 device_type 路由 == 新 lane 路由」
python _int1799_probe/routing_equiv_probe.py
```

> `routing_equiv_probe` 会跳过「迁移后由新代码建的行」（`device_type` 列已不再
> 维护，恒为默认值，拿它当旧口径比较无意义），跳过条数会打印出来。
