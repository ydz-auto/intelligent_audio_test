# -*- coding: utf-8 -*-
"""INT-38 验收补充：api 线性链 _run_single_api → _evaluate_result 参数传递单测。

真实链路回归（Postgres + gRPC 替身）用 reference_params 为空的用例覆盖了「任务收敛
completed」；本文件补齐其未覆盖的两点（对应 INT-38 交付评论的建议测试点 2 / 3）：

- 测试点 2：首轮配置 reference_params_path 时 _load_case_config 注入的 list 形态
  reference_params（RefParamsStorageAdapter.load_reference_params 返回 List[Dict]）
  经调用点传入 _evaluate_result，基类入口转成 {code: value} dict 进入评估参数。
- 测试点 3：用例无 reference_params 时调用点以空 dict 兜底，评估照常提交、无
  TypeError（原缺陷：必填参数缺失 → TypeError 被 execute_api_case 兜底 except
  吞掉 → 用例悬挂 exec=completed/eval=pending → 任务永久卡 running）。

隔离方式：APIExecutor 以 __new__ 跳过 __init__（不构建并发/任务执行器协作者），
task_runner / result_processor 用 MagicMock 替身；_evaluate_result 走真实基类实现
（ACL 注入点与 _log 替换为记录型 mock），因此同时验证「必填参数已传」与「基类
list→dict 转换、评估参数组装」两端；末尾测试用真实签名 bind 直接复现原缺陷的
失败面（缺参即 TypeError）。
"""
import inspect
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_test_service.core.api_executor as api_executor_module
from api_test_service.core.api_executor import APIExecutor
from shared.infrastructure.base_executor import BaseExecutor


def _make_executor(monkeypatch):
    """构建跳过 __init__ 的 APIExecutor，协作者全部替身化，返回 (executor, algo_acl, task_acl)。"""
    executor = APIExecutor.__new__(APIExecutor)

    runner = MagicMock(name='task_runner')
    runner.setup_endpoints.return_value = (['/api/create_task'], 'http://select', 'http://release')
    runner.wait_for_completion.return_value = (0.1, True, None)
    runner.get_final_result.return_value = {'data': {'answer': '今天天气怎么样'}}
    runner.extract_final_result.return_value = ({'answer': '今天天气怎么样'}, 12)
    executor._task_runner = runner

    processor = MagicMock(name='result_processor')
    processor.create_test_result.return_value = 'result-1'
    executor._result_processor = processor

    algo_acl = MagicMock(name='algo_acl')
    algo_acl.extract_case_all_params.return_value = {'evaluation': {}}
    task_acl = MagicMock(name='task_data_acl')

    monkeypatch.setattr(executor, '_get_algorithm_acl', lambda: algo_acl)
    monkeypatch.setattr(executor, '_get_task_data_acl', lambda: task_acl)
    monkeypatch.setattr(executor, '_log', MagicMock())
    monkeypatch.setattr(executor, '_log_case_result', MagicMock())
    # _log_single_api_result 直接用模块级 _algo_acl，同样替换以保持无网络
    monkeypatch.setattr(api_executor_module, '_algo_acl', algo_acl)
    return executor, algo_acl, task_acl


def _run_single_api(executor, case_config):
    executor._run_single_api(
        task_id='task-1', tc_rel_id='tc-rel-1', test_case_id='case-1',
        case_name='单测用例', algorithm_type='translation',
        api_config=SimpleNamespace(id='api-1'), api_specific_config={},
        audio=SimpleNamespace(id='audio-1'), total_audio_duration=1.0,
        case_config=case_config, case_algorithm_params={'k': 'v'},
    )


class TestInt38RunSingleApiEvaluateParams:

    def test_reference_params_list_converted_and_passed(self, monkeypatch):
        """建议测试点 2：list 形态 reference_params 传入基类并转为 {code: value}。"""
        executor, algo_acl, task_acl = _make_executor(monkeypatch)
        case_config = {
            'reference_params': [
                {'code': 'standard_text', 'value': '今天天气怎么样'},
                {'code': 'speaker', 'value': '女声'},
            ],
        }
        _run_single_api(executor, case_config)

        # 评估提交恰好一次（原缺陷下 TypeError 在提交前抛出，永远到不了这里）
        assert task_acl.submit_evaluate_case.call_count == 1
        kwargs = task_acl.submit_evaluate_case.call_args.kwargs
        assert kwargs['task_id'] == 'task-1'
        assert kwargs['result_id'] == 'result-1'
        assert kwargs['test_case_id'] == 'case-1'
        assert kwargs['algorithm_result'] == {'answer': '今天天气怎么样'}
        assert kwargs['test_type'] == 'api'

        # extract_case_all_params 共被调两次：#1 来自真实 _evaluate_result
        # （list 已在基类入口转为 {code: value}），#2 来自 _log_single_api_result
        # （日志路径，原始 list，本卡未改动）
        full_case_params = algo_acl.extract_case_all_params.call_args_list[0].args[0]
        assert full_case_params['reference_params'] == {
            'standard_text': '今天天气怎么样', 'speaker': '女声'}

    def test_missing_reference_params_falls_back_to_empty_dict(self, monkeypatch):
        """建议测试点 3：用例无 reference_params 时空 dict 兜底，评估照常提交。"""
        executor, algo_acl, task_acl = _make_executor(monkeypatch)
        _run_single_api(executor, {'algorithm_params': {'k': 'v'}})

        assert task_acl.submit_evaluate_case.call_count == 1
        kwargs = task_acl.submit_evaluate_case.call_args.kwargs
        assert kwargs['task_id'] == 'task-1'
        assert kwargs['result_id'] == 'result-1'
        assert kwargs['test_type'] == 'api'

        full_case_params = algo_acl.extract_case_all_params.call_args[0][0]
        assert full_case_params['reference_params'] == {}

    def test_none_case_config_falls_back_to_empty_dict(self, monkeypatch):
        """调用点 case_config=None 防御分支：不抛 TypeError，评估照常提交。"""
        executor, algo_acl, task_acl = _make_executor(monkeypatch)
        _run_single_api(executor, None)

        assert task_acl.submit_evaluate_case.call_count == 1
        full_case_params = algo_acl.extract_case_all_params.call_args[0][0]
        assert full_case_params['reference_params'] == {}

    def test_call_site_kwargs_bind_against_base_signature(self, monkeypatch):
        """调用点实参必须对基类真实签名完成绑定——af2dbbd9 收紧签名后调用点
        漏传必填参数时 bind 即抛 TypeError（原缺陷的直接失败面）。"""
        executor, _, _ = _make_executor(monkeypatch)
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(executor, '_evaluate_result', _capture)
        _run_single_api(executor, {'reference_params': [{'code': 'a', 'value': 'b'}]})

        assert 'case_reference_params' in captured, \
            '调用点未显式传 case_reference_params'
        inspect.signature(BaseExecutor._evaluate_result).bind(None, **captured)
