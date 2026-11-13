# -*- coding: utf-8 -*-
"""INT-2456 agent_service /health（DB / Redis 连通 + T2 运行时可见性）与
三个部署挂载点的启动校验。

验收锚点（卡面第 1 条 / 拍板#3）：/health 反映真实依赖状态；skills / memory /
config 目录缺失或不可写时启动前明确报错，不静默忽略。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import agent_service.app as agent_app
from agent_service.config.config import Config
from agent_service.infrastructure.sandbox.t2_runtime import T2RuntimeStatus


class _Container:
    """最小组合根替身（只用到 shutdown；本组用例不触达 run/事件）。"""

    def shutdown(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(Config, 'RECOVERY_ON_STARTUP', False)
    app = agent_app.create_app(container=_Container())
    with TestClient(app) as test_client:
        yield test_client


def _stub_db(monkeypatch, ok=True, detail=''):
    monkeypatch.setattr(agent_app, '_probe_database', lambda: (ok, detail))


def _stub_redis(monkeypatch, ok=True, detail=''):
    monkeypatch.setattr(agent_app, '_probe_redis', lambda: (ok, detail))


def _stub_t2(monkeypatch, available=False):
    monkeypatch.setattr(
        agent_app, 'probe_t2_runtime',
        lambda runtime='': T2RuntimeStatus(
            runtime=runtime or 'runsc', available=available,
            binary_path='' if not available else '/usr/local/bin/runsc',
            detail='stub'))


def test_health_ok_reports_all_checks(monkeypatch, client):
    _stub_db(monkeypatch)
    _stub_redis(monkeypatch)
    _stub_t2(monkeypatch, available=True)
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['service'] == 'agent_service'
    assert body['checks']['database']['status'] == 'ok'
    assert body['checks']['redis']['status'] == 'ok'
    assert body['t2_runtime']['status'] == 'available'


def test_health_db_down_is_503(monkeypatch, client):
    _stub_db(monkeypatch, ok=False, detail='connection refused')
    _stub_redis(monkeypatch)
    _stub_t2(monkeypatch)
    response = client.get('/health')
    assert response.status_code == 503
    body = response.json()
    assert body['status'] == 'error'
    assert body['checks']['database']['status'] == 'error'


def test_health_redis_down_is_degraded_but_alive(monkeypatch, client):
    """Redis 只承载 SSE 唤醒（正文回表读），不可用退化为轮询，不算容器死亡。"""
    _stub_db(monkeypatch)
    _stub_redis(monkeypatch, ok=False, detail='connection refused')
    _stub_t2(monkeypatch)
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'degraded'
    assert body['checks']['redis']['status'] == 'error'


def test_health_t2_unavailable_is_reported_not_fatal(monkeypatch, client):
    _stub_db(monkeypatch)
    _stub_redis(monkeypatch)
    _stub_t2(monkeypatch, available=False)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['t2_runtime']['status'] == 'unavailable'


# ---------------------------------------------------------------- 探测本体

def test_probe_database_without_initialized_engine(monkeypatch):
    monkeypatch.setattr('shared.models.database.get_engine', lambda: None)
    ok, detail = agent_app._probe_database()
    assert ok is False
    assert 'DATABASE_URL' in detail


def test_probe_database_with_live_engine(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setattr('shared.models.database.get_engine', lambda: engine)
    assert agent_app._probe_database() == (True, '')


def test_probe_database_reports_failure(monkeypatch):
    def boom():
        raise RuntimeError('db gone')
    monkeypatch.setattr('shared.models.database.get_engine', boom)
    ok, detail = agent_app._probe_database()
    assert ok is False
    assert 'db gone' in detail


def test_probe_redis_skipped_for_local_wakeup(monkeypatch):
    monkeypatch.setattr(Config, 'EVENT_WAKEUP_BACKEND', 'local')
    ok, detail = agent_app._probe_redis()
    assert ok is True
    assert 'local' in detail


def test_probe_redis_reports_failure(monkeypatch):
    monkeypatch.setattr(Config, 'EVENT_WAKEUP_BACKEND', 'redis')
    monkeypatch.setattr(Config, 'REDIS_URL', 'redis://127.0.0.1:1')
    ok, _detail = agent_app._probe_redis()
    assert ok is False


# ---------------------------------------------------------------- 挂载点校验

def _mounts(tmp_path):
    skills = tmp_path / 'skills'
    skills.mkdir()
    # INT-2529：空 skills 目录不再是合法布局，哨兵必须是合法的 SKILL.md。
    sentinel = skills / 'platform-reference'
    sentinel.mkdir()
    (sentinel / 'SKILL.md').write_text(
        '---\nname: platform-reference\ndescription: 测试哨兵\n---\n\n'
        '# platform-reference\n\n## Gotchas\n\n- 无\n\n## 验收\n\n- 无\n',
        encoding='utf-8')
    memory = tmp_path / 'memory'
    memory.mkdir()
    catalog = tmp_path / 'model_catalog.json'
    catalog.write_text('{}', encoding='utf-8')
    return skills, memory, catalog


def test_validate_mounts_rejects_empty_skills_dir(monkeypatch, tmp_path):
    """卡面验收 4：空目录（bind 源缺失被 Docker 自动创建）→ 启动失败。"""
    _skills, memory, catalog = _mounts(tmp_path)
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(empty))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(memory))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(catalog))
    with pytest.raises(RuntimeError) as exc:
        Config.validate_mounts()
    assert 'SKILL.md' in str(exc.value)


def test_validate_mounts_rejects_skills_dir_without_skill_md(
        monkeypatch, tmp_path):
    """只有非 SKILL.md 文件同样视为零 Skill，不能静默放行。"""
    _skills, memory, catalog = _mounts(tmp_path)
    only_other = tmp_path / 'other-skills'
    (only_other / 'platform-reference').mkdir(parents=True)
    (only_other / 'platform-reference' / 'README.md').write_text(
        'not a skill', encoding='utf-8')
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(only_other))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(memory))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(catalog))
    with pytest.raises(RuntimeError) as exc:
        Config.validate_mounts()
    assert 'SKILL.md' in str(exc.value)


def test_validate_mounts_accepts_complete_layout(monkeypatch, tmp_path):
    skills, memory, catalog = _mounts(tmp_path)
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(skills))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(memory))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(catalog))
    Config.validate_mounts()


def test_validate_mounts_rejects_missing_skills(monkeypatch, tmp_path):
    _skills, memory, catalog = _mounts(tmp_path)
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(tmp_path / 'nope'))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(memory))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(catalog))
    with pytest.raises(RuntimeError) as exc:
        Config.validate_mounts()
    assert 'skills' in str(exc.value)


def test_validate_mounts_rejects_missing_memory(monkeypatch, tmp_path):
    skills, _memory, catalog = _mounts(tmp_path)
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(skills))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(tmp_path / 'nope'))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(catalog))
    with pytest.raises(RuntimeError) as exc:
        Config.validate_mounts()
    assert 'memory' in str(exc.value)


def test_validate_mounts_rejects_missing_catalog(monkeypatch, tmp_path):
    skills, memory, _catalog = _mounts(tmp_path)
    monkeypatch.setattr(Config, 'SKILLS_ROOT', str(skills))
    monkeypatch.setattr(Config, 'MEMORY_ROOT', str(memory))
    monkeypatch.setattr(Config, 'MODEL_CATALOG_PATH', str(tmp_path / 'nope.json'))
    with pytest.raises(RuntimeError) as exc:
        Config.validate_mounts()
    assert '模型目录' in str(exc.value)


def test_default_paths_are_inside_repo():
    """缺省路径与部署目录约定一致（skills/ 顶层、memory/ 写卷、config/）。"""
    assert Config.SKILLS_ROOT.replace('\\', '/').endswith('/skills')
    assert Config.MEMORY_ROOT.replace('\\', '/').endswith('/memory')
    assert Config.model_catalog_path().replace('\\', '/').endswith(
        '/agent_service/config/model_catalog.json')
