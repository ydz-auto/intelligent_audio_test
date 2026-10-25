# -*- coding: utf-8 -*-
"""INT-1572 返工三轮（终审 P2）：操作人身份跨线程透传。

背景：报告取数从 `ListTestCases`（无可见性过滤）换成 `GetTestCaseDetail`（按
操作人过滤）后，身份必须一路带到底——task_service 按出站 metadata 的
`x-user-id` 判可见性，缺身份时 PRIVATE 用例一律按 404 返回（owner 自己也看不到，
且被记成「用例不存在」而非「查询不完整」）。

contextvars 不跨线程传播，本测试锁定共享助手的透传 / 复原语义，以及报告生成
线程池提交时确实带上发起请求的操作人身份。
"""
import os
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import (
    capture_identity,
    get_current_user_id,
    get_current_user_is_admin,
    run_with_identity,
    set_current_user_id,
    set_current_user_is_admin,
)


@pytest.fixture(autouse=True)
def _reset_identity():
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _run_in_thread(identity, job=None):
    """在线程池风格的工作线程里执行 job，返回线程内观察到的身份。"""
    obs = {}

    def _job():
        if job is not None:
            job()
        obs['seen'] = (get_current_user_id(), get_current_user_is_admin())

    t = threading.Thread(target=run_with_identity, args=(identity, _job))
    t.start()
    t.join(timeout=10)
    assert not t.is_alive()
    return obs


class TestRunWithIdentity:

    def test_carries_identity_into_worker_thread(self):
        set_current_user_id(101)
        set_current_user_is_admin(True)
        identity = capture_identity()

        obs = _run_in_thread(identity)

        assert obs['seen'] == (101, True)
        # 提交线程上下文不受影响
        assert get_current_user_id() == 101

    def test_none_identity_runs_as_unauthenticated(self):
        obs = _run_in_thread(None)

        assert obs['seen'] == (None, False)

    def test_restores_previous_context_after_task(self):
        """线程池线程复用：任务结束必须复原，不能把本次请求的身份留给下一个。"""
        observed = []

        def _job():
            set_current_user_id(5)  # 模拟该线程上残留的上一次任务身份
            run_with_identity((101, False), lambda: None)
            observed.append(get_current_user_id())

        t = threading.Thread(target=_job)
        t.start()
        t.join(timeout=10)
        assert observed == [5]


class TestGenerationSubmitCarriesIdentity:

    def test_submit_generation_propagates_identity(self):
        import report_service.application.services.report_task_generator as gen_mod

        done = threading.Event()
        seen = {}

        def _fake_async(task_id, name, description, lock):
            seen['uid'] = get_current_user_id()
            seen['admin'] = get_current_user_is_admin()
            done.set()

        old = gen_mod.ReportTaskGenerator._generate_task_report_async
        gen_mod.ReportTaskGenerator._generate_task_report_async = staticmethod(_fake_async)
        try:
            set_current_user_id(101)
            set_current_user_is_admin(True)
            submitted = gen_mod._submit_generation(4242, None, None, None, 'test')
            assert submitted is True
            assert done.wait(10), '生成任务未在 10s 内执行'
        finally:
            gen_mod.ReportTaskGenerator._generate_task_report_async = old
            gen_mod._generation_tracker = gen_mod.GenerationTracker()

        assert seen == {'uid': 101, 'admin': True}

    def test_submit_secondary_generation_propagates_identity(self):
        import report_service.application.services.report_compare_generator as cmp_mod

        done = threading.Event()
        seen = {}

        def _fake_secondary(report_ids, description, report_key):
            seen['uid'] = get_current_user_id()
            seen['ids'] = list(report_ids)
            done.set()

        old = cmp_mod.ReportCompareGenerator._secondary_compare_async
        cmp_mod.ReportCompareGenerator._secondary_compare_async = staticmethod(_fake_secondary)
        try:
            set_current_user_id(202)
            submitted = cmp_mod._submit_secondary_generation([11, 12], (11, 12), 'test')
            assert submitted is True
            assert done.wait(10), '二次对比任务未在 10s 内执行'
        finally:
            cmp_mod.ReportCompareGenerator._secondary_compare_async = old
            cmp_mod._secondary_generation_tracker = cmp_mod.GenerationTracker()
            cmp_mod._generating_secondary.clear()

        assert seen == {'uid': 202, 'ids': [11, 12]}
