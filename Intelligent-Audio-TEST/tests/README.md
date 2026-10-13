# 测试隔离规范（INT-163）

并行回归命令与隔离口径的唯一来源。历轮回归中「单文件全绿、并行/共进程红」
的假失败反复消耗逐轮人工归因（int152 / int146 / int145 / int107 / int68 /
int120 族），本规范固化其根因结论与收敛手段。

## 回归口径

```
python -m pytest tests -q -n 8 --dist loadgroup
```

- **默认离线**：不含实机栈用例（tests/api 默认 skip，见下）。栈恰好在跑
  也不再改变结果——同一条命令在同一代码状态下必须产出同一结论。
- 实机验收（直击运行中的 V9.7.31 栈）：`RUN_LIVE_STACK=1` 显式纳入
  tests/api，仍受 require_backend 版本标记约束。
- 已知非隔离红例不在本规范收敛范围：tests/integration/test_task_execute_
  real_chain.py（int118，回归指引已登记的实机链用例）。

## 隔离单元 = 文件（conftest 默认分组）

`tests/conftest.py` 在 `--dist loadgroup` 下把每个测试文件默认成组
（`xdist_group(file:<相对路径>)`）：同文件用例固定同 worker、按收集序执行，
等价于单文件运行；跨文件并行不受影响。

原因（INT-163 实证）：load 调度会把同文件用例拆到不同 worker，每个
worker 各自重跑 module fixture（全新种子库），凡测试间存在序依赖的文件
即并行假失败——int107 第二例（依赖首例播种行）、int152 同名可重建例
（依赖首例软删）单独运行即 1:1 复现并行失败。跨文件共享进程级库并依赖
播种顺序的族（auth / g3 / int147 / int72）仍走 conftest
`_XDIST_GROUP_RULES` 显式跨文件组，优先于默认文件组。

新增测试文件无需登记分组；只有「多文件共享同一进程级库且互相依赖播种
顺序」时才在 `_XDIST_GROUP_RULES` 加显式组。

## 用例编写要求

1. **用例自足**：不得依赖同文件前序用例的副作用。需要种子行/前置状态时
   在本用例内幂等播种（先查后插）或写入模块 fixture。
2. **共享库内不假设空库**：进程级共享 sqlite 文件库下，其它文件的行可能
   已在表内。断言用「种子前基线相对差值」或唯一后缀命名（`_RUN` / uuid）
   + 按名过滤，禁止裸 `count()==N` / 按无后缀名查唯一行。
3. **文件内需要固定 magic id 的**（如 int107 的 91070001）：播种幂等且每
   用例执行前自播种，不依赖兄弟用例。

## 共享进程库四类陷阱（历史归因）

| 类别 | 机制 | 收敛手段 |
| --- | --- | --- |
| 进程级 sqlite 文件库 | conftest 的 `DATABASE_URL` 兜底在进程内首个 import 冻结；文件内 `setdefault` 恒为 no-op，同 worker 全部文件共享同一库文件 | 默认文件分组 + 基线相对断言（上文） |
| 模块级单例 / 全局后台线程 | `get_db_handler()` 日志 worker 等跨文件存活，污染事件计数/捕获断言 | tests/unit/conftest.py 的 `_quiesce_global_log_worker` autouse 清理，勿删 |
| **真实 Redis** | 键空间跨 worker、与实机栈全局共享：DistributedLock（lock:spl:calibration:{api_id}）并发抢锁 → 409 假失败（int68 实证）；stats 缓存键同理 | 业务测试内打桩（int68 的 `_stub_calibration_redis_lock`）；必须触真库的用例用专用 scratch 键 + 用例前后删除（int204 的 scratch_redis 范式），Redis 不可用 skip |
| 环境变量残留 | 见下节 DATABASE_URL 陷阱 | 不在 shell 预置任何业务环境变量跑 pytest |

## ⚠️ DATABASE_URL 陷阱（勿在 shell 预置）

跑 `tests/unit/` 认证族（test_auth_* / test_g3_* / test_int147_* 等）及
一切带 `os.environ.setdefault('DATABASE_URL', ...)` 的测试文件时，**不要
在 shell 里预置/导出 `DATABASE_URL`（含 `.env` 的值）**：预置后各测试文件
的 `setdefault` 全部失效，用例会连上真实 dev 库并写入测试行
（INT-147 自测期实证：92 测试用户 + 27 测试提供方残留，已按标记清理）。
正常裸跑即可：`python -m pytest tests/unit/...`。conftest 会自行兜底进程
级临时 sqlite 文件库，xdist worker 各得独立库。

## 测试/业务库隔离（INT-246）

共享业务库 `intelligent_audio_test` 是负责人数据所在库，**pytest 与 agent
冒烟一律禁写**；集群另有隔离测试库 `intelligent_audio_test_test` 专供
实机链路回归 / 集成冒烟 / 验收。库名常量唯一来源：
`shared/constants/database.py`。

- **pytest 会话守卫**（tests/conftest.py）：生效 DATABASE_URL 指向共享
  业务库时整个会话拒绝启动（宁可拒绝，绝不静默写业务库）——上节「勿在
  shell 预置」由此获得机器强制兜底。裸跑（sqlite 兜底）与显式指向隔离
  测试库均放行。
- **实机门禁**（tests/api/conftest.py + api_gateway /health 的 database
  字段）：`RUN_LIVE_STACK=1` 时栈必须已切隔离测试库（database ==
  intelligent_audio_test_test），指向共享库或缺字段（旧栈）一律 fail。
- **实机冒烟标准流程**：
  1. `python run_all.py --test-db` —— 整栈切隔离库起栈（库不存在自动建）
  2. 需要种子时以 `DATABASE_URI` 指向隔离库重播 `scripts/migrations` 下
     seed_*.py
  3. `RUN_LIVE_STACK=1 python -m pytest tests/api -q`（或手动冒烟）
  4. `python scripts/reset_test_db.py` —— 冒烟后清库（TRUNCATE 全表，
     硬拒共享库名）
- **集成推送门禁四步冒烟**（INT-314，登录→建用例→dry 执行→报告）：
  `python scripts/smoke_gate.py` 一键执行——并行隔离栈（端口 +1000）上
  自动完成前置引导与四步断言，数据自建自清，详见 `docs/回归测试指引.md`
  「推送前冒烟门禁」节；与上列全栈口径互补（前者门禁用并行栈不重启共享栈）。
- 共享库仅允许冒烟验收的**只读探测**与负责人手动操作；历史残留清理走
  `scripts/migrations/202610/cleanup_int246_smoke_residue.py`（软删 =
  回收站语义）。

## 实机栈用例（tests/api）

- 默认全部 skip（`_live_stack_gate`），回归信号与栈启停解耦。
- 实机验收：`python run_all.py --test-db` 起栈后
  `RUN_LIVE_STACK=1 python -m pytest tests/api -q`（可叠加 `-n 8`，但注意
  用例间共享栈内业务数据，写入型用例以唯一后缀命名）；栈指向共享业务库
  时门禁直接 fail（INT-246）。

## 新增用例 checklist

- [ ] 单文件运行全绿（`python -m pytest tests/unit/test_xxx.py -q`）
- [ ] 无跨用例序依赖；magic id 用例内幂等自播种
- [ ] 断言基线相对或按唯一名过滤；不假设共享库为空
- [ ] 不触真实 Redis（或走 scratch 键 + 清理 + 不可用 skip）
- [ ] 不要求 shell 预置环境变量
- [ ] 实机栈用例放 tests/api 并接受 RUN_LIVE_STACK 门控
