# -*- coding: utf-8 -*-
"""INT-2256：E2EExecutor 单例跨用例状态污染回归

E2EExecutor 是进程级单例（E2EService.executor 懒加载唯一实例），gRPC 线程池
并发执行不同用例（同一任务不同实验室的路由行也并行）。修复前用例级状态挂在
实例属性上：UI 抓取降级标记不复位、音频本地路径只增不减、播放时间戳不回收，
连续/并发用例会互相继承。

修复后用例级状态按执行线程隔离（_CaseScopedState + _case_scope），用例结束即释放。
"""
import os
import threading
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager
from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor

_DEGRADE = {'device_name': 'd1', 'degrade_reason': 'hypium_missing'}

_ROUND_ARGS = dict(
    task_id='t1', tc_rel_id='tc1',
    data={'case_algorithm_params': None},
    case_config={'rounds': [{'round_number': 1, 'audios': [],
                             'evaluation': {'dimensions': []}}]},
    case_name='case-x', algorithm_type='voice_llm', test_case_id='c1',
    rounds=[{'round_number': 1, 'audios': []}],
    result_id=99, case_reference_params=None,
    round_idx=0, primary={'success': True},
    tagged_results=[{'success': True}],
    rounds_data=[], round_algo_params={},
)


def _host():
    """裸宿主：绕过 __init__ 的重依赖，只装执行链路与轮次写入所需件"""
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._log = MagicMock()
    ex._validate_and_get_data = MagicMock(
        return_value={'success': True, 'data': {'case_name': 'case-x'}})
    ex._aggregator = MagicMock()
    ex._task_data_repo = MagicMock()
    ex._device_repo = MagicMock()
    ex._playback_repo = MagicMock()
    ex._thread_ctx = type('ThreadCtx', (), {})()
    ex._eval_submit_failures = []
    ex._evaluate_result = MagicMock()
    return ex


def _degraded_via_manager(ex):
    """按 preparation_mixin 的读法（经 device manager）取本用例降级状态"""
    mgr = object.__new__(E2EDeviceManager)
    mgr._executor = ex
    return mgr.get_ui_capture_degraded()


class TestSequentialCases:

    def test_second_case_does_not_inherit_degrade(self):
        """用例 A 降级后，用例 B 不得继承 A 的降级标记与音频本地路径"""
        ex = _host()
        observed = {}

        def fake_rounds(task_id, tc_rel_id, data, device_id=None, device_ids=None):
            # 用例内 initialize 阶段（E2EDeviceManager.initialize_devices）才写降级
            if task_id == 101:
                ex.set_ui_capture_degraded([_DEGRADE], task_id=task_id, test_case_id='c1')
                ex._audio_local_paths.update({'a1': {'original': '/tmp/a1.wav'}})
            observed[task_id] = {
                'degraded': _degraded_via_manager(ex),
                'note': ex._ui_capture_degraded_note,
                'audio': dict(ex._audio_local_paths),
            }
            # 本轮结果记录：第二次执行不得出现 ui_capture 留痕
            observed[task_id]['round'] = ex._build_and_submit_round_data(**_ROUND_ARGS)
            return True

        ex._execute_e2e_with_rounds = fake_rounds

        assert ex.execute_e2e_case(101, 'tc1') is True
        assert ex.execute_e2e_case(102, 'tc2') is True

        assert observed[101]['degraded'] == [_DEGRADE]
        assert observed[101]['note']['status'] == 'skipped'
        assert observed[101]['round']['ui_capture']['degrade_reason'] == 'hypium_missing'
        assert observed[101]['audio'] == {'a1': {'original': '/tmp/a1.wav'}}

        # 第二次：零继承
        assert observed[102]['degraded'] is None
        assert observed[102]['note'] is None
        assert observed[102]['audio'] == {}
        assert 'ui_capture' not in observed[102]['round']

    def test_case_state_released_after_case(self):
        """用例收尾释放用例级状态（音频路径不随进程单调增长、播放账本不残留）"""
        ex = _host()

        def fake_rounds(task_id, tc_rel_id, data, device_id=None, device_ids=None):
            ex.set_ui_capture_degraded([_DEGRADE], task_id=task_id)
            ex._audio_local_paths.update({'a1': {'original': '/tmp/a1.wav'}})
            ex._playback_timestamps.setdefault(task_id, {})['audio_play_times'] = [1]
            return True

        ex._execute_e2e_with_rounds = fake_rounds
        assert ex.execute_e2e_case(301, 'tc1') is True

        assert ex._ui_capture_degraded is None
        assert ex._ui_capture_degraded_note is None
        assert ex._audio_local_paths == {}
        assert ex._playback_timestamps == {}

    def test_case_state_released_on_failure(self):
        """用例异常退出同样释放（finally 收口，残留零）"""
        ex = _host()

        def boom(task_id, tc_rel_id, data, device_id=None, device_ids=None):
            ex.set_ui_capture_degraded([_DEGRADE], task_id=task_id)
            raise RuntimeError('case blew up')

        ex._execute_e2e_with_rounds = boom
        try:
            ex.execute_e2e_case(302, 'tc1')
        except RuntimeError:
            pass
        else:  # pragma: no cover - 执行链异常应上抛给 E2EService 收口
            raise AssertionError('expected RuntimeError')

        assert ex._ui_capture_degraded is None
        assert ex._audio_local_paths == {}


class TestConcurrentCases:

    def test_concurrent_cases_keep_their_own_state(self):
        """并发的两个 task_id 各自降级标记/音频路径互不串"""
        ex = _host()
        barrier = threading.Barrier(2)
        results = {}
        lock = threading.Lock()
        errors = []

        def fake_rounds(task_id, tc_rel_id, data, device_id=None, device_ids=None):
            # 各自 initialize：每用例降级自己的设备
            ex.set_ui_capture_degraded(
                [{'device_name': f'd{task_id}', 'degrade_reason': 'hypium_missing'}],
                task_id=task_id)
            ex._audio_local_paths.update({f'a{task_id}': {'original': f'/tmp/a{task_id}.wav'}})
            ex._playback_timestamps.setdefault(task_id, {})['audio_play_times'] = [task_id]
            # 两用例都已写入后再各自读取：共享实例属性时这里必然串味
            barrier.wait(timeout=10)
            with lock:
                results[task_id] = {
                    'degraded': [d['device_name'] for d in (_degraded_via_manager(ex) or [])],
                    'note_devices': (ex._ui_capture_degraded_note or {}).get('devices'),
                    'audio': sorted(ex._audio_local_paths),
                    'timestamps': sorted(ex._playback_timestamps),
                    'round': ex._build_and_submit_round_data(**_ROUND_ARGS),
                }
            return True

        ex._execute_e2e_with_rounds = fake_rounds

        def run(task_id):
            try:
                ex.execute_e2e_case(task_id, f'tc{task_id}')
            except Exception as e:  # pragma: no cover - 线程内异常上报
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=run, args=(tid,)) for tid in (201, 202)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors
        assert set(results) == {201, 202}
        for task_id in (201, 202):
            own = results[task_id]
            assert own['degraded'] == [f'd{task_id}']
            assert own['note_devices'] == [f'd{task_id}']
            assert own['audio'] == [f'a{task_id}']
            assert own['timestamps'] == [task_id]
            assert own['round']['ui_capture']['devices'] == [f'd{task_id}']

    def test_manager_reads_are_thread_scoped(self):
        """device manager 读降级状态只在当前线程可见（prepare 与 initialize 同线程）"""
        ex = _host()
        mgr = object.__new__(E2EDeviceManager)
        mgr._executor = ex
        seen = {}

        def worker(task_id):
            ex.set_ui_capture_degraded(
                [{'device_name': f'd{task_id}', 'degrade_reason': 'hypium_missing'}],
                task_id=task_id)
            seen[task_id] = mgr.get_ui_capture_degraded()

        threads = [threading.Thread(target=worker, args=(tid,)) for tid in (401, 402)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert [d['device_name'] for d in seen[401]] == ['d401']
        assert [d['device_name'] for d in seen[402]] == ['d402']
        assert mgr.get_ui_capture_degraded() is None  # 主线程从未写过


class TestCaseScopedAttributeCompat:

    def test_bare_new_host_supports_assign_and_delete(self):
        """__new__ 裸宿主（无 __init__）读写/删除用例级属性照常可用"""
        ex = E2EExecutor.__new__(E2EExecutor)
        assert ex._ui_capture_degraded is None
        assert ex._audio_local_paths == {}

        ex._ui_capture_degraded = [_DEGRADE]
        ex._audio_local_paths = {'a1': {'original': '/tmp/a1.wav'}}
        assert ex._ui_capture_degraded == [_DEGRADE]
        assert ex._audio_local_paths == {'a1': {'original': '/tmp/a1.wav'}}

        del ex._ui_capture_degraded_note
        assert ex._ui_capture_degraded_note is None

        # 删除后的可变状态是全新对象，不与上一份共享
        paths = ex._audio_local_paths
        del ex._audio_local_paths
        assert ex._audio_local_paths == {}
        assert ex._audio_local_paths is not paths

    def test_round_marker_reads_scoped_note(self):
        """轮次留痕读的是当前用例上下文里的 note（非上一次用例的残留）"""
        ex = _host()
        note = {'status': 'skipped', 'skip_reason': 'environment_excluded',
                'degrade_reason': 'hypium_missing', 'devices': ['d9']}
        ex._ui_capture_degraded_note = note
        round_data = ex._build_and_submit_round_data(**_ROUND_ARGS)
        assert round_data['ui_capture'] == note

        ex._reset_case_state()
        round_data = ex._build_and_submit_round_data(**_ROUND_ARGS)
        assert 'ui_capture' not in round_data
