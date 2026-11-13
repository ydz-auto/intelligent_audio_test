# -*- coding: utf-8 -*-
"""INT-2529 部署接线补漏（INT-2522 审计 P0/P1）。

覆盖三件事：
1. 工具回源地址必须指向网关容器（compose 接线 + Config 解析）；
2. 总开关关闭态不产生任何后台 run（启动恢复投递门控）；
3. skills 空目录（bind 源缺失被 Docker 自动创建）不得静默变「零 Skill」。

静态编排守卫在 ``test_int2456_deploy_wiring``；本文件验证运行期语义。
"""
import os
import subprocess
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _import_config_value(expr, **overrides):
    """在干净子进程里 import Config 取字段（BaseConfig 字段 import 即固化）。"""
    env = dict(os.environ)
    env.pop('AGENT_TOOL_GATEWAY_BASE_URL', None)
    env.update(overrides)
    env.setdefault('DATABASE_URL', 'sqlite://')
    env.setdefault('OSS_ACCESS_KEY', 'test')
    env.setdefault('OSS_SECRET_KEY', 'test')
    code = ('from agent_service.config.config import Config; '
            f'print({expr})')
    out = subprocess.run(
        [sys.executable, '-c', code], env=env, cwd=PROJECT_ROOT,
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


# ---------------------------------------------------------------- 工具回源

def test_config_parses_tool_gateway_base_url_from_env():
    """卡面验收 2：容器内解析为 http://api_gateway:5000，而非 127.0.0.1:5000。"""
    assert _import_config_value(
        'Config.TOOL_GATEWAY_BASE_URL',
        AGENT_TOOL_GATEWAY_BASE_URL='http://api_gateway:5000',
    ) == 'http://api_gateway:5000'


def test_config_tool_gateway_default_is_loopback():
    """缺省只适合同机直跑：容器内必须在编排层显式覆盖（见 compose）。"""
    assert _import_config_value(
        'Config.TOOL_GATEWAY_BASE_URL') == 'http://127.0.0.1:5000'
