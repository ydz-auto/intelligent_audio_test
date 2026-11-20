# -*- coding: utf-8 -*-
"""INT-2590 真实 PG 探针：device_service 后台线程只读路径必须结束事务。

事故（INT-2588）：宿主 device_service 的 presence / monitor 后台线程在每轮只读
查询后既不 commit 也不 rollback，连接以 ``idle in transaction`` 常驻 12 小时，
持有 ``devices`` / ``laboratories`` 的 AccessShareLock，把 db_bootstrap 的
``ALTER TABLE devices ADD COLUMN lab_id`` 顶到锁超时（55P03）。

本脚本连 docker 主库（默认 localhost:5432），在**同一线程**里按修复后的调用路径
走两轮：
  1. presence 轮：``device_repository.list_devices``（内含 ``resolve_lab_names``）
     → ``resolve_lab_names`` → 轮次收尾 ``remove_db_session()``；
  2. monitor 轮：``device_monitor_repository.list_enabled_alarm_rules`` → 轮次收尾。
每步之间用 ``pg_stat_activity`` 按本轮实际执行过语句的 backend pid 取 ``state``；
同时用 ``--legacy`` 复现修复前的形态（同样的只读 SQL，无任何收尾）作 before 对照。

只读约束：脚本只执行 SELECT / pg_stat_activity 查询，不写数据、不 TRUNCATE /
reset / drop，不重启任何服务。

用法（项目根目录）：
    python scripts/probe_int2590_bg_thread_read_tx.py            # 默认 before + after
    python scripts/probe_int2590_bg_thread_read_tx.py --fixed     # 只跑 after
连接串可用环境变量 ``PROBE_DATABASE_URL`` 覆盖。
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_DSN = ('postgresql://intelligent_audio_test:intelligent_audio_test666'
               '@localhost:5432/intelligent_audio_test')
DSN = os.environ.get('PROBE_DATABASE_URL', DEFAULT_DSN)
# shared 的 BaseConfig 在首次导入即冻结 DATABASE_URL，必须先设好再 import 业务模块
os.environ['DATABASE_URL'] = DSN
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine, event, text  # noqa: E402

from shared.config.query_constants import QueryConstants  # noqa: E402
from shared.models.database import (  # noqa: E402
    get_db_session,
    get_engine,
    init_db,
    remove_db_session,
)

# 采样连接独立于被测 engine：AUTOCOMMIT 保证采样本身不会留下 idle in transaction
_SAMPLER = create_engine(DSN, isolation_level='AUTOCOMMIT', pool_size=1)

# 本轮实际执行过语句的 backend pid（按 engine 事件采集，无额外 SQL 干扰）
_round_pids = set()


def _install_pid_recorder():
    engine = get_engine()

    @event.listens_for(engine, 'after_cursor_execute')
    def _record_pid(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        try:
            _round_pids.add(conn.connection.dbapi_connection.get_backend_pid())
        except Exception:  # noqa: BLE001 - 采集失败不影响探针
            pass


def _sample(label):
    """按本轮 pid 查 pg_stat_activity，返回 [(pid, state, idle_seconds, last_query)]。"""
    pids = sorted(_round_pids)
    if not pids:
        return label, []
    placeholders = ', '.join(f':p{i}' for i in range(len(pids)))
    params = {f'p{i}': v for i, v in enumerate(pids)}
    with _SAMPLER.connect() as conn:
        rows = conn.execute(
            text(
                'SELECT pid, state, '
                'extract(epoch FROM now() - state_change)::int AS idle_seconds, '
                'left(query, 96) AS last_query '
                f'FROM pg_stat_activity WHERE pid IN ({placeholders}) ORDER BY pid'
            ),
            params,
        ).fetchall()
    return label, [tuple(row) for row in rows]


def _print_sample(label, rows, judged=True):
    """打印一次采样。judged=False 表示轮内采样（不以 idle in transaction 判负）。"""
    print(f'\n[采样] {label}   backend pid={sorted(_round_pids) or "-"}')
    print('    SELECT pid, state, idle_seconds, left(query,96) FROM pg_stat_activity '
          'WHERE pid IN (...)')
    if not rows:
        print('    (无匹配行：连接已归还且进程未持有该 backend)')
        return
    for pid, state, idle_seconds, last_query in rows:
        if state == 'idle in transaction':
            flag = 'FAIL' if judged else '轮内'
        else:
            flag = 'OK'
        print(f'    pid={pid} state={state!r} idle={idle_seconds}s [{flag}]')
        print(f'      last_query={last_query}')


def _reset_round():
    _round_pids.clear()


# ==================== BEFORE：修复前形态复现 ====================

def run_legacy_round():
    """复现修复前：同样的只读查询，结束后无收尾，事务悬挂。"""
    print('\n' + '=' * 78)
    print('BEFORE（修复前形态：只读查询后不 commit / 不 rollback）')
    print('=' * 78)

    _reset_round()
    session = get_db_session()
    # 与 list_devices / resolve_lab_names / list_enabled_alarm_rules 等价的只读 SQL
    session.execute(text('SELECT id FROM devices WHERE deleted = false LIMIT 500')).fetchall()
    legacy_lab = _sample('presence: devices 查询后（无收尾）')

    session.execute(text(
        'SELECT id, name FROM laboratories WHERE deleted = false LIMIT 500')).fetchall()
    legacy_lab2 = _sample('presence: laboratories 查询后（无收尾）')

    session.execute(text(
        'SELECT id FROM device_alarm_rules WHERE deleted = false AND enabled = true '
        'LIMIT 500')).fetchall()
    legacy_monitor = _sample('monitor: device_alarm_rules 查询后（无收尾）')

    for pair in (legacy_lab, legacy_lab2, legacy_monitor):
        _print_sample(*pair)

    # 清掉 before 形态，避免污染 after 的采样
    remove_db_session()
    _print_sample('before 段收尾 remove_db_session() 后', *_sample('cleanup')[1:])

    return [legacy_lab, legacy_lab2, legacy_monitor]


# ==================== AFTER：修复后的真实调用路径 ====================

def run_fixed_round():
    """按修复后的路径走一轮 presence + 一轮 monitor，逐步采样。

    采样点分两类：
    - 「轮内」：后台线程一轮尚未结束，事务本就开在轮内（修复不改仓储读方法的
      事务边界，只保证轮末一定收尾）——仅作透明展示；
    - 「轮次边界」：``remove_db_session()`` 之后，是验收判据点——必须不是
      ``idle in transaction``（事故形态就是这一边界永不发生：线程阻塞在监听流上）。
    """
    from device_service.infrastructure.persistence._lab_resolver import resolve_lab_names
    from device_service.infrastructure.persistence.device_monitor_repository import (
        device_monitor_repository,
    )
    from device_service.infrastructure.persistence.device_repository import (
        device_repository,
    )

    print('\n' + '=' * 78)
    print('AFTER（修复后：真实仓储调用路径 + 轮次收尾）')
    print('=' * 78)
    in_round = []
    boundaries = []

    # ---- presence 轮 ----
    _reset_round()
    result = device_repository.list_devices(
        page=1, per_page=QueryConstants.UNLIMITED_PAGE_SIZE)
    items = result.get('items') or []
    in_round.append(_sample(
        f'presence 轮内：list_devices 后（{len(items)} 台设备，内含 resolve_lab_names）'))

    lab_ids = [item['lab_id'] for item in items if item.get('lab_id')]
    if lab_ids:
        names = resolve_lab_names(lab_ids)
        in_round.append(_sample(
            f'presence 轮内：单独 resolve_lab_names({len(lab_ids)} 个 lab) 后'))
        print(f'    resolve_lab_names -> {names}')
    remove_db_session()
    boundaries.append(_sample('presence 轮次边界：remove_db_session() 后'))

    # ---- monitor 轮 ----
    _reset_round()
    rules = device_monitor_repository.list_enabled_alarm_rules()
    print(f'    list_enabled_alarm_rules -> {len(rules)} 条启用规则')
    in_round.append(_sample('monitor 轮内：list_enabled_alarm_rules 后'))
    remove_db_session()
    boundaries.append(_sample('monitor 轮次边界：remove_db_session() 后'))

    print('\n-- 轮内采样（事务开在轮内，由轮次收尾释放；非验收判据点）--')
    for pair in in_round:
        _print_sample(*pair, judged=False)
    print('\n-- 轮次边界采样（验收判据点：不得 idle in transaction）--')
    for pair in boundaries:
        _print_sample(*pair)

    return boundaries


def main():
    parser = argparse.ArgumentParser(description='INT-2590 后台线程只读事务探针')
    parser.add_argument('--legacy', action='store_true', help='只跑 before（修复前形态）')
    parser.add_argument('--fixed', action='store_true', help='只跑 after（修复后路径）')
    args = parser.parse_args()
    run_before = args.legacy or not args.fixed
    run_after = args.fixed or not args.legacy

    print(f'DSN = {DSN.rsplit("@", 1)[-1]}')  # 不打印口令
    init_db(pool_size=2)
    _install_pid_recorder()

    try:
        if run_before:
            run_legacy_round()
        if run_after:
            results = run_fixed_round()
            bad = [pair for pair in results
                   if any(row[1] == 'idle in transaction' for row in pair[1])]
            print('\n' + '=' * 78)
            print('AFTER 判定（轮次边界）：' + (
                'FAIL — 轮次结束后仍存在 idle in transaction'
                if bad else 'PASS — 每轮结束后均无 idle in transaction'))
            print('=' * 78)
            return 1 if bad else 0
        return 0
    finally:
        remove_db_session()
        engine = get_engine()
        if engine is not None:
            engine.dispose()
        _SAMPLER.dispose()


if __name__ == '__main__':
    sys.exit(main())
