# -*- coding: utf-8 -*-
"""测试全局夹具：裸 pytest 一律离线（LLM api_key 置空）。

.env 会在 import 链里加载进 os.environ，真实 api_key 存在时 v2 逐轮裁判钩子
（interruption_judge.judge_interruption_rounds 的 api_key gate）会发起真实网络调用。
需要 LLM 的测试自行 monkeypatch judge 模块的 get_llm_config/call_llm_api 覆盖本夹具。
"""
import pytest


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    from app.config import config
    llm = getattr(config, 'LLM_JUDGE', None)
    if isinstance(llm, dict) and llm.get('api_key'):
        monkeypatch.setitem(llm, 'api_key', '')
