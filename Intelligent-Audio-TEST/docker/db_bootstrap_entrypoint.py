# -*- coding: utf-8 -*-
"""INT-272：数据库结构引导 job 入口（compose db_bootstrap 服务 CMD）。

执行 scripts/migrations/README.md 全新库初始化链（全脚本幂等）：
    1. create_all_tables.py            —— 69 表建表（Base.metadata.create_all）
    2. 202608 结构基线 + 审计列 + RBAC 种子
    3. 202609 结构列 + 种子
    4. 202610 结构迁移 + dev 引导用户种子
    （数据回填/清洗类脚本不在引导链内：仅对存量数据有意义，全新库为 no-op）

任一步非零退出即整体失败 —— compose 以 service_completed_successfully 门控
后端服务启动，未引导完成的库不会被业务服务连接。

种子/迁移脚本以子进程运行（与 README 手工口径 1:1，脚本各自处理幂等与输出）；
连接串统一经 DATABASE_URI 环境变量注入（compose 设置）。

INT-1652（DDL 锁预算）：本入口给每个子进程注入 PGOPTIONS，让它们建立的**每一条**
数据库连接（psycopg2 与 SQLAlchemy/psycopg2 底层同是 libpq）在会话级带上：
    lock_timeout                       —— DDL 等锁上限（默认 5s），不再无限等
    statement_timeout                  —— 单条语句上限（默认 300s）
    idle_in_transaction_session_timeout —— 会话在事务里空转上限（默认 60s）
外加 application_name=db_bootstrap（失败时据此只清理本 job 自己的孤儿后端）。
任一步失败 / 超时：打印锁诊断（持锁者 pid + 表名）、清理本 job 的 idle in
transaction 后端，并以非零码退出 —— 迁移进程或容器消失后不会留下占着
ACCESS EXCLUSIVE 锁队列头部的孤儿 Postgres 后端（2026-10-23 事故形态）。
"""
import os
import subprocess
import sys

SCRIPTS = '/opt/scripts'
APP_ROOT = '/app'

# ===== INT-1652：DDL 锁预算 =====
# 事故：db_bootstrap 的 ALTER TABLE 需要 ACCESS EXCLUSIVE，被应用层 idle in
# transaction 一挡就无限等待；发起它的 run 容器被删后 Postgres 后端不退出，
# 永久占住锁队列头部，把整张表的读写全部堵死（/algorithm/* 全站 40s+ → 60s 超时）。
# 没有 lock_timeout 就没有任何自愈可能，故这三个上限是硬性预算（可用环境变量覆盖）。
BOOTSTRAP_APP_NAME = 'db_bootstrap'
DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 300000
DEFAULT_IDLE_IN_TX_TIMEOUT_MS = 60000
# 单步进程级兜底：statement_timeout 之外仍有 Python 层死循环 / 交互提示卡住等
# 不受 SQL 超时约束的等待，超时即 kill 该步并按失败收口（不留孤儿进程/后端）。
DEFAULT_STEP_TIMEOUT_SECONDS = 900


def _int_env(name, default):
    """读取正整数环境变量，非法值回落默认（预算类配置不接受 0/负数）。"""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        print(f"[BOOTSTRAP] [WARN] 环境变量 {name}={raw!r} 非法，回落默认 {default}", flush=True)
        return default
    if value <= 0:
        print(f"[BOOTSTRAP] [WARN] 环境变量 {name}={raw!r} 非正数，回落默认 {default}", flush=True)
        return default
    return value


def lock_budget():
    """本次引导的锁预算（毫秒 / 秒），环境变量可覆盖以便大库放宽。"""
    return {
        'lock_timeout_ms': _int_env('DB_BOOTSTRAP_LOCK_TIMEOUT_MS', DEFAULT_LOCK_TIMEOUT_MS),
        'statement_timeout_ms': _int_env('DB_BOOTSTRAP_STATEMENT_TIMEOUT_MS',
                                         DEFAULT_STATEMENT_TIMEOUT_MS),
        'idle_in_tx_timeout_ms': _int_env('DB_BOOTSTRAP_IDLE_IN_TX_TIMEOUT_MS',
                                          DEFAULT_IDLE_IN_TX_TIMEOUT_MS),
        'step_timeout_s': _int_env('DB_BOOTSTRAP_STEP_TIMEOUT_SECONDS',
                                   DEFAULT_STEP_TIMEOUT_SECONDS),
    }


def build_pgoptions(budget):
    """把锁预算编成 libpq 的 PGOPTIONS 串（会话级 SET 的等价物）。"""
    return (
        f'-c lock_timeout={budget["lock_timeout_ms"]} '
        f'-c statement_timeout={budget["statement_timeout_ms"]} '
        f'-c idle_in_transaction_session_timeout={budget["idle_in_tx_timeout_ms"]}'
    )

# 引导链：按 scripts/migrations/README.md「执行顺序总览」精选结构/种子项。
# 排除项（数据回填/清洗/一次性修复）：backfill_*、cleanup_*、
# drop_task_type_and_testcase_test_type（破坏性收尾，全新库无此列）、
# fix_audio_tags_types（历史临时脚本遗留 + 硬编码连接串）、
# fix_partial_unique_indexes（可选项，沿用运行库现状）。
# （add_laboratory_tables 已于 INT-537 纳入：实验室扩展随 ① 落地，全新库须建表）
BOOTSTRAP_STEPS = [
    # ① 初始建表（69 表）
    ('python', 'scripts/create_all_tables.py'),
    # ② 结构基线：删 FK（应用层管理引用完整性）+ 软删除/审计列 + 索引
    ('python', 'scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py'),
    # ③ 审计/软删除列兜底（逐表对齐 ORM 元数据）
    ('python', 'scripts/migrations/202608/add_audit_columns.py'),
    # ④ 重新评估列
    ('python', 'scripts/migrations/202608/add_reevaluated_at.py'),
    # ④.1 实验室扩展：laboratories 主表 + task_laboratory_relations + 各表 lab_id 列
    #     （INT-493/INT-537 拆分①；脚本幂等，全步骤 CREATE IF NOT EXISTS / 列存在跳过）
    ('python', 'scripts/migrations/202608/add_laboratory_tables.py'),
    # ⑦ RBAC 种子（权限点 + 5 角色，含 INT-537 lab:* 三码）
    ('python', 'scripts/migrations/202608/seed_rbac.py'),
    # ⑧ 评估阈值列
    ('python', 'scripts/migrations/202609/add_pass_threshold_to_eval_params.py'),
    # ⑨ 用例级设备路由列
    ('python', 'scripts/migrations/202609/add_task_case_device_type.py'),
    # ⑩ 已发布任务表 + 日常任务追溯字段
    ('python', 'scripts/migrations/202609/add_published_tasks.py'),
    # 维度列扩展（dimension seeds 的前置：sort_order / agg_denominator /
    # exclude_rounds 为 fresh create_all 库缺失的列；worker_instance_id 为
    # test_results 执行实例列）
    ('python', 'scripts/migrations/202609/add_dimension_sort_order.py'),
    ('python', 'scripts/migrations/202609/add_agg_denominator_column.py'),
    ('python', 'scripts/migrations/202609/add_exclude_rounds_column.py'),
    ('python', 'scripts/migrations/202609/add_worker_instance_id.py'),
    # 维度种子（评估域金标；seed_voice_llm 为 ㉓㉔㉕ 前置）
    ('python', 'scripts/migrations/202609/seed_voice_llm.py'),
    ('python', 'scripts/migrations/202609/seed_interruption_dimensions.py'),
    ('python', 'scripts/migrations/202609/seed_noise_latency.py'),
    ('python', 'scripts/migrations/202609/seed_reject_judge.py'),
    ('python', 'scripts/migrations/202609/seed_non_interactive_latency.py'),
    ('python', 'scripts/migrations/202609/seed_xiaoyi_dimensions.py'),
    ('python', 'scripts/migrations/202609/seed_env_sound_judge.py'),
    # ⑫ 时间戳列 DB 级 DEFAULT（INT-47；create_all 新库为 no-op）
    ('python', 'scripts/migrations/202610/add_timestamp_db_defaults.py'),
    # ⑬ Benchmark 排行 4 表 + 指标映射种子（INT-27）
    ('python', 'scripts/migrations/202610/add_benchmark_tables.py'),
    # ⑯ INT-88 残留约束修复（FK / 唯一约束 / 缺失索引）
    ('python', 'scripts/migrations/202610/fix_leftover_foreign_keys_and_indexes.py'),
    # ⑰-⑲ apis 列扩展（RMS-SPL 映射 / output_types / device adapter 三列）
    ('python', 'scripts/migrations/202610/add_api_rms_spl_mappings.py'),
    ('python', 'scripts/migrations/202610/add_api_output_types.py'),
    ('python', 'scripts/migrations/202610/add_api_device_adapter_columns.py'),
    # ㉑ users schema 漂移收敛 + dev 引导用户种子（INT-156）
    ('python', 'scripts/migrations/202610/fix_users_schema_drift.py', '--apply'),
    # ㉒ user_oauth_bindings 表（全新库 create_all 已含，执行为全 SKIP）
    ('python', 'scripts/migrations/202610/add_user_oauth_bindings.py'),
    # INT-1140 access_tokens 表（Access Token + skill/MCP 鉴权令牌；全新库 create_all 已含，执行为全 SKIP）
    ('python', 'scripts/migrations/202610/add_access_tokens_table.py'),
    # ㉓㉔㉕ INT-192 三族维度种子（依赖 seed_voice_llm）
    ('python', 'scripts/migrations/202610/seed_turn_eval.py'),
    ('python', 'scripts/migrations/202610/seed_env_judge.py'),
    ('python', 'scripts/migrations/202610/seed_interruption_v2.py'),
    # INT-299 CUD 操作人列（幂等兜底）
    ('python', 'scripts/migrations/202610/add_operator_columns_int299.py'),
    # INT-141 收藏表 + 删除操作人列
    ('python', 'scripts/migrations/202610/add_trash_operator_and_favorites.py'),
    # published_tasks 算法类型列（INT-303 追溯）
    ('python', 'scripts/migrations/202610/add_published_task_type_algorithm_type.py'),
    # 自定义 OAuth 提供方种子（INT-147 数据行形态）
    ('python', 'scripts/migrations/202610/seed_custom_oauth_providers.py'),
    # ㉘ task_case_relations (task, case, 路由) 唯一索引（INT-604；建索引前先查重）
    ('python', 'scripts/migrations/202610/add_uq_task_case_route_int604.py'),
    # ㊳ test_cases 执行口径派生列（INT-1469/INT-1565）：create_all 只建缺失的表、
    #    不给存量表补列，存量库（真实库 / 隔离库）缺 derived_test_type 时新镜像
    #    建用例/列表即 UndefinedColumn 400。脚本幂等（列/索引存在即 SKIP、回填按
    #    值比对），全新库为全 SKIP；默认 dry-run，引导链必须带 --apply。
    ('python', 'scripts/migrations/202610/add_derived_test_type_int1469.py', '--apply'),
    # ㊴ report_export_records 报告导出历史表（INT-1555；INT-1609 补迁移守卫）：
    #     create_all 只建缺失的表，建库早于 INT-1555 的存量库在引导链里建表自愈；
    #     脚本幂等（表/索引存在即 SKIP），全新库为全 SKIP。
    ('python', 'scripts/migrations/202610/add_report_export_records_int1555.py'),
    # ㊵ transfer_records / transfer_chunks 传输代理两表（INT-1623）：
    #     create_all_tables.py 此前漏导 transfer_agent 的 PO，这两张表只靠
    #     transfer_agent 启动时自建；本次已收口模型全集（89 表），本步为建库早于
    #     该模块的存量库兜底建表 + 索引 + 唯一约束。脚本幂等（表/索引/约束存在
    #     即 SKIP），全新库为全 SKIP。
    ('python', 'scripts/migrations/202610/add_transfer_agent_tables_int1623.py'),
    # ㊶ device_status_events 补设备类型列 device_kind（INT-1679）：
    #     播放设备控制事件与测试设备事件 id 空间重叠，查询侧按 device_kind='test'
    #     过滤（契约 §1.2）。create_all 只建缺失的表、不给存量表补列，建库早于本卡
    #     的存量库在引导链里自愈；回填只命中 detail.operation ∈ 三个播放控制动作。
    #     脚本幂等（列存在即 SKIP、回填按值比对），全新库为全 SKIP；默认 dry-run，
    #     引导链必须带 --apply。
    ('python', 'scripts/migrations/202610/add_device_kind_int1679.py', '--apply'),
]


def _prepare_env(budget):
    """子进程环境：库连接串映射 + OSS 兜底凭据 + 锁预算 PGOPTIONS。"""
    env = os.environ.copy()
    # 脚本读 BaseConfig.DATABASE_URL（required=True）而非 DATABASE_URI：
    # compose 注入的 DATABASE_URI（迁移脚本口径）同步映射到 DATABASE_URL。
    env.setdefault('DATABASE_URL', env['DATABASE_URI'])
    # BaseConfig 还要求 OSS 凭据（建表路径不触网，仅 import 期校验非空）：
    # 缺省注入与 rustfs 容器一致的本地凭据，显式配置的值优先。
    env.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
    env.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')

    # INT-1652：锁预算经 PGOPTIONS 下发到子进程建立的每条连接（libpq 会话参数，
    # 与执行 DDL 前 SET lock_timeout / statement_timeout 等价，且覆盖到全部 76 个
    # 迁移脚本 —— 它们分别用 psycopg2.connect / create_engine，无法统一插钩子）。
    pgoptions = build_pgoptions(budget)
    inherited = (env.get('PGOPTIONS') or '').strip()
    env['PGOPTIONS'] = f'{inherited} {pgoptions}'.strip() if inherited else pgoptions
    # 只标记本 job 的连接：失败清理时据此 terminate，绝不碰业务服务的会话。
    env['PGAPPNAME'] = BOOTSTRAP_APP_NAME
    return env


def _diagnostic_connection(env):
    """打开一条 autocommit 诊断连接（只读系统视图，不参与迁移事务）。"""
    import psycopg2
    conn = psycopg2.connect(env['DATABASE_URI'], connect_timeout=10,
                            application_name=f'{BOOTSTRAP_APP_NAME}_diag')
    conn.autocommit = True
    return conn


def _print_lock_diagnostics(env):
    """打印当前库的等锁 / 空转会话（表名 + 持锁者 pid），供失败时定位。

    只在失败路径调用：此时迁移子进程已退出，但挡住它的那个会话（例如应用层
    idle in transaction）仍在，正好指出「谁占着哪张表」。
    """
    queries = [
        ('等锁会话', """
            SELECT w.pid AS waiting_pid,
                   host(w.client_addr) AS waiting_client,
                   c.relname AS relation,
                   l.mode AS lock_mode,
                   b.pid AS blocker_pid,
                   host(b.client_addr) AS blocker_client,
                   b.state AS blocker_state,
                   now() - b.state_change AS blocker_state_age,
                   left(regexp_replace(b.query, '\\s+', ' ', 'g'), 100) AS blocker_last_query
              FROM pg_locks l
              JOIN pg_stat_activity w ON w.pid = l.pid
              JOIN pg_locks bl ON bl.locktype = l.locktype
                              AND bl.database IS NOT DISTINCT FROM l.database
                              AND bl.relation IS NOT DISTINCT FROM l.relation
                              AND bl.granted AND bl.pid <> l.pid
              JOIN pg_stat_activity b ON b.pid = bl.pid
              LEFT JOIN pg_class c ON c.oid = l.relation
             WHERE NOT l.granted
               AND l.database = (SELECT oid FROM pg_database
                                  WHERE datname = current_database())
             ORDER BY w.pid
             LIMIT 10
        """),
        ('idle in transaction 会话', """
            SELECT pid, host(client_addr) AS client, state,
                   now() - state_change AS idle_age,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 100) AS last_query
              FROM pg_stat_activity
             WHERE datname = current_database()
               AND pid <> pg_backend_pid()
               AND state LIKE 'idle in transaction%'
             ORDER BY state_change
             LIMIT 10
        """),
        # 失败那一刻迁移语句本身已经退出，等锁方可能已不在——把「持有强锁的会话」
        # 一并列出，才能真正回答「谁占着哪张表」（事故里就是应用层的那个会话）。
        ('持有强锁的会话', """
            SELECT a.pid, host(a.client_addr) AS client, a.state,
                   now() - a.state_change AS state_age,
                   c.relname AS relation, l.mode AS lock_mode,
                   left(regexp_replace(a.query, '\\s+', ' ', 'g'), 100) AS last_query
              FROM pg_locks l
              JOIN pg_stat_activity a ON a.pid = l.pid
              JOIN pg_class c ON c.oid = l.relation
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE l.granted
               AND l.locktype = 'relation'
               AND l.mode IN ('AccessExclusiveLock', 'ExclusiveLock',
                              'ShareRowExclusiveLock', 'ShareLock')
               AND n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND a.pid <> pg_backend_pid()
             ORDER BY a.state_change
             LIMIT 10
        """),
    ]
    print("[BOOTSTRAP] ---- 锁诊断（失败时的库内等锁 / 空转会话）----", flush=True)
    try:
        conn = _diagnostic_connection(env)
    except Exception as exc:  # noqa: BLE001 - 诊断失败不得遮盖原始失败
        print(f"[BOOTSTRAP] 锁诊断连接失败: {exc}", flush=True)
        return
    try:
        with conn.cursor() as cur:
            for title, sql in queries:
                try:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description]
                except Exception as exc:  # noqa: BLE001
                    print(f"[BOOTSTRAP] [{title}] 查询失败: {exc}", flush=True)
                    continue
                if not rows:
                    print(f"[BOOTSTRAP] [{title}] 无", flush=True)
                    continue
                for row in rows:
                    detail = ', '.join(f'{k}={v}' for k, v in zip(cols, row))
                    print(f"[BOOTSTRAP] [{title}] {detail}", flush=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _cleanup_own_orphans(env):
    """terminate 本 job 遗留的 idle in transaction 后端（application_name 精确匹配）。

    迁移步超时被 kill、或脚本异常没关连接时，Postgres 后端可能仍挂在事务里持锁。
    这里只清理 application_name=db_bootstrap 的会话，业务服务连接不受影响。
    返回被终止的 pid 列表。
    """
    terminated = []
    try:
        conn = _diagnostic_connection(env)
    except Exception as exc:  # noqa: BLE001
        print(f"[BOOTSTRAP] 孤儿会话清理跳过（诊断连接失败）: {exc}", flush=True)
        return terminated
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pid FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND application_name = %s
                   AND pid <> pg_backend_pid()
                   AND state LIKE 'idle in transaction%%'
            """, (BOOTSTRAP_APP_NAME,))
            pids = [row[0] for row in cur.fetchall()]
            for pid in pids:
                cur.execute('SELECT pg_terminate_backend(%s)', (pid,))
                terminated.append(pid)
    except Exception as exc:  # noqa: BLE001
        print(f"[BOOTSTRAP] 孤儿会话清理失败: {exc}", flush=True)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    if terminated:
        print(f"[BOOTSTRAP] 已清理本 job 的 idle in transaction 后端: {terminated}", flush=True)
    return terminated


def _run_step(step, script_root, env, confirmation, step_timeout_s):
    """跑单个引导步；返回 (returncode, timed_out)。

    timeout 兜底覆盖 SQL 超时照不到的 Python 层等待；超时时子进程被 kill，
    其连接随进程结束关闭。
    """
    try:
        result = subprocess.run(list(step), cwd=script_root, env=env,
                                input=confirmation + '\n', text=True,
                                timeout=step_timeout_s)
        return result.returncode, False
    except subprocess.TimeoutExpired:
        print(f"[BOOTSTRAP] [FAIL] {step[1]} 超过单步时限 {step_timeout_s}s，已终止进程",
              flush=True)
        return 1, True


def main():
    if not os.path.isdir(SCRIPTS):
        print(f"[BOOTSTRAP] scripts 卷未挂载: {SCRIPTS} 不存在", flush=True)
        return 1
    if not os.environ.get('DATABASE_URI'):
        print("[BOOTSTRAP] DATABASE_URI 未设置", flush=True)
        return 1

    budget = lock_budget()
    env = _prepare_env(budget)
    print(f"[BOOTSTRAP] DDL 锁预算：lock_timeout={budget['lock_timeout_ms']}ms "
          f"statement_timeout={budget['statement_timeout_ms']}ms "
          f"idle_in_transaction_session_timeout={budget['idle_in_tx_timeout_ms']}ms "
          f"单步时限={budget['step_timeout_s']}s", flush=True)
    # 交互式确认类 seed 脚本（202609 seed_voice_llm 等 6 个的 input() 提示）：
    # stdin 预喂 y 逐条确认（脚本幂等，重复执行安全）。
    confirmations = ['y'] * len(BOOTSTRAP_STEPS)
    # 脚本以「仓库根」为 cwd 运行（README 手工口径：python scripts/migrations/...）。
    # BOOTSTRAP_STEPS 的路径自带 scripts/ 前缀，故 script_root 必须是仓库根：
    #   - 卷挂载形态：scripts/ 挂在 /opt/scripts → 取其父目录 /opt 为根；
    #   - 镜像内兜底：COPY 已把 scripts/ 打入 /app/scripts → 根即 /app。
    # （.dockerignore 只排除 scripts/**/__pycache__，镜像内含脚本副本，卷缺席
    #   也可引导；两者内容同源。）
    if os.path.isdir(os.path.join(SCRIPTS, 'migrations')):
        script_root = os.path.dirname(SCRIPTS)
    else:
        script_root = APP_ROOT
    for step in BOOTSTRAP_STEPS:
        script = step[1]
        if not os.path.isfile(os.path.join(script_root, script)):
            print(f"[BOOTSTRAP] [SKIP] 脚本不存在: {script}", flush=True)
            continue
        print(f"[BOOTSTRAP] ==> {script}", flush=True)
        returncode, timed_out = _run_step(step, script_root, env,
                                          confirmations.pop(0),
                                          budget['step_timeout_s'])
        if timed_out or returncode != 0:
            print(f"[BOOTSTRAP] [FAIL] {script} 退出码 {returncode}"
                  f"{'（超时）' if timed_out else ''}", flush=True)
            # INT-1652：失败即收口——先把「谁占着哪张表」打出来（表名 + 持锁者
            # pid），再清掉本 job 自己遗留的空转事务，最后非零退出。既不无声地
            # 挂在锁队列里，也不把连接留在 idle in transaction。
            _print_lock_diagnostics(env)
            _cleanup_own_orphans(env)
            return returncode or 1

    print("[BOOTSTRAP] 数据库结构引导完成（全脚本幂等通过）。", flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - 未预期异常也必须非零退出且可诊断
        import traceback
        traceback.print_exc()
        print(f"[BOOTSTRAP] [FAIL] 引导入口异常: {exc}", flush=True)
        sys.exit(1)
