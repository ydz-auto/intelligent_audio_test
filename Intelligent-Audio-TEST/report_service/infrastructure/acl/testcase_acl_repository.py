# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService ACL 仓储 — gRPC 实现。

INT-1572：按 ID 取用例改为逐 id 调 GetTestCaseDetail（受限并发 + 单条超时容错）。
原实现用 ListTestCases(per_page=1000) 全表拉取后按 id 过滤：docker 栈上单次
20~35s（列表项逐条向宿主 audio / evaluation 取数），且耗时与所需 id 数无关——
报告对比 / case-averages 一次请求内多次调用该 ACL，直接撞上网关 60s 截止。
TestCaseConfigService 没有按 ID 批量查询的 RPC，故按 id 取详情；耗时只与
id 数相关，缺失/超时的单条由调用方按 id 兜底，不拖垮整批。取到的用例进
TTL 缓存，同一报告请求内多次取同一批用例只付一次代价。

INT-1572 返工（INT-1482 复测）补两点：
- 结果带完整性口径（missing_ids / incomplete_ids），整批截止时调用方不再把
  部分用例算出的均值当完整数据返回；
- 未取到的 id 进短 TTL 负缓存，同一请求内的第二次取数不再重复支付整批截止。
INT-1572 返工二轮（INT-1482 二次复测）：
- 固定 8 路并发是放大器而不是拐点。宿主 audio_service 对并发取数是串行的
  （单路 0.12~0.4s，8 路并发时单条被拖到 10s 以上），固定并发一遇到宿主排队就把
  整批打成超时；单条 10s 超时又会在「冷启动 / 宿主排队」窗口把在途请求全部取消，
  下游永远热不起来，形成死亡螺旋（实测 138 用例 0/138、50 用例 0/50）。
  改为自适应并发（AIMD：超时降并发并放大单条超时，连续成功再逐步升），并且在
  超时的 id 上重试一轮，先把下游焐热。
- 整批截止不再固定 40s，改为「本次报告请求剩余预算 - 后续阶段预留」
  （见 report_service/domain/request_budget.py），避免 ACL 独占预算把结果段
  顶过网关 60s。
INT-1572 返工三轮（终审 P2/P3）：
- 取数走共享线程池，contextvars 不跨线程传播，worker 里没有操作人身份 →
  出站 GetTestCaseDetail 不带 x-user-id → task_service 把 PRIVATE 用例按 404
  返回（owner 自己也看不到，且被当成「用例不存在」而非「取数不完整」）。
  现在在调用线程捕获身份（capture_identity）并随任务带进 worker
  （run_with_identity），出站 metadata 与同步调用口径一致。
- 缓存按可见性分键：visibility='shared' 的载荷对所有查看者一致，按 id 全局共享；
  private / 未知可见性按 (user_id, is_admin) 分键，避免 A 查到的私有用例在 TTL
  内供给 B；负缓存同样按身份分键（404 可能是「私有无权限」，不能跨用户复用）。
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import FIRST_COMPLETED
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as _wait_futures
from typing import Dict, Optional

from report_service.config.config import Config
from report_service.domain.dto import TestCaseDTO, TestCaseLookupResult
from report_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigAclRepository,
)
from report_service.domain.request_budget import remaining_seconds
from shared.infrastructure.user_context import capture_identity, run_with_identity
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)

# 按 id 取用例详情的共享线程池（跨请求复用；容量见 Config.TESTCASE_ACL_LOOKUP_MAX_WORKERS）
_lookup_executor = ThreadPoolExecutor(
    max_workers=Config.TESTCASE_ACL_LOOKUP_MAX_WORKERS,
    thread_name_prefix='testcase_acl_lookup',
)


class _AdaptiveConcurrency:
    """跨请求共享的自适应并发许可（AIMD）。

    宿主 audio_service 对并发取数是串行的：并发越高，单条越慢。固定 8 路在
    排队窗口会把单条拖过超时线，进而整批失败。这里在「超时」时减半并发、
    在「连续成功」时逐个放大，把并发稳定在本次宿主负载能承受的档位。

    进程级单例：一次报告请求内的多次取数、相邻请求都复用同一份负载判断。
    """

    def __init__(self, initial: int, minimum: int, maximum: int):
        self._lock = threading.Lock()
        self._min = max(int(minimum), 1)
        self._max = max(int(maximum), self._min)
        self._permits = min(max(int(initial), self._min), self._max)
        self._ok_streak = 0
        # 单条超时放大系数：超时时上调，连续成功时回落（冷启动 / 宿主排队时
        # 在途请求被 10s 掐断是死亡螺旋的起点，宁可慢一点也要让请求跑完）
        self._timeout_scale = 1.0

    @property
    def permits(self) -> int:
        with self._lock:
            return self._permits

    @property
    def timeout_scale(self) -> float:
        with self._lock:
            return self._timeout_scale

    def on_success(self) -> None:
        with self._lock:
            self._ok_streak += 1
            self._timeout_scale = max(1.0, self._timeout_scale * 0.9)
            if self._ok_streak >= self._permits and self._permits < self._max:
                self._permits += 1
                self._ok_streak = 0

    def on_timeout(self) -> None:
        with self._lock:
            self._permits = max(self._min, self._permits // 2)
            self._ok_streak = 0
            self._timeout_scale = min(self._timeout_scale * 1.5, Config.TESTCASE_ACL_LOOKUP_MAX_TIMEOUT_SCALE)

    def reset(self) -> None:
        with self._lock:
            self._permits = min(max(Config.TESTCASE_ACL_LOOKUP_INITIAL_WORKERS, self._min), self._max)
            self._ok_streak = 0
            self._timeout_scale = 1.0


_governor = _AdaptiveConcurrency(
    Config.TESTCASE_ACL_LOOKUP_INITIAL_WORKERS,
    Config.TESTCASE_ACL_LOOKUP_MIN_WORKERS,
    Config.TESTCASE_ACL_LOOKUP_MAX_WORKERS,
)

# 命中缓存。一次报告请求会对同一批用例多次取数（统计链路 2 次、报告生成更多次），
# 缓存把重复取数压成一次；只存查到的用例，缺失/软删不缓存。
# 读写都做深拷贝：载荷里的 config 会被下游按引用持有，避免调用方原地修改污染缓存。
#
# 键按可见性分两类（INT-1572 返工三轮）：
# - ('s', tc_id)：visibility='shared' 的载荷，对所有查看者一致，可全局共享；
# - ('u', user_id, is_admin, tc_id)：private（以及载荷未带 visibility 的旧口径），
#   只对取到它的操作人有效——否则 A 查过的私有用例会在 TTL 内供给 B，绕过可见性。
_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_cache_lock = threading.Lock()

# 负缓存：键为 ('u', user_id, is_admin, tc_id)，值 (过期时刻 monotonic, 是否「查询未完成」)
# ——整批截止 / 单条超时 / 用例不存在。同一报告请求内 ACL 会被调用多次（case-averages
# 统计链路 2 次），若首次整批截止，后续调用会再次按同一批 id 重查并再吃一个整批截止
# （实测 2×40s 直接越过网关 60s）。负缓存让这些 id 在短时间内不再重复查询；同时保留
# 「未完成」标记，使后续调用的 partial 口径不至于因为不再重试而变成「正常缺失」。
# 必须按身份分键：404 既可能是「用例不存在」也可能是「私有无权限」，跨用户复用会让
# 别人查不到的私有用例在 30s 内连 owner 也挡住。
_neg_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_neg_cache_lock = threading.Lock()


def _identity_key(user_id, is_admin) -> tuple:
    """负缓存 / 私有载荷缓存的用户维度键前缀。"""
    return ('u', user_id, bool(is_admin))


def _neg_cache_hit(tc_id: str, identity):
    """负缓存命中返回 (True, incomplete)，未命中返回 None。

    返回的 incomplete 表示该 id 上次是「查询没做完」而不是「用例不存在」。
    """
    ttl = Config.TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS
    if ttl <= 0:
        return None
    key = _identity_key(*identity) + (tc_id,)
    now = time.monotonic()
    with _neg_cache_lock:
        entry = _neg_cache.get(key)
        if entry is None:
            return None
        if now >= entry[0]:
            _neg_cache.pop(key, None)
            return None
        _neg_cache.move_to_end(key)
        return True, entry[1]


def _neg_cache_put_many(tc_ids, identity, incomplete: bool = False) -> None:
    """写入负缓存。

    「查询未完成」的缓存期比「用例不存在」短得多（Config.TESTCASE_ACL_INCOMPLETE_CACHE_TTL_SECONDS）：
    它只用来挡住同一次报告请求里紧跟着的第二次 ACL 调用，而不是让用户手动重试
    也拿不到数据（复测实测：上一轮没取全的 id 在 30s 内重试仍返回缺失）。
    """
    if incomplete:
        ttl = Config.TESTCASE_ACL_INCOMPLETE_CACHE_TTL_SECONDS
    else:
        ttl = Config.TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS
    if ttl <= 0 or not tc_ids:
        return
    expiry = time.monotonic() + ttl
    prefix = _identity_key(*identity)
    max_entries = max(int(Config.TESTCASE_ACL_CACHE_MAX_ENTRIES), 1)
    with _neg_cache_lock:
        for tc_id in tc_ids:
            key = prefix + (tc_id,)
            _neg_cache[key] = (expiry, incomplete)
            _neg_cache.move_to_end(key)
        while len(_neg_cache) > max_entries:
            _neg_cache.popitem(last=False)


def clear_caches() -> None:
    """清空正 / 负缓存并复位自适应并发（单测与需要强制重查的调用方使用）。"""
    with _cache_lock:
        _cache.clear()
    with _neg_cache_lock:
        _neg_cache.clear()
    _governor.reset()


def _cache_keys(tc_id: str, identity) -> tuple:
    """同一 id 在该操作人下的查找顺序：先全局共享键，再本人私有键。"""
    return (('s', tc_id), _identity_key(*identity) + (tc_id,))


def _cache_get(tc_id: str, identity) -> Optional[dict]:
    ttl = Config.TESTCASE_ACL_CACHE_TTL_SECONDS
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _cache_lock:
        for key in _cache_keys(tc_id, identity):
            entry = _cache.get(key)
            if entry is None:
                continue
            if now - entry[0] >= ttl:
                _cache.pop(key, None)
                continue
            _cache.move_to_end(key)
            return copy.deepcopy(entry[1])
        return None


def _cache_put(tc_id: str, payload: dict, identity) -> None:
    if Config.TESTCASE_ACL_CACHE_TTL_SECONDS <= 0:
        return
    # 只有显式 shared 的载荷可以跨用户复用；载荷未带 visibility（老版本服务）
    # 一律按私有处理，宁可少命中也不把私有用例供给他人。
    visibility = payload.get('visibility') if isinstance(payload, dict) else None
    if visibility == 'shared':
        key = ('s', tc_id)
    else:
        key = _identity_key(*identity) + (tc_id,)
    with _cache_lock:
        _cache[key] = (time.monotonic(), copy.deepcopy(payload))
        _cache.move_to_end(key)
        max_entries = max(int(Config.TESTCASE_ACL_CACHE_MAX_ENTRIES), 1)
        while len(_cache) > max_entries:
            _cache.popitem(last=False)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class TestCaseConfigAclRepositoryImpl(TestCaseConfigAclRepository):
    """task_service.TestCaseConfigService 跨域只读查询 gRPC 实现。"""

    def list_testcases_by_ids(self, test_case_ids) -> TestCaseLookupResult:
        """按 ID 取用例。

        软删 / 不存在 / 不可见的用例返回 404，按缺失处理（与原先列表口径一致：
        调用方按 id 兜底显示）。取数在预算内自适应调度（并发 AIMD + 单条超时放大
        + 超时重试），预算用尽时返回已取到的部分并告警——这些未完成的 id 进
        incomplete_ids，调用方据此判定「数据不完整」而不是当成缺失用例。

        预算来源：本次报告请求的剩余时限（report_budget，由 gRPC servicer 注入）
        减去后续阶段预留；没有请求上下文时（生成线程池 / 单测）用配置的固定值。
        """
        ordered_ids = list(dict.fromkeys(
            str(tid) for tid in test_case_ids or [] if tid is not None))
        if not ordered_ids:
            return TestCaseLookupResult(items={}, missing_ids=[], incomplete_ids=[])

        # 操作人身份在调用线程捕获：RPC 线程由 ServerUserContextInterceptor 写入，
        # 后台生成线程由 _submit_generation 透传。取数 worker 与缓存都按它分口径。
        identity = capture_identity()

        result_map: Dict[str, TestCaseDTO] = {}
        to_query = []
        missing_ids = []
        incomplete_ids = []
        for tc_id in ordered_ids:
            payload = _cache_get(tc_id, identity)
            if payload is not None:
                result_map[tc_id] = _attach(dict_to_dto(payload, TestCaseDTO), payload)
                continue
            neg = _neg_cache_hit(tc_id, identity)
            if neg is not None:
                # 刚查过且没取到（不存在 / 上一轮已超时）：本轮不再重复支付
                missing_ids.append(tc_id)
                if neg[1]:
                    incomplete_ids.append(tc_id)
            else:
                to_query.append(tc_id)
        if not to_query:
            return TestCaseLookupResult(
                items=result_map, missing_ids=missing_ids, incomplete_ids=incomplete_ids)

        budget = self._lookup_budget_seconds()
        deadline = time.monotonic() + budget
        new_missing_ids, timed_out_ids = self._fetch_adaptive(
            to_query, result_map, deadline, identity)

        incomplete_ids.extend(timed_out_ids)
        if incomplete_ids:
            logger.warning(
                "list_testcases_by_ids 未取全（预算 %.1fs）：取到 %d / 共 %d，"
                "未完成 %d 条（已标 partial，并发 %d）",
                budget, len(result_map), len(ordered_ids), len(incomplete_ids),
                _governor.permits,
            )

        # 负缓存：本轮没取到的 id 短期内不再重查，避免同一报告请求内的后续 ACL
        # 调用再吃一个整批截止（复测实测 2×40s 直接越过网关 60s）。「未完成」与
        # 「不存在」分开记：前者在后续调用里仍要报 partial。
        _neg_cache_put_many(new_missing_ids, identity, incomplete=False)
        _neg_cache_put_many(incomplete_ids, identity, incomplete=True)

        missing_ids.extend(new_missing_ids)
        missing_ids.extend(incomplete_ids)
        return TestCaseLookupResult(
            items=result_map,
            missing_ids=list(dict.fromkeys(missing_ids)),
            incomplete_ids=list(dict.fromkeys(incomplete_ids)),
        )

    @staticmethod
    def _lookup_budget_seconds() -> float:
        """本次取数可用的时间预算（秒）。

        优先用本次报告请求的剩余时限减预留（ACL 之后还要聚合结果、读结果文件、
        渲染响应，不能把网关的 60s 全吃掉）；没有请求上下文时用配置固定值。
        """
        cap = max(float(Config.TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS), 0.0)
        budget = remaining_seconds(
            reserve=Config.TESTCASE_ACL_LOOKUP_REQUEST_RESERVE_SECONDS)
        if budget is None:
            return cap
        return min(budget, cap) if cap > 0 else budget

    def _fetch_adaptive(self, to_query, result_map: Dict[str, TestCaseDTO],
                        deadline: float, identity):
        """在窗口内按自适应并发取详情，返回 (缺失 id, 未完成 id)。

        - 窗口大小 = _governor.permits，未完成一条就补一条（没有分波次的头阻塞）；
        - 单条超时 = 基础超时 × 超时放大系数，且不超过剩余预算；
        - 超时的 id 重排到队尾重试（最多 MAX_ATTEMPTS 次），让冷启动 / 宿主排队
          窗口里的在途请求跑完，一次超时不再等同「这条没戏」；
        - 每个任务带着调用线程的操作人身份进 worker（contextvars 不跨线程传播），
          出站 GetTestCaseDetail 才能带上 x-user-id，私有用例对 owner 才可见。
        """
        new_missing_ids = []
        incomplete_ids = []
        queue = deque(to_query)
        attempts: Dict[str, int] = {tc_id: 0 for tc_id in to_query}
        in_flight = {}
        max_attempts = max(int(Config.TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS), 1)
        base_timeout = max(float(Config.TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS), 0.1)

        try:
            while True:
                now = time.monotonic()
                remaining = deadline - now
                # 补满窗口
                while queue and len(in_flight) < _governor.permits and remaining > 0:
                    tc_id = queue.popleft()
                    item_timeout = min(base_timeout * _governor.timeout_scale, remaining)
                    future = _lookup_executor.submit(
                        run_with_identity, identity, self._fetch_detail,
                        tc_id, item_timeout)
                    in_flight[future] = tc_id
                    remaining = deadline - time.monotonic()
                if not in_flight:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                done, _ = _wait_futures(
                    list(in_flight), timeout=remaining, return_when=FIRST_COMPLETED)
                if not done:
                    break
                for future in done:
                    tc_id = in_flight.pop(future)
                    try:
                        payload = future.result()
                    except Exception as e:  # 单条失败不拖垮整批
                        attempts[tc_id] += 1
                        _governor.on_timeout()
                        if attempts[tc_id] < max_attempts and time.monotonic() < deadline:
                            logger.warning(
                                "GetTestCaseDetail 超时/失败 (tc_id=%s, 第 %d 次)，排队重试: %s",
                                tc_id, attempts[tc_id], e)
                            queue.append(tc_id)
                        else:
                            logger.warning("GetTestCaseDetail 失败 (tc_id=%s): %s", tc_id, e)
                            incomplete_ids.append(tc_id)
                        continue
                    if not isinstance(payload, dict):
                        # resp.success=false：软删 / 不存在 / 私有不可见，属正常缺失
                        new_missing_ids.append(tc_id)
                        _governor.on_success()
                        continue
                    _cache_put(tc_id, payload, identity)
                    result_map[tc_id] = _attach(dict_to_dto(payload, TestCaseDTO), payload)
                    _governor.on_success()
        finally:
            # 预算用尽仍在途 / 没排上的：查询没做完，不能当作「用例不存在」
            for future, tc_id in list(in_flight.items()):
                future.cancel()
                incomplete_ids.append(tc_id)
            incomplete_ids.extend(queue)
        return new_missing_ids, incomplete_ids

    @staticmethod
    def _fetch_detail(tc_id: str, timeout: Optional[float] = None) -> Optional[dict]:
        """取单条用例详情，返回载荷 dict；成功标记为 false 或载荷异常时返回 None。

        timeout 由调度器按剩余预算 / 当前负载给出，缺省用配置值。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_testcase_config_service_stub()
        resp = stub.GetTestCaseDetail(
            task_pb.GetTestCaseDetailRequest(tc_id=tc_id),
            timeout=timeout or Config.TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS,
        )
        if not resp.success:
            # 软删 / 不存在 / 私有不可见都会走到这里，按缺失处理
            logger.debug("GetTestCaseDetail 无结果 (tc_id=%s): %s", tc_id, resp.message)
            return None
        payload = _loads(resp.data, {})
        if not isinstance(payload, dict) or payload.get('id') is None:
            logger.warning("GetTestCaseDetail 载荷异常 (tc_id=%s)", tc_id)
            return None
        return payload
