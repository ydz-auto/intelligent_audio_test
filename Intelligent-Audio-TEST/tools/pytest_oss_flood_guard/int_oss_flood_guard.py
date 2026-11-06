"""INT-352 解释器级 pytest OSS 断网守卫（site-packages 结构覆盖）。

背景：主仓 tests/conftest.py 的会话守卫（commit e657febf）只覆盖主仓工作区。
multica 任务级临时 checkout（multica repo checkout 固定旧 commit）从其它目录
用同一批解释器跑 pytest 时不受保护——2026-10-14 18:0x~18:3x+08 实证：INT-311
验证区（c59c1dfc，早于守卫提交）的 ``python -m pytest tests/`` 复现洪泛
（5 分钟窗口 82 条 InvalidAccessKeyId）。

机制：以 pytest11 入口点插件装入解释器 site-packages，任何目录发起的 pytest
会话都会在启动早期（早于一切 conftest / 项目代码导入）加载本模块：

- OSS_ENDPOINT 未设置（将回落项目默认 http://localhost:9000）或显式指向
  localhost/127.0.0.1/::1 的 :9000 时，改写为 http://127.0.0.1:9（必拒端口，
  connection refused 瞬时失败 → 照常本地降级，判定结论不变）；
- 显式配置了其它端点 → 不干预（不覆盖真实远端 OSS 配置）；
- PYTEST_ALLOW_REAL_OSS=1 → 完全豁免（与主仓 conftest 守卫同一豁免口）；
- pytest_configure 兜底复查一次，覆盖 conftest 在导入期把端点改回 :9000 的
  场景（插件加载先于 conftest，此处是最后一道）。

作用域：仅 pytest 进程内生效（pytest11 插件只在 pytest 启动时导入），不污染
普通 python 进程；须以 pip 装入实际跑 pytest 的解释器（当前为
D:\\00_env\\miniconda 与 D:\\00_env\\conda_envs\\intelligent_audio_test）。

残余风险（登记）：PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 会跳过所有入口点插件；
其它解释器（如 eval_server）未装本插件。
"""

import os
from urllib.parse import urlsplit

DEAD_ENDPOINT = "http://127.0.0.1:9"

# 本机 rustfs（INT-220 rehome 后常驻）的判定特征
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _is_local_9000(endpoint):
    """端点是否指向本机 :9000。容忍缺 scheme 的写法（如 localhost:9000）。"""
    if "://" not in endpoint:
        endpoint = "http://" + endpoint
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return host in _LOCAL_HOSTS and port == 9000


def _apply():
    """按守卫语义改写 OSS_ENDPOINT（幂等；仅当会命中本机 :9000 时）。"""
    if os.environ.get("PYTEST_ALLOW_REAL_OSS"):
        return
    endpoint = os.environ.get("OSS_ENDPOINT")
    if endpoint and not _is_local_9000(endpoint):
        return
    os.environ["OSS_ENDPOINT"] = DEAD_ENDPOINT


_apply()


def pytest_configure(config):
    """兜底：conftest 导入期若把端点改回本机 :9000，配置完成后补写。"""
    _apply()
