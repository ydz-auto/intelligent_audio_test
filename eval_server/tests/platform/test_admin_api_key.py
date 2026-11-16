# -*- coding: utf-8 -*-
"""PUT /admin/config/api_key 管理端点测试（VEGA-77）。

最小 Flask app 仅注册 admin_bp（避免 create_app 的 worker 线程/init_db 副作用），
monkeypatch 把 .env 路径指到 tmp_path。
覆盖验收矩阵 1-12（13 文档同步走 diff 核对，14 真实服务冒烟在测试阶段人工执行）。
"""
import logging
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from flask import Flask

import app.config as real_config_module
from app.config import config
from app.controllers.admin import admin_bp
from app.services import admin_config_service
from app.services.admin_config_service import AdminConfigError

TOKEN = 'unit-test-admin-token'
URL = '/admin/config/api_key'


@pytest.fixture()
def isolated_llm_env(monkeypatch):
    """隔离真实 LLM_JUDGE 配置：服务直调与路由测试共用（teardown 恢复原值）。"""
    monkeypatch.setitem(config.LLM_JUDGE, 'api_key', 'old-key')
    monkeypatch.setenv('LLM_JUDGE_API_KEY', 'old-key')


@pytest.fixture()
def client(tmp_path, monkeypatch, isolated_llm_env):
    """最小 Flask app + .env 指向 tmp_path。"""
    monkeypatch.setattr(admin_config_service, '_default_env_path', lambda: tmp_path / '.env')
    monkeypatch.setenv('EVAL_ADMIN_TOKEN', TOKEN)
    app = Flask(__name__)
    app.register_blueprint(admin_bp)
    return app.test_client()


def put(client, key_name='LLM_JUDGE_API_KEY', api_key='new-key', token=TOKEN):
    """带 token 的 PUT 请求；token=None 表示不带该请求头。"""
    headers = {'X-Admin-Token': token} if token is not None else {}
    return client.put(URL, json={'key_name': key_name, 'api_key': api_key}, headers=headers)


# ── 矩阵 1/2：未授权（无 token / 错误 token）一律 401，固定文案 ──

def test_matrix_1_no_token_401(client):
    resp = put(client, token=None)
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['code'] == 4001
    assert body['msg'] == '未授权'


def test_matrix_2_wrong_token_401(client):
    resp = put(client, token='wrong-token')
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['code'] == 4001
    # 与无 token 场景文案一致（不区分缺失/错误）
    assert body['msg'] == '未授权'


# ── 矩阵 3：EVAL_ADMIN_TOKEN 未配置三形态 → 403 端点禁用，空值头不得通过 ──

@pytest.mark.parametrize('env_value', [None, '', '   '], ids=['unset', 'empty', 'blank'])
def test_matrix_3_token_unconfigured_403(client, monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv('EVAL_ADMIN_TOKEN', raising=False)
    else:
        monkeypatch.setenv('EVAL_ADMIN_TOKEN', env_value)
    # 无论不带 / 空值 / 纯空白 / 正确值头，端点一律 403 禁用（fail-closed）
    for token in (None, '', '   ', TOKEN):
        resp = put(client, token=token)
        assert resp.status_code == 403, f'env={env_value!r} token={token!r}'
        body = resp.get_json()
        assert body['code'] == 4002
        assert body['msg'] == '管理端点未启用'


# ── 矩阵 4：key 不回显、不落日志（token 值也不落日志） ──

def test_matrix_4_no_key_echo_no_log(client, caplog):
    secret = "cfg-secret-must-not-echo-anywhere"
    with caplog.at_level(logging.INFO):
        resp = put(client, api_key=secret)
    assert resp.status_code == 200
    body = resp.get_json()
    # data 只有 key_name/updated_at，无任何 key 值/旧值/掩码
    assert set(body['data'].keys()) == {'key_name', 'updated_at'}
    assert secret not in resp.get_data(as_text=True)
    assert secret not in caplog.text
    assert TOKEN not in caplog.text


# ── 矩阵 5：更新后热生效（os.environ 与 config.LLM_JUDGE 双断言） ──

def test_matrix_5_hot_effect(client):
    resp = put(client, api_key='hot-new-key')
    assert resp.status_code == 200
    assert os.environ['LLM_JUDGE_API_KEY'] == 'hot-new-key'
    assert config.LLM_JUDGE['api_key'] == 'hot-new-key'


# ── 矩阵 6：重启后仍生效（影子目录 + 子进程 import config） ──

def test_matrix_6_effective_after_restart(tmp_path, isolated_llm_env):
    shadow = tmp_path / 'shadow'
    (shadow / 'app').mkdir(parents=True)
    # 影子 app 包：空 __init__.py + 复制真实 config.py；config.yaml 同级复制
    (shadow / 'app' / '__init__.py').write_text('', encoding='utf-8')
    real_dir = Path(real_config_module.__file__).resolve().parent
    shutil.copy2(real_dir / 'config.py', shadow / 'app' / 'config.py')
    shutil.copy2(real_dir.parent / 'config.yaml', shadow / 'config.yaml')

    new_key = 'restart-new-key'
    admin_config_service.update_env_key('LLM_JUDGE_API_KEY', new_key, env_path=shadow / '.env')

    # 子进程 sys.path 指影子目录（.env 为模块相对路径 → 影子 .env）；
    # 环境剔除 LLM_JUDGE_API_KEY：setdefault 语义下 shell 预置变量会短路 .env
    code = (
        "import sys; sys.path.insert(0, r'%s'); "
        "from app.config import config; "
        "print(config.LLM_JUDGE['api_key'])"
    ) % str(shadow)
    env = {k: v for k, v in os.environ.items() if k != 'LLM_JUDGE_API_KEY'}
    result = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True,
        env=env, cwd=str(tmp_path), timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == new_key


# ── 矩阵 7：.env 其它行逐行原样保留（含行尾字符，仅目标行变） ──

def test_matrix_7_other_lines_preserved(client, tmp_path):
    env_path = tmp_path / '.env'
    original = [
        '# 顶部注释\r\n',
        'LLM_JUDGE_API_KEY=old-key\r\n',
        'ASR_SERVER_URL=http://127.0.0.1:10095\r\n',
        '# 中部注释（保留）\r\n',
        'ASR_TIMEOUT=120\r\n',
    ]
    with open(env_path, 'w', encoding='utf-8', newline='') as f:
        f.write(''.join(original))

    resp = put(client, api_key='preserve-new-key')
    assert resp.status_code == 200

    with open(env_path, encoding='utf-8', newline='') as f:
        after = f.read()
    assert after.splitlines(keepends=True) == [
        original[0],
        'LLM_JUDGE_API_KEY=preserve-new-key\r\n',
        original[2],
        original[3],
        original[4],
    ]


# ── 矩阵 8：并发写安全（无交错损坏、无临时文件残留） ──

def test_matrix_8_concurrent_writes(client, tmp_path):
    env_path = tmp_path / '.env'
    with open(env_path, 'w', encoding='utf-8', newline='') as f:
        f.write('# 注释\nLLM_JUDGE_API_KEY=old\nASR_TIMEOUT=120\n')
    values = [f'conc-key-{i}' for i in range(8)]

    def worker(value):
        # 每线程独立 Flask app + test_client（同一线程池并发打请求）
        app = Flask(__name__)
        app.register_blueprint(admin_bp)
        with app.test_client() as c:
            resp = c.put(URL, json={'key_name': 'LLM_JUDGE_API_KEY', 'api_key': value},
                         headers={'X-Admin-Token': TOKEN})
        return resp.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(worker, values))
    assert statuses == [200] * 8

    with open(env_path, encoding='utf-8', newline='') as f:
        lines = f.read().splitlines(keepends=True)
    assert len(lines) == 3
    target = [ln for ln in lines if ln.startswith('LLM_JUDGE_API_KEY=')]
    assert len(target) == 1
    assert target[0].split('=', 1)[1].strip() in values
    # 无残留 .env.tmp.* 临时文件
    assert not list(tmp_path.glob('.env.tmp.*'))


# ── 矩阵 9/10：非法 key_name / 非法或缺失 api_key → 400 code=4000 ──

def test_matrix_9_invalid_key_name(client):
    resp = put(client, key_name='OSS_ACCESS_KEY')
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['code'] == 4000
    assert body['msg'] == '参数不合法'


@pytest.mark.parametrize('api_key', ['', '   ', 123, None], ids=['empty', 'blank', 'int', 'null'])
def test_matrix_10_invalid_api_key(client, api_key):
    resp = put(client, api_key=api_key)
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 4000


def test_matrix_10_missing_field_and_non_json(client):
    # 缺 api_key 字段
    resp = client.put(URL, json={'key_name': 'LLM_JUDGE_API_KEY'},
                      headers={'X-Admin-Token': TOKEN})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 4000
    # 非 JSON 请求体
    resp = client.put(URL, data='not-json', headers={'X-Admin-Token': TOKEN})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 4000


def test_matrix_10_unhashable_key_name(client):
    # JSON 传 list：服务层先 isinstance 再查白名单，不得 500
    resp = put(client, key_name=['LLM_JUDGE_API_KEY'])
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 4000


# ── 矩阵 11：.env 不存在时自动创建，不产生 .env.bak ──

def test_matrix_11_env_autocreate(client, tmp_path):
    env_path = tmp_path / '.env'
    assert not env_path.exists()
    resp = put(client, api_key='fresh-key')
    assert resp.status_code == 200
    assert 'LLM_JUDGE_API_KEY=fresh-key' in env_path.read_text(encoding='utf-8')
    assert not (tmp_path / '.env.bak').exists()


# ── 矩阵 12：读端点不存在 → 405 ──

def test_matrix_12_no_read_endpoint(client):
    resp = client.get(URL)
    assert resp.status_code == 405


# ── 分层补充：边界（超长 key）/ 异常（写失败 500 且临时文件被清理） ──

def test_boundary_very_long_key(client):
    long_key = 'k' * 10000
    resp = put(client, api_key=long_key)
    assert resp.status_code == 200
    assert os.environ['LLM_JUDGE_API_KEY'] == long_key
    # 响应体不回显超长 key
    assert long_key not in resp.get_data(as_text=True)


def test_write_failure_500_and_tmp_cleanup(client, tmp_path, monkeypatch):
    env_path = tmp_path / '.env'
    env_path.write_text('LLM_JUDGE_API_KEY=old-key\n', encoding='utf-8')

    def fake_replace(src, dst):
        raise OSError('模拟 os.replace 失败')

    monkeypatch.setattr(os, 'replace', fake_replace)
    resp = put(client, api_key='doomed-key')
    assert resp.status_code == 500
    body = resp.get_json()
    assert body['code'] == 5000
    assert body['msg'] == '配置写入失败'
    # 失败不回显 key 值，且临时文件被 finally 清理
    assert 'doomed-key' not in resp.get_data(as_text=True)
    assert not list(tmp_path.glob('.env.tmp.*'))
    # .env 原样未动、内存未改（先文件后内存的顺序保证）
    assert env_path.read_text(encoding='utf-8') == 'LLM_JUDGE_API_KEY=old-key\n'
    assert os.environ['LLM_JUDGE_API_KEY'] == 'old-key'
    assert config.LLM_JUDGE['api_key'] == 'old-key'


# ── 服务函数直调（脱离 HTTP） ──

def test_service_stores_stripped_value(tmp_path, isolated_llm_env):
    # 存储取 strip 后的值，与 config.py 读取端 v.strip() 口径一致
    admin_config_service.update_env_key('LLM_JUDGE_API_KEY', '  padded-key  ',
                                        env_path=tmp_path / '.env')
    assert (tmp_path / '.env').read_text(encoding='utf-8') == 'LLM_JUDGE_API_KEY=padded-key\n'


@pytest.mark.parametrize('key_name,value', [
    ('OSS_ACCESS_KEY', 'x'),
    ('LLM_JUDGE_API_KEY', ''),
    ('LLM_JUDGE_API_KEY', '   '),
    ('LLM_JUDGE_API_KEY', 123),
    (123, 'x'),
], ids=['not-whitelisted', 'empty', 'blank', 'int-value', 'int-key'])
def test_service_validation_errors(tmp_path, isolated_llm_env, key_name, value):
    with pytest.raises(AdminConfigError):
        admin_config_service.update_env_key(key_name, value, env_path=tmp_path / '.env')


def test_service_backup_created(tmp_path, isolated_llm_env):
    env_path = tmp_path / '.env'
    env_path.write_text('LLM_JUDGE_API_KEY=old-key\n', encoding='utf-8')
    admin_config_service.update_env_key('LLM_JUDGE_API_KEY', 'new-key', env_path=env_path)
    assert (tmp_path / '.env.bak').read_text(encoding='utf-8') == 'LLM_JUDGE_API_KEY=old-key\n'
    # 重复更新：.env.bak 单槽覆盖为上一版内容
    admin_config_service.update_env_key('LLM_JUDGE_API_KEY', 'newer-key', env_path=env_path)
    assert (tmp_path / '.env.bak').read_text(encoding='utf-8') == 'LLM_JUDGE_API_KEY=new-key\n'
