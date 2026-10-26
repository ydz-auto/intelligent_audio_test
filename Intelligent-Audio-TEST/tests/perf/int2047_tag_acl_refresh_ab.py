# -*- coding: utf-8 -*-
"""INT-2047 取证脚本：标签快照「TTL 过期刷新」改造前后 A/B（宿主进程内，只读）。

不起任何服务：同一进程里同时加载
- 旧实现：V9.7.31 主 clone 的 ``audio_service/infrastructure/acl/tag_acl_repository.py``
  （= 常驻宿主 audio_service 正在跑的版本，TTL 到期由第一个到达的请求线程
  自己同步打上游，其余等待者最多阻塞 5 s）；
- 新实现：本 worktree 的同一文件（请求线程只读快照，刷新交给后台 daemon 线程）。
两者共用同一份 docker task_service（宿主映射 gRPC 端口，默认 127.0.0.1:53061）
与同一份真实标签表，逐 ID 比对解析结果，再各跑一轮跨 TTL 周期的连续请求。

用法（仓库根目录）::

    python tests/perf/int2047_tag_acl_refresh_ab.py
    python tests/perf/int2047_tag_acl_refresh_ab.py --delay 3 --old-path <其他 clone>

``--delay`` 给上游 ListTags 注入固定时延，用来复现线上刷新 281 ms – 29.5 s
的尾部分布；不传则量真实 docker task_service。
"""
import argparse
import importlib.util
import os
import statistics
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_OLD_PATH = os.path.join(
    r'D:\00_code\V9.7.31\Intelligent-Audio-TEST',
    'audio_service', 'infrastructure', 'acl', 'tag_acl_repository.py')


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _DelayStub:
    """在真实 stub 前面加固定时延，模拟慢上游。"""

    def __init__(self, inner, delay):
        self._inner = inner
        self._delay = delay

    def ListTags(self, req, timeout=None):
        time.sleep(self._delay)
        return self._inner.ListTags(req, timeout=timeout)


def _percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * pct)))
    return ordered[idx]


def _ms(seconds):
    return round(seconds * 1000.0, 1)


def _expire(module, ttl):
    with module._COND:
        module._SNAPSHOT_AT = module._SNAPSHOT_AT - (ttl + 1)


def _warm(module, repo, ids, is_new):
    if is_new:
        # 宿主机 → docker task_service 首连实测可到 10 s 以上，等后台预热重试落地
        module.start_tag_acl_warmup()
        module.wait_tag_acl_refresh_idle(timeout=120)
    else:
        repo.get_tag_id_to_name_map(ids)     # 旧实现首轮就同步拉一次


def _run_sequence(module, repo, ids, is_new, n, ttl, expire_at, delay, label):
    """连续 n 次请求，在指定下标前把快照推到 TTL 之外（模拟跨 TTL 周期）。"""
    module.reset_tag_acl_cache()
    _warm(module, repo, ids, is_new)
    if is_new:
        module.wait_tag_acl_refresh_idle(timeout=30)

    samples = []
    expiry_samples = []
    for i in range(n):
        if i in expire_at:
            _expire(module, ttl)
        t0 = time.perf_counter()
        resolved = repo.get_tag_id_to_name_map(ids)
        cost = time.perf_counter() - t0
        samples.append(cost)
        if i in expire_at:
            expiry_samples.append(cost)
        if is_new:
            # 后台刷新落地再进下一次（模拟「请求之间」而不是「请求内部」的等待），
            # 让每轮 TTL 边界都是干净的一次过期。
            module.wait_tag_acl_refresh_idle(timeout=60)
        assert resolved, f'{label}: 解析结果为空'
    return {
        'samples': samples,
        'expiry_samples': expiry_samples,
        'stats': module.get_tag_acl_cache_stats(),
        'resolved': resolved,
    }


def _burst(module, repo, ids, threads, delay):
    """上游慢 delay 秒时，并发 threads 个请求侧解析：量请求侧耗时。"""
    module.reset_tag_acl_cache()
    _warm(module, repo, ids, True)
    module.wait_tag_acl_refresh_idle(timeout=30)
    _expire(module, module.tag_cache_ttl_seconds())

    barrier = threading.Barrier(threads)
    costs = []
    lock = threading.Lock()
    errors = []

    def worker():
        try:
            barrier.wait(timeout=30)
            t0 = time.perf_counter()
            repo.get_tag_id_to_name_map(ids)
            cost = time.perf_counter() - t0
            with lock:
                costs.append(cost)
        except Exception as exc:      # pragma: no cover - 仅用于定位
            with lock:
                errors.append(exc)

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join(timeout=60)
    module.wait_tag_acl_refresh_idle(timeout=60)
    return costs, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-path', default=DEFAULT_OLD_PATH)
    parser.add_argument('--delay', type=float, default=0.0,
                        help='给上游 ListTags 注入固定时延（秒），0 = 真实上游')
    parser.add_argument('--requests', type=int, default=40)
    parser.add_argument('--ttl', type=int, default=3)
    parser.add_argument('--threads', type=int, default=20)
    args = parser.parse_args()

    os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
    os.environ.setdefault('OSS_ACCESS_KEY', 'unused')
    os.environ.setdefault('OSS_SECRET_KEY', 'unused')
    os.environ.setdefault('OSS_ENDPOINT', 'http://127.0.0.1:9')
    os.environ.setdefault('TASK_SERVICE_HOST', '127.0.0.1')
    os.environ.setdefault('TASK_SERVICE_GRPC_PORT', '53061')

    from shared.infrastructure.config import BaseConfig
    BaseConfig.AUDIO_TAG_ACL_CACHE_TTL_SECONDS = args.ttl
    BaseConfig.AUDIO_TAG_ACL_NEGATIVE_CACHE_SECONDS = 0
    BaseConfig.AUDIO_TAG_ACL_REFRESH_TIMEOUT_SECONDS = 2.0
    BaseConfig.AUDIO_TAG_ACL_REFRESH_AHEAD_RATIO = 1.0    # 先关预热，让过期边界可复现
    BaseConfig.AUDIO_TAG_ACL_REFRESH_BACKOFF_SECONDS = 1.0
    BaseConfig.AUDIO_TAG_ACL_WARMUP_ENABLED = True

    new_mod = _load_module(
        os.path.join(REPO_ROOT, 'audio_service', 'infrastructure', 'acl',
                     'tag_acl_repository.py'),
        'int2047_new_tag_acl')
    old_mod = _load_module(args.old_path, 'int2047_old_tag_acl')

    import shared.clients.grpc_clients as grpc_clients
    real_factory = grpc_clients.get_tag_config_service_stub
    if args.delay > 0:
        grpc_clients.get_tag_config_service_stub = (
            lambda: _DelayStub(real_factory(), args.delay))

    new_repo = new_mod.TagAclRepository()
    old_repo = old_mod.TagAclRepository()

    # 真实标签表：用新实现预热一次拿全量 id
    new_mod.start_tag_acl_warmup()
    new_mod.wait_tag_acl_refresh_idle(timeout=180)
    with new_mod._COND:
        all_ids = sorted(new_mod._SNAPSHOT.keys())
    if not all_ids:
        print('FATAL: 上游没有返回任何标签（检查 task_service gRPC 端口/连通性）')
        return 1
    ids = all_ids[:20]

    expire_at = {args.requests // 3, (2 * args.requests) // 3}
    common = dict(ids=ids, n=args.requests, ttl=args.ttl,
                  expire_at=expire_at, delay=args.delay)

    print(f'# INT-2047 A/B  delay={args.delay}s ttl={args.ttl}s '
          f'requests={args.requests} tags={len(all_ids)} sample_ids={len(ids)}')
    old_res = _run_sequence(old_mod, old_repo, is_new=False, label='old', **common)
    new_res = _run_sequence(new_mod, new_repo, is_new=True, label='new', **common)

    def _line(name, res):
        s = res['samples']
        exp = res['expiry_samples']
        stats = res['stats']
        print(f'{name}: p50={_ms(statistics.median(s))}ms '
              f'p95={_ms(_percentile(s, 0.95))}ms max={_ms(max(s))}ms '
              f'expiry={[_ms(x) for x in exp]}ms '
              f'over1000ms={sum(1 for x in s if x > 1.0)} '
              f'refresh_ok={stats.get("refresh_ok")} '
              f'refresh_fail={stats.get("refresh_fail")} '
              f'degraded={stats.get("degraded")} '
              f'refresh_scheduled={stats.get("refresh_scheduled", "-")} '
              f'request_stale={stats.get("request_stale", "-")}')

    _line('old', old_res)
    _line('new', new_res)

    same = old_res['resolved'] == new_res['resolved']
    print(f'resolve_equal={same} items={len(new_res["resolved"])}')

    costs, errors = _burst(new_mod, new_repo, ids, args.threads, args.delay)
    if errors:
        print(f'burst_errors={errors[:3]}')
    print(f'new burst threads={args.threads} '
          f'p50={_ms(statistics.median(costs))}ms '
          f'p95={_ms(_percentile(costs, 0.95))}ms max={_ms(max(costs))}ms '
          f'over50ms={sum(1 for x in costs if x > 0.05)} '
          f'upstream_delay={args.delay}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
