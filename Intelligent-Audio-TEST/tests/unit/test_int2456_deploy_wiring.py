# -*- coding: utf-8 -*-
"""INT-2456 部署接线静态守卫。

覆盖卡面验收 1/4/5 与拍板增补的「编排可读、开关默认关、挂载点齐全」：
- Dockerfile.agent_service 走统一 build args、EXPOSE 5011、CMD 指向 app；
- compose 的 agent_service 不发布宿主端口、restart 自愈、三卷挂载、healthcheck；
- 网关代理地址与总开关默认 false；
- 构建/健康脚本登记了新服务；
- db_bootstrap 引导 agent_* 表（依赖 m0-01 的迁移脚本）。
"""
import os

import yaml

# tests/unit/conftest.py 的日志 worker 清理夹具在 teardown 导入 shared 配置，
# 需要基础凭据占位（与其余单测同口径）。
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DOCKER_DIR = os.path.join(PROJECT_ROOT, 'docker')


def _read(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


def _compose():
    return yaml.safe_load(_read('docker', 'docker-compose.yml'))


# ---------------------------------------------------------------- Dockerfile

def test_dockerfile_follows_backend_conventions():
    text = _read('docker', 'Dockerfile.agent_service')
    assert 'FROM python:3.11-slim' in text
    assert 'ARG APT_MIRROR' in text
    assert 'ARG PIP_INDEX_URL' in text
    assert 'EXPOSE 5011' in text
    assert 'agent_service.app' in text


# ---------------------------------------------------------------- compose

def test_agent_service_compose_block():
    service = _compose()['services']['agent_service']
    assert service['restart'] == 'unless-stopped'
    # 不发布宿主端口：只经网关访问，身份头不可伪造。
    assert 'ports' not in service
    assert service['build']['dockerfile'] == 'docker/Dockerfile.agent_service'
    assert service['build']['args'], '必须复用 x-backend-build-args'


def test_agent_service_mounts_three_volumes_with_expected_modes():
    volumes = _compose()['services']['agent_service']['volumes']
    assert '../skills:/app/skills:ro' in volumes
    assert 'agent_memory:/app/memory' in volumes
    assert '../agent_service/config:/app/agent_service/config:ro' in volumes
    assert 'agent_memory' in _compose()['volumes']


def test_agent_service_dependencies_and_healthcheck():
    service = _compose()['services']['agent_service']
    depends = service['depends_on']
    for name in ('postgres', 'redis', 'api_gateway', 'db_bootstrap'):
        assert name in depends, name
    test = ' '.join(service['healthcheck']['test'])
    assert '5011/health' in test


def test_agent_service_env_covers_config_contract():
    env = '\n'.join(_compose()['services']['agent_service']['environment'])
    for needle in (
        'DATABASE_URL=', 'REDIS_URL=',
        # BaseConfig 导入期强校验 OSS 凭据：缺了容器起不来（实测 2026-11-13）
        'OSS_ACCESS_KEY=', 'OSS_SECRET_KEY=', 'OSS_ENDPOINT=',
        'AGENT_CREDENTIAL_MASTER_KEY=', 'AGENT_ALLOW_PLATFORM_KEY=false',
        'AGENT_MODEL_CATALOG_PATH=/app/agent_service/config/model_catalog.json',
        'AGENT_SKILLS_ROOT=/app/skills', 'AGENT_MEMORY_ROOT=/app/memory',
        'AGENT_T2_RUNTIME=', 'AGENT_SANDBOX_EXECUTOR_MODE=',
        'AGENT_MAX_ROUNDS=', 'AGENT_MAX_TOOL_CALLS=', 'AGENT_MAX_TOKENS=',
        'AGENT_MAX_DURATION_SECONDS=', 'AGENT_MAX_OUTPUT_BYTES=',
        # INT-2529：意图工具回源必须指向网关容器；缺省 127.0.0.1:5000 在容器内
        # 打到自身（ConnectError），启动与 /health 却全绿，属静默故障。
        'AGENT_TOOL_GATEWAY_BASE_URL=http://api_gateway:5000',
        # INT-2529：总开关同源传入，关闭态门控启动恢复投递（不产生后台 run）。
        'AGENT_ENABLED=${AGENT_ENABLED:-false}',
    ):
        assert needle in env, needle


def test_gateway_points_at_agent_service_and_defaults_off():
    env = '\n'.join(_compose()['services']['api_gateway']['environment'])
    assert 'AGENT_SERVICE_URL=http://agent_service:5011' in env
    assert 'AGENT_ENABLED=${AGENT_ENABLED:-false}' in env
    # 总开关关闭不得让网关反向依赖 agent_service（人工流程不受影响）。
    assert 'agent_service' not in _compose()['services']['api_gateway'].get(
        'depends_on', {})


# ---------------------------------------------------------------- 脚本/文档

def test_build_and_health_scripts_register_agent_service():
    build_text = _read('docker', 'build_stack.py')
    assert "'agent_service'" in build_text
    run_text = _read('docker', 'run_stack.py')
    assert "('agent_service', 5011, None)" in run_text


def test_env_examples_document_switch_and_secret():
    compose_env = _read('docker', '.env.compose.example')
    for key in ('AGENT_ENABLED', 'AGENT_CREDENTIAL_MASTER_KEY',
                'AGENT_T2_RUNTIME', 'LOG_ENVIRONMENT'):
        assert key in compose_env, key
    root_env = _read('.env.example')
    for key in ('AGENT_ENABLED', 'AGENT_CREDENTIAL_MASTER_KEY',
                'AGENT_MEMORY_ROOT', 'AGENT_T2_RUNTIME'):
        assert key in root_env, key


def test_readme_documents_t2_runtime_and_mounts():
    readme = _read('docker', 'README.md')
    assert 'runsc' in readme
    assert 'T2_RUNTIME_UNAVAILABLE' in readme
    assert 'AGENT_ENABLED' in readme
    assert '/app/skills' in readme and '/app/memory' in readme


# ---------------------------------------------------------------- 依赖前置

def test_skills_and_memory_roots_exist_for_mounts():
    """只读挂载源目录必须存在：skills/ 由 INT-2452 建、memory/ 由本卡建。"""
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'skills'))
    assert os.path.isfile(os.path.join(
        PROJECT_ROOT, 'skills', 'platform-reference', 'SKILL.md'))
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'memory'))
    assert os.path.isdir(os.path.join(PROJECT_ROOT, 'agent_service', 'config'))


def test_db_bootstrap_bootstraps_agent_tables():
    text = _read('docker', 'db_bootstrap_entrypoint.py')
    assert '202611/add_agent_runtime_tables.py' in text
    assert '202611/add_agent_llm_provider_table.py' in text
