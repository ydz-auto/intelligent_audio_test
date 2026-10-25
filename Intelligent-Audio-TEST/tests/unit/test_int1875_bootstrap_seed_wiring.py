# -*- coding: utf-8 -*-
"""INT-1875：引导链「种子/迁移脚本必须真的被引导链执行」守卫。

背景：INT-1746（C1）的种子 ``seed_api_eval_mapping_int1746.py`` 随卡落盘，
C1 分支里也在 ``BOOTSTRAP_STEPS`` 追加了这一步，但集成合入 INT-1746/INT-1749
（``f8a97ea94``）时整份取了 int-1749 侧的引导链文件，追加项静默丢失 ——
V9.7.31 上「文件在、步骤不在」，新环境跑完引导链 ``voice_llm`` 只剩
``response_audio`` 一条输出声明，INT-1748（C3）删掉执行侧硬编码展示字段后
任务详情 / 报告的 voice_llm 结果整段降级。

本守卫钉住三件事（任一被删/被挤出末位即红）：
1. 该种子步骤在 ``BOOTSTRAP_STEPS`` 里且带 ``--apply``（脚本默认 dry-run）；
2. 排在 ⑪ ``seed_voice_llm`` 之后 —— 后者 Step 5 会 DELETE ``session_id`` 等
   会话协议字段，排前面等于白补；
3. 排在 INT-1741 的 ``ANALYZE`` 兜底之前 —— 分析后再写数据会让统计过期
   （``test_int1741_analyze_stale_statistics.py::test_bootstrap_step_is_last``
   钉住 ANALYZE 必须是最后一步）。
"""
import importlib.util
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENTRYPOINT = os.path.join(_REPO_ROOT, 'docker', 'db_bootstrap_entrypoint.py')

_SEED_1746 = 'scripts/migrations/202610/seed_api_eval_mapping_int1746.py'
_SEED_VOICE_LLM = 'scripts/migrations/202609/seed_voice_llm.py'
_ANALYZE_1741 = 'scripts/migrations/202610/analyze_stale_statistics_int1741.py'


def _load_entrypoint():
    """只加载常量（模块级无副作用：psycopg2 在函数内 import）。"""
    spec = importlib.util.spec_from_file_location('_db_bootstrap_int1875', _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _step_index(steps, script_rel):
    for idx, step in enumerate(steps):
        if step[1] == script_rel:
            return idx
    return -1


def test_seed_1746_step_is_in_bootstrap_chain():
    """INT-1746 的 API 输出声明 + source='api' 映射种子必须被引导链执行。"""
    steps = _load_entrypoint().BOOTSTRAP_STEPS
    idx = _step_index(steps, _SEED_1746)
    assert idx >= 0, (
        f'{_SEED_1746} 不在 BOOTSTRAP_STEPS 里：新环境跑完引导链后 voice_llm 的 '
        'direction=output 声明与 source=\'api\' 映射都没有来源（INT-1875 缺陷形态）')
    assert steps[idx][2:] == ('--apply',), (
        '种子脚本默认 dry-run，引导链里必须带 --apply，否则等于没执行')


def test_seed_1746_runs_after_seed_voice_llm():
    """seed_voice_llm 会 DELETE session_id 等会话协议字段，本步必须在其后。"""
    steps = _load_entrypoint().BOOTSTRAP_STEPS
    assert _step_index(steps, _SEED_VOICE_LLM) < _step_index(steps, _SEED_1746)


def test_seed_1746_runs_before_analyze_last_step():
    """写数据的种子必须排在 INT-1741 的 ANALYZE 兜底之前（后者保持末位）。"""
    steps = _load_entrypoint().BOOTSTRAP_STEPS
    assert steps[-1][1] == _ANALYZE_1741, 'ANALYZE 兜底必须仍是引导链最后一步'
    assert _step_index(steps, _SEED_1746) < len(steps) - 1


def test_seed_1746_step_appears_once():
    """重复追加会让同一脚本在一次引导里跑两遍（幂等但无意义，且易掩盖冲突解错）。"""
    steps = _load_entrypoint().BOOTSTRAP_STEPS
    assert [s[1] for s in steps].count(_SEED_1746) == 1


def test_seed_1746_declared_in_migrations_readme():
    """README 执行顺序总览里必须登记该步（集成时同批丢失的还有这一行）。"""
    with open(os.path.join(_REPO_ROOT, 'scripts', 'migrations', 'README.md'),
              encoding='utf-8') as fh:
        content = fh.read()
    assert _SEED_1746 in content, (
        'README「执行顺序总览」缺 seed_api_eval_mapping_int1746.py 的登记行')
