# -*- coding: utf-8 -*-
"""INT-314 集成推送门禁·失败路径回归单测（P1/P2/P3 修复防线，审计第 7 项）。

打回三项在 main()/s2_create_case() 内的修复逻辑，不依赖真实栈/库/裁判替身——
前置函数与 HTTP/DB 全部 mock，单测直接驱动 scripts/smoke_gate 模块：

1. P1（创建即登记 + 失败路径清理/零残留终检）：api_cfg 创建成功即写入 created
   registry，随后 upload/init 抛非 GateFail AssertionError → created 已登记
   api_cfg 不丢；main() 失败退出码 1，finally 仍对已登记资源执行 cleanup
   （spy 断言收到 id），失败路径照跑零残留终检。
2. P2（非 GateFail 异常收敛 + --json 恒输出）：同注入 → 结果 JSON pass=false，
   fail_detail 含「异常逃逸（已收敛）」与 @ file:line 定位，无裸 traceback。
3. P3（dry 样例 wav 前置 GateFail）：样例 wav 缺失时 s2_create_case 在任何写
   操作之前以 GateFail 失败（带完整路径），created registry 不被污染。
"""
import json
import sys

import pytest

import scripts.smoke_gate as sg


class _Resp:
    """最小 httpx 响应替身（smoke_gate 只取 status_code/json()/text）。"""

    def __init__(self, data=None, status=200):
        self.status_code = status
        self._data = data if data is not None else {'success': True, 'code': 200, 'data': {}}
        self.text = json.dumps(self._data, ensure_ascii=False)

    def json(self):
        return self._data


class _FakeCur:
    """只读游标替身：turn_eval 主维度查询返回 id=55。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return None

    def fetchone(self):
        return (55,)


class _FakeConn:
    def cursor(self):
        return _FakeCur()

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _patch_front(monkeypatch):
    """前置（栈/替身/引导/隔离库串/终检）全部隔离，不触真实环境。"""
    monkeypatch.setattr(sg, 'ensure_stack', lambda: {'database': 'intelligent_audio_test_test'})
    monkeypatch.setattr(sg, 'ensure_judge', lambda: (None, True))
    monkeypatch.setattr(sg, 'bootstrap_db', lambda url: None)
    monkeypatch.setattr(sg, '_isolated_db_url',
                        lambda: 'postgresql://u:p@localhost:5432/intelligent_audio_test_test')
    monkeypatch.setattr(sg, 'residue_check', lambda: [])
    monkeypatch.setattr(sg, '_port_open', lambda *a, **k: False)
    monkeypatch.setattr(sys, 'argv', ['smoke_gate.py', '--json'])


def _make_wav_samples(monkeypatch, tmp_path):
    """构造两个假 dry 样例 wav，绕过 P3 前置（P1/P2 用例的目标是建用例中途失败）。"""
    for name in ('a.wav', 'b.wav'):
        (tmp_path / name).write_bytes(b'RIFF' + b'\x00' * 64)
    monkeypatch.setattr(sg, 'SAMPLE_DIR', str(tmp_path))
    monkeypatch.setattr(sg, 'SAMPLE_AUDIO_FILES', ['a.wav', 'b.wav'])


def _patch_upload_init_fail(monkeypatch):
    """httpx.post：/apis 创建成功返回 id=314001；upload/init 抛非 GateFail
    AssertionError（模拟建用例中途、api_cfg 已创建之后的非门禁异常逃逸）。"""
    created_api = {'success': True, 'code': 200, 'data': {'id': 314001}}
    real_post = sg.httpx.post

    def fake_post(url, *args, **kwargs):
        if str(url).endswith('/apis'):
            return _Resp(created_api)
        if str(url).endswith('/audios/upload/init'):
            raise AssertionError('注入: upload/init 抛非 GateFail AssertionError')
        raise sg.GateFail(f'unexpected http call: {url}')

    monkeypatch.setattr(sg.httpx, 'post', fake_post)


def test_p1_registry_captures_created_api_before_midway_failure(monkeypatch, tmp_path):
    """P1 创建即登记：api_cfg 创建成功后即写入 registry，upload/init 中途失败不丢。"""
    _make_wav_samples(monkeypatch, tmp_path)
    _patch_upload_init_fail(monkeypatch)
    monkeypatch.setattr(sg.psycopg2, 'connect', lambda *a, **k: _FakeConn())

    created = {}
    with pytest.raises(AssertionError, match='upload/init'):
        sg.s2_create_case('tok', created)

    assert created['api_cfg_ids'] == [314001], '已创建 api_cfg 必须保留在 registry'


def test_p2_non_gatefail_converged_json_and_cleanup_runs(monkeypatch, tmp_path, capsys):
    """P2 非 GateFail 收敛 + --json 恒输出 + finally 按 registry 全量清理。"""
    _patch_front(monkeypatch)
    _make_wav_samples(monkeypatch, tmp_path)
    _patch_upload_init_fail(monkeypatch)
    monkeypatch.setattr(sg.psycopg2, 'connect', lambda *a, **k: _FakeConn())

    def fake_login():
        sg.step('S1 登录（mock）', True, 'token_len=212')
        return 'test-token'

    monkeypatch.setattr(sg, 's1_login', fake_login)

    seen = {}

    def spy_cleanup(token, created):
        seen['token'] = token
        seen['created'] = dict(created)
        return []

    monkeypatch.setattr(sg, 'cleanup', spy_cleanup)

    ec = sg.main()
    assert ec == 1, '非 GateFail 异常必须收敛进失败路径（退出码 1）'
    assert seen['created']['api_cfg_ids'] == [314001], \
        'finally 清理必须拿到「创建即登记」的已登记资源'

    out, _ = capsys.readouterr()
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if ln.strip() == '{' and i + 1 < len(lines) and '"gate"' in lines[i + 1])
    result = json.loads('\n'.join(lines[start:]))
    assert result['pass'] is False
    assert '异常逃逸（已收敛）' in result['fail_detail']
    assert 'AssertionError' in result['fail_detail']
    assert '@ ' in result['fail_detail'], 'fail_detail 必须带 file:line 定位'
    assert result['residue'] == []
    assert result['tag'].startswith('INT314SMOKE_')


def test_p3_wav_missing_gatefail_before_any_write(monkeypatch, tmp_path):
    """P3 前置：dry 样例 wav 缺失时在任何写操作之前 GateFail，registry 不被污染。"""
    empty_dir = tmp_path / 'empty'
    empty_dir.mkdir()
    monkeypatch.setattr(sg, 'SAMPLE_DIR', str(empty_dir))
    monkeypatch.setattr(sg, 'SAMPLE_AUDIO_FILES', ['a.wav', 'b.wav'])

    created = {}
    with pytest.raises(sg.GateFail) as ei:
        sg.s2_create_case('tok', created)

    msg = str(ei.value)
    assert '样例音频缺失' in msg
    assert 'a.wav' in msg and 'b.wav' in msg
    # 任何写操作之前失败：registry 只留空列表默认值，不得有任何已登记资源 id
    assert created['api_cfg_ids'] == []
    assert created['audio_ids'] == []
    assert created['tc_ids'] == []
    assert created['group_ids'] == []
