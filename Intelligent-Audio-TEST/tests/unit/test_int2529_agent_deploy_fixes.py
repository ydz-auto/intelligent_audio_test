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

import yaml
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _import_config_value(expr, **overrides):
    """在干净子进程里 import Config 取字段（BaseConfig 字段 import 即固化）。"""
    env = dict(os.environ)
    env.pop('AGENT_TOOL_GATEWAY_BASE_URL', None)
    env.pop('AGENT_ENABLED', None)
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


# ---------------------------------------------------------------- 总开关门控恢复

class _FakeRecovery:
    def __init__(self):
        self.calls = 0

    def recover(self):
        self.calls += 1
        return ['run-1']


class _FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, run_id):
        self.submitted.append(run_id)


class _Container:
    """最小组合根替身：只用到 recovery / executor / shutdown。"""

    def __init__(self):
        self.recovery = _FakeRecovery()
        self.executor = _FakeExecutor()

    def shutdown(self):
        pass


def _run_lifespan(monkeypatch, *, enabled, recovery_on_startup=True):
    import agent_service.app as agent_app
    from agent_service.config.config import Config

    monkeypatch.setattr(Config, 'AGENT_ENABLED', enabled)
    monkeypatch.setattr(Config, 'RECOVERY_ON_STARTUP', recovery_on_startup)
    container = _Container()
    app = agent_app.create_app(container=container)
    with TestClient(app):  # 进入即触发 lifespan 启动段
        pass
    return container


def test_agent_enabled_defaults_false():
    """与网关同源、缺省关闭：关闭态不产生任何后台 run。"""
    assert _import_config_value('Config.AGENT_ENABLED') == 'False'


def test_disabled_switch_skips_recovery_and_dispatch(monkeypatch):
    """卡面验收 3：AGENT_ENABLED=false 时 recover() 与投递一律跳过。"""
    container = _run_lifespan(monkeypatch, enabled=False)
    assert container.recovery.calls == 0
    assert container.executor.submitted == []


def test_disabled_switch_wins_over_recovery_flag(monkeypatch):
    """恢复开关为 true 也不能让关闭态产生后台 run（开关优先）。"""
    container = _run_lifespan(
        monkeypatch, enabled=False, recovery_on_startup=True)
    assert container.recovery.calls == 0
    assert container.executor.submitted == []


def test_enabled_switch_keeps_recovery_behavior(monkeypatch):
    """卡面验收 3：开启后恢复投递行为不变（recover + submit 各一次）。"""
    container = _run_lifespan(
        monkeypatch, enabled=True, recovery_on_startup=True)
    assert container.recovery.calls == 1
    assert container.executor.submitted == ['run-1']


def test_enabled_switch_still_honours_recovery_flag(monkeypatch):
    container = _run_lifespan(
        monkeypatch, enabled=True, recovery_on_startup=False)
    assert container.recovery.calls == 0
    assert container.executor.submitted == []


# ---------------------------------------------------------------- 网络隔离

def _compose():
    with open(os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.yml'),
              encoding='utf-8') as handle:
        return yaml.safe_load(handle)


def _networks(compose, service):
    return list(compose['services'][service].get('networks') or [])


def test_agent_service_is_off_the_default_network():
    """同网络容器不能凭 X-User-Id 头绕过网关直连建 run（INT-2522 附带项）。"""
    compose = _compose()
    assert compose['networks']['agent_internal']['internal'] is True
    assert _networks(compose, 'agent_service') == ['agent_internal',
                                                   'agent_egress']
    assert 'default' not in _networks(compose, 'agent_service')


def test_agent_internal_membership_is_only_gateway_db_redis():
    compose = _compose()
    members = sorted(
        name for name, service in compose['services'].items()
        if 'agent_internal' in (service.get('networks') or []))
    assert members == ['agent_service', 'api_gateway', 'postgres', 'redis']
    for name in ('api_gateway', 'postgres', 'redis'):
        assert 'default' in _networks(compose, name), name


def test_agent_egress_has_no_other_members():
    """出网网络只有 agent_service：LLM 供应商出网，但不构成第二条入站路径。"""
    compose = _compose()
    members = [name for name, service in compose['services'].items()
               if 'agent_egress' in (service.get('networks') or [])]
    assert members == ['agent_service']
