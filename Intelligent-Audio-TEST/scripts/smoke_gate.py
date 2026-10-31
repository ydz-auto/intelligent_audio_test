# -*- coding: utf-8 -*-
"""集成推送门禁·全栈冒烟四步断言（INT-314，INT-95 主链验收精简版）。

INT-95 附加条款移交：主链实机验收（7/7 步）通过后，把其精简版固化为集成工程师
每次批次推送前的标准门禁——【登录 → 建用例 → dry 执行 → 报告】四步断言。

设计要点（与 INT-246 隔离纪律 / INT-260 并行栈 / INT-182 裁判替身对齐）：

1. **目标栈 = 并行隔离栈（:6000，库 intelligent_audio_test_test）**，不是 :5000
   共享业务栈——本门禁含写操作（建用例/建任务/执行），写共享库即触碰 INT-246
   红线。:6000 栈跑的是磁盘检出代码（即待推送批次），与门禁语义一致；
   栈未起时经 tests/ui/utils/parallel_stack.py 自动拉起（WMI 脱离进程树），
   已起时直接复用（database 字段核验隔离库，拒绝误连共享库栈）。
2. **裁判兜底 = INT-182 收编替身**（mock_services/mock_eval_server_judge.py，
   :5097）：维度种子以 EVAL_SERVER_URL=http://127.0.0.1:5097 播种，评估出分
   不依赖外网真实裁判；:5097 已监听则复用常驻实例，未监听则本脚本自起子进程、
   结束时回收（只回收自己起的）。
3. **隔离数据自建自清**：全部资源（API 配置/音频/用例/任务/报告）挂唯一
   run tag 前缀（INT314SMOKE_<tag>_），**创建即登记**（每建成功一个立即写入
   created registry，中途失败也不丢已登记资源），finally 按 registry 全量
   清理（软删资源走 DELETE，与 tests/api/test_e2e_full_chain.py 同口径）；
   失败路径同样执行零残留终检，清理失败在结果中如实标注——绝不依赖
   reset_test_db.py 兜底（那是全量清库，会误伤并行验收数据）。
4. **四步断言**（任一步失败输出响应原文与定位，退出码 1；任何异常——含
   非 GateFail 逃逸——统一收敛进失败路径，保证 `--json` 恒输出含
   fail_detail/residue/tag，推送卡失败留证也是机器可读）：
   - S1 登录：GET /auth/login/encryption-key（白名单非 401）→ RSA-OAEP 前端
     同款加密 → POST /auth/login → access_token。
   - S2 建用例：上传 dry 样例音频（presign→OSS 直传→complete-direct）→
     创建 voice_llm API 用例（多轮 rounds + 逐轮维度绑定 turn_eval 主维度）。
   - S3 dry 执行：创建 mock 适配器（MockDialogAdapter，零外部依赖）API 配置 →
     建 api 任务并关联用例 → start → 轮询终态 → 断言执行+评估双 completed。
   - S4 报告：POST /reports/generate-task → 轮询 completed → 断言 summary。
5. 前置引导幂等：RBAC 种子（tests/ui/utils/bootstrap.py 口径）+ admin 自举 +
   voice_llm/turn_eval 维度种子（scripts/migrations seed 脚本，DATABASE_URI
   指向隔离库，幂等原地更新）——隔离库被 reset_test_db.py 清空后本门禁仍可
   一键自愈重建。
6. **前置：dry 样例 wav**（doc/voice_llm/样例/2026144010.wav、2026144019.wav）。
   `*.wav` 被 .gitignore 排除，全新检出/新 worktree 需先从主检出复制；缺失时
   S2 在任何写操作之前以 GateFail（带完整路径）失败，不产生残留。

用法（项目环境 python，仓库根执行）：
    python scripts/smoke_gate.py              # 四步门禁（自动确保栈/替身/种子）
    python scripts/smoke_gate.py --json       # 机器可读结果（供推送卡留证）
    python scripts/smoke_gate.py --keep-data  # 调试：保留冒烟数据（禁用于推送门禁）

退出码：0 四步全 PASS；1 任一步 FAIL（输出含失败步骤响应原文与定位）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import traceback
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import httpx  # noqa: E402
import psycopg2  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402

from shared.constants.database import ISOLATED_TEST_DB_NAME, SHARED_BUSINESS_DB_NAME  # noqa: E402

# ── 端口口径（tests/ui/utils/parallel_stack.py 的 +1000 偏移表）──────────
GATEWAY = 'http://127.0.0.1:6000'
API_BASE = f'{GATEWAY}/api/v1'
GATEWAY_HTTP = 6000
MOCK_JUDGE_PORT = 5097
CK = dict(timeout=30, trust_env=False)  # trust_env=False：Windows 代理劫持规避（INT-102）
_CK_PROBE = dict(trust_env=False)  # 探测专用（可自定义 timeout）

SAMPLE_DIR = os.path.join(PROJECT_ROOT, 'doc', 'voice_llm', '样例')
# dry 样例取 2 个（2 轮用例，覆盖多轮 session + 整体评估 per_round 形态）
SAMPLE_AUDIO_FILES = ['2026144010.wav', '2026144019.wav']

TAG = f'INT314SMOKE_{secrets.token_hex(4)}'
PY = sys.executable


class GateFail(Exception):
    """四步断言失败（携带定位与响应原文）。"""


# ── 结果记录 ──────────────────────────────────────────────────────────
_STEPS: list = []  # (step, ok, detail)


def step(name, ok, detail=''):
    _STEPS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f' — {detail}' if detail else ''))
    if not ok:
        raise GateFail(f'{name}: {detail}')


def resp_data(r):
    """解包统一信封 {success, code, data}；非 2xx/失败信封抛 GateFail 带原文。"""
    try:
        body = r.json()
    except ValueError:
        raise GateFail(f'HTTP {r.status_code} 非 JSON 响应: {r.text[:400]}')
    if r.status_code >= 400 or not (body.get('success') or body.get('code') in (0, 200, 201)):
        raise GateFail(f'HTTP {r.status_code}: {json.dumps(body, ensure_ascii=False)[:400]}')
    return body.get('data') or {}


def _exc_detail(e) -> str:
    """非 GateFail 异常 → 含定位的失败原文（type: message @ file:line）。

    保证任何异常逃逸都能在 --json 的 fail_detail 里给出「原文 + 定位」
    （验收标准 1/3），而不是只剩裸 traceback。
    """
    tb = e.__traceback__
    loc = ''
    if tb is not None:
        frames = traceback.extract_tb(tb)
        if frames:
            last = frames[-1]
            loc = f'{os.path.basename(last.filename)}:{last.lineno}'
    return f'{type(e).__name__}: {e}' + (f' @ {loc}' if loc else '')


# ── 前置 0a：并行隔离栈（复用或拉起）────────────────────────────────
def _port_open(port, timeout=0.8):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(('127.0.0.1', port)) == 0


def _gw_health():
    try:
        r = httpx.get(f'{GATEWAY}/health', timeout=3, **_CK_PROBE)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def ensure_stack() -> dict:
    """栈已隔离 → 复用；未起 → parallel_stack.py start（WMI 脱离进程树，常驻）。"""
    body = _gw_health()
    if body:
        db = body.get('database', '')
        if db == SHARED_BUSINESS_DB_NAME:
            raise GateFail(
                f':{GATEWAY_HTTP} 是共享业务库栈（database={db}），本门禁含写操作，'
                f'拒绝执行（INT-246 红线）。请以 python tests/ui/utils/parallel_stack.py '
                f'start 另起并行隔离栈，或先排查端口占用。')
        if db != ISOLATED_TEST_DB_NAME:
            raise GateFail(f':{GATEWAY_HTTP} /health database={db!r} 非隔离库，拒绝误连。')
        print(f'[前置] 复用并行隔离栈 :{GATEWAY_HTTP}（database={db}）')
        return body
    launcher = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'utils', 'parallel_stack.py')
    print(f'[前置] 并行隔离栈未起，WMI 脱离进程树启动（首次约 1-2 分钟）...')
    ps = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
        f"CommandLine = 'cmd.exe /c \"\"{PY}\"\" \"{launcher}\" start\"';"
        f"CurrentDirectory = '{PROJECT_ROOT}'"
        "}; $r.ReturnValue"
    )
    subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                   capture_output=True, text=True, timeout=30)
    deadline = time.time() + 180
    while time.time() < deadline:
        body = _gw_health()
        if body and body.get('database') == ISOLATED_TEST_DB_NAME:
            print(f'[前置] 隔离栈已就绪 :{GATEWAY_HTTP}')
            return body
        time.sleep(3)
    raise GateFail(f'隔离栈 180s 未就绪（详见 logs/ui_stack/ui_stack.log）。'
                   f'手动检查: python tests/ui/utils/parallel_stack.py status')


# ── 前置 0b：裁判替身 :5097（复用常驻或自起自收）────────────────────
def ensure_judge() -> tuple:
    """返回 (proc_or_None, reused: bool)。proc 非 None 时由调用方负责回收。"""
    if _port_open(MOCK_JUDGE_PORT):
        try:
            r = httpx.get(f'http://127.0.0.1:{MOCK_JUDGE_PORT}/health', timeout=3, **_CK_PROBE)
            if r.status_code == 200 and 'mock_eval_server_judge' in r.text:
                print(f'[前置] 复用常驻裁判替身 :{MOCK_JUDGE_PORT}')
                return None, True
        except Exception:
            pass
        raise GateFail(f':{MOCK_JUDGE_PORT} 被非裁判替身进程占用，拒绝误连。')
    proc = subprocess.Popen(
        [PY, os.path.join(PROJECT_ROOT, 'mock_services', 'mock_eval_server_judge.py')],
        cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        if _port_open(MOCK_JUDGE_PORT):
            print(f'[前置] 裁判替身已自起 :{MOCK_JUDGE_PORT}（pid {proc.pid}，结束回收）')
            return proc, False
        time.sleep(1)
    proc.terminate()
    raise GateFail(f'裁判替身 :{MOCK_JUDGE_PORT} 30s 未就绪。')


# ── 前置 0c：隔离库引导（RBAC + admin + voice_llm/turn_eval 种子）────
def _isolated_db_url() -> str:
    from urllib.parse import urlsplit, urlunsplit
    env_path = os.path.join(PROJECT_ROOT, '.env')
    url = ''
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    url = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        url = os.environ.get('DATABASE_URL', '')
    parts = urlsplit(url)
    if not parts.scheme.startswith('postgres'):
        raise GateFail(f'.env DATABASE_URL 非 Postgres，无法推导隔离库连接串: {url!r}')
    return urlunsplit((parts.scheme, parts.netloc, '/' + ISOLATED_TEST_DB_NAME, '', ''))


def _seeded(url: str, table: str, where: str) -> bool:
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {table} WHERE {where}')
            return (cur.fetchone()[0] or 0) > 0
    finally:
        conn.close()


def _run_seed(script_rel: str, url: str) -> None:
    env = dict(os.environ)
    env['DATABASE_URI'] = url          # seed 脚本只读 DATABASE_URI，防串库歧义
    env.pop('DATABASE_URL', None)
    env['EVAL_SERVER_URL'] = f'http://127.0.0.1:{MOCK_JUDGE_PORT}'
    env['PYTHONUTF8'] = '1'
    proc = subprocess.run([PY, os.path.join(PROJECT_ROOT, script_rel)],
                          cwd=PROJECT_ROOT, env=env, capture_output=True,
                          text=True, timeout=180,
                          input='y\n')  # seed_voice_llm 有交互确认，管道喂 y
    if proc.returncode != 0:
        raise GateFail(f'{script_rel} 失败（exit {proc.returncode}）:\n'
                       f'{proc.stdout[-500:]}\n{proc.stderr[-500:]}')


def bootstrap_db(url: str) -> None:
    """RBAC 种子 + admin 自举 + voice_llm/turn_eval 维度种子（全部幂等）。"""
    from tests.ui.utils import bootstrap  # 复用 INT-260 口径（含 seed_rbac 播放）
    if not bootstrap.roles_seeded(url):
        bootstrap.seed_rbac(url)
        print('[前置] RBAC 种子完成')

    # voice_llm 算法定义（audio 用例与执行依赖 algorithm_definitions/device_params）
    if not _seeded(url, 'algorithm_definitions', "type='voice_llm' AND deleted=FALSE"):
        _run_seed(os.path.join('scripts', 'migrations', '202609', 'seed_voice_llm.py'), url)
        print('[前置] seed_voice_llm 完成')

    # turn_eval 维度族（seed 幂等；主维度 UPDATE 会刷新 api_url，子维度不刷）
    if not _seeded(url, 'dimensions', "task_type_code='turn_eval' AND deleted=FALSE"):
        _run_seed(os.path.join('scripts', 'migrations', '202610', 'seed_turn_eval.py'), url)
        print('[前置] seed_turn_eval 完成')

    # 维度端点归位：隔离库维度可能残留旧替身端口（:18888 等历史轮端口），统一
    # 指向当前裁判替身 :5097（INT-182 口径）。仅写隔离库，幂等。
    judge_url = f'http://127.0.0.1:{MOCK_JUDGE_PORT}'
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE dimensions SET api_url=%s, updated_at=NOW() '
                        "WHERE deleted=FALSE AND api_url IS DISTINCT FROM %s "
                        "AND (api_url LIKE 'http://127.0.0.1:%%' OR api_url LIKE 'http://localhost:%%')",
                        (judge_url, judge_url))
            fixed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if fixed:
        print(f'[前置] {fixed} 个维度端点归位 → {judge_url}')

    # admin 账号（空库首注册即 admin 角色；已存在则直接复用）
    from tests.ui.utils.api_client import ApiClient
    api = ApiClient(GATEWAY)
    try:
        api.login('admin', 'admin123')
    except Exception:
        api.register('admin', 'admin123')
        api.login('admin', 'admin123')
    print('[前置] admin 账号可登录（bootstrap 完成）')


# ══════════════════════════════════════════════════════════════════════
# 四步断言
# ══════════════════════════════════════════════════════════════════════

# ── S1 登录（前端 LoginPage 同款 RSA-OAEP 姿势）──────────────────────
def encryption_key() -> dict:
    r = httpx.get(f'{API_BASE}/auth/login/encryption-key', **CK)
    # 白名单断言：无 token 必须非 401（401 = 白名单断裂，登录链路前端必炸）
    if r.status_code == 401:
        raise GateFail('GET /auth/login/encryption-key 返回 401（公钥下发应在白名单）')
    r.raise_for_status()
    return r.json()


def encrypt_pw(password: str, doc: dict) -> dict:
    key = serialization.load_pem_public_key(doc['public_key'].encode())
    ct = key.encrypt(password.encode(),
                     padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                  algorithm=hashes.SHA256(), label=None))
    return {'password_encrypted': base64.b64encode(ct).decode(),
            'encryption_key_id': doc['kid']}


def s1_login() -> str:
    doc = encryption_key()
    if not doc.get('enabled'):
        raise GateFail(f'加密登录未启用（encryption-key 响应: {json.dumps(doc)[:200]}）')
    r = httpx.post(f'{API_BASE}/auth/login',
                   json={'username': 'admin', **encrypt_pw('admin123', doc)}, **CK)
    # /auth/login 直接返回 {access_token, user}（非统一信封），兼容信封形态
    body = r.json() if r.status_code == 200 else {}
    tok = body.get('access_token') or (body.get('data') or {}).get('access_token') or ''
    if r.status_code != 200 or not tok:
        raise GateFail(f'登录失败 HTTP {r.status_code}: {r.text[:400]}')
    step('S1 登录（encryption-key 白名单 + RSA-OAEP 提交）', True,
         f"token_len={len(tok)} kid={doc.get('kid', '')[:12]}")
    return tok


def H(token):
    return {'Authorization': f'Bearer {token}'}


# ── S2 建用例（上传 dry 样例 → voice_llm API 用例，多轮 + 维度绑定）──
def s2_create_case(token: str, created: dict) -> dict:
    """创建即登记（INT-314 验收 P1 修复）：每建成功一个资源立即写入传入的
    created registry，调用方 main 的 finally 据此全量清理——即使函数中途
    失败，已登记资源也不会丢（不再依赖函数返回后才登记）。

    返回同一 created（内容含 api_cfg_id/audio_ids/group_ids/tc_id 等）。
    """
    created.setdefault('audio_ids', [])
    created.setdefault('tc_ids', [])
    created.setdefault('api_cfg_ids', [])
    created.setdefault('group_ids', [])

    # 0. 前置：dry 样例 wav 缺失检查（INT-314 验收 P3）——在任何写操作之前
    #    失败，带完整路径定位。*.wav 被 .gitignore 排除，全新检出/新 worktree
    #    需先从主检出复制到 doc/voice_llm/样例/。
    missing = [os.path.join(SAMPLE_DIR, name) for name in SAMPLE_AUDIO_FILES
               if not os.path.isfile(os.path.join(SAMPLE_DIR, name))]
    if missing:
        raise GateFail(
            'dry 样例音频缺失（前置：doc/voice_llm/样例/ 需存在 dry wav，'
            '*.wav 被 .gitignore 排除不随检出带入，请从主检出复制）: '
            + '; '.join(missing))

    h = H(token)

    # turn_eval 主维度（bootstrap 播种的维度族，api_url 已指 :5097）
    conn = psycopg2.connect(_isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM dimensions WHERE task_type_code='turn_eval' "
                        "AND deleted=FALSE ORDER BY id LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise GateFail('turn_eval 主维度未种子化（bootstrap 失败？）')
    turn_eval_dim_id = row[0]

    # 0a. mock 适配器 API 配置（api 任务执行走 MockDialogAdapter，零外部依赖）
    r = httpx.post(f'{API_BASE}/apis', headers=h, **CK,
                   json={'name': f'{TAG}_mock_api',
                         'vendor': 'mock', 'description': 'INT-314 冒烟门禁 mock 适配器',
                         'algorithm_type': 'voice_llm',
                         # INT-1799：写侧 device_type 已废弃（一律 400），
                         # 改用协议 / 流式性正交两维（与 INT-2198 门禁同口径）
                         'protocol': 'http', 'streaming': False,
                         'adapter_class': 'MockDialogAdapter', 'status': 'online',
                         'meta': {'purpose': 'int314-smoke-gate', 'mode': 'dialog'}})
    api_cfg_id = resp_data(r).get('id')
    if not api_cfg_id:
        raise GateFail(f'API 配置创建失败: {r.text[:300]}')
    created['api_cfg_ids'].append(api_cfg_id)

    # 0b. 上传 dry 样例音频（presign → OSS 直传 → complete-direct）
    files = []
    for name in SAMPLE_AUDIO_FILES:
        p = os.path.join(SAMPLE_DIR, name)
        if not os.path.isfile(p):
            raise GateFail(f'样例音频缺失: {p}')
        with open(p, 'rb') as f:
            files.append({'path': p, 'name': name, 'size': os.path.getsize(p),
                          'md5': hashlib.md5(f.read()).hexdigest(),
                          'relativePath': f'sample/{name}'})

    r = httpx.post(f'{API_BASE}/audios/upload/init', headers=h, **CK)
    upload_task_id = resp_data(r).get('taskId') or resp_data(r).get('task_id')
    if not upload_task_id:
        raise GateFail(f'upload/init 未返回 taskId: {r.text[:300]}')

    r = httpx.post(f'{API_BASE}/audios/upload/register', headers=h, **CK,
                   json={'taskId': upload_task_id,
                         'files': [{'name': f['name'], 'size': f['size'], 'md5': f['md5'],
                                    'relativePath': f['relativePath']} for f in files]})
    reg = resp_data(r).get('files', [])
    if len(reg) != len(files):
        raise GateFail(f'register 文件数不符: {r.text[:300]}')
    file_ids = [rf.get('fileId') or rf.get('file_id') for rf in reg]

    for idx, (f, fid) in enumerate(zip(files, file_ids)):
        r = httpx.post(f'{API_BASE}/audios/upload/presign', headers=h, **CK,
                       json={'filename': f['name'], 'fileSize': f['size'],
                             'md5': f['md5'], 'chunkSize': 5 * 1024 * 1024,
                             'isWav': True, 'relativePath': f['relativePath']})
        pres = resp_data(r)
        audio_id = None
        if pres.get('instantUpload'):
            audio_id = pres.get('audioId') or pres.get('audio_id')
        else:
            up_id = pres.get('uploadId') or pres.get('upload_id')
            oss_key = pres.get('ossKey') or pres.get('oss_key')
            parts = pres.get('parts', [])
            total_parts = pres.get('totalParts') or pres.get('total_parts', 1)
            uploaded = []
            for pi in range(total_parts):
                if pi < len(parts):
                    purl = parts[pi].get('url') or parts[pi].get('URL')
                else:
                    rr = httpx.post(f'{API_BASE}/audios/upload/presign-part', headers=h, **CK,
                                    json={'uploadId': up_id, 'partNumber': pi + 1},
                                    params={'oss_key': oss_key,
                                            'category': pres.get('category', 'audios')})
                    purl = resp_data(rr).get('url')
                with open(f['path'], 'rb') as fh:
                    pr = httpx.put(purl, content=fh.read(), **{**CK, 'timeout': 60})
                if pr.status_code != 200:
                    raise GateFail(f'OSS PUT {pr.status_code}: {pr.text[:200]}')
                uploaded.append({'PartNumber': pi + 1,
                                 'ETag': pr.headers.get('ETag', '').strip('"')})
            r = httpx.post(f'{API_BASE}/audios/upload/complete-direct', headers=h, **CK,
                           json={'ossKey': oss_key, 'uploadId': up_id, 'parts': uploaded,
                                 'filename': f['name'], 'md5': f['md5'],
                                 'fileSize': f['size'], 'audioType': 'dry'})
            audio_id = resp_data(r).get('audioId') or resp_data(r).get('audio_id')
        if not audio_id:
            raise GateFail(f'音频 {f["name"]} 未获得 audioId: {r.text[:300]}')
        created['audio_ids'].append(audio_id)

        # merge 归档（不自动建用例，用例在下方显式创建以便绑定维度）
        r = httpx.post(f'{API_BASE}/audios/upload/merge', headers=h, **CK,
                       json={'fileId': fid, 'taskId': upload_task_id,
                             'audioType': 'dry', 'createTestCase': False,
                             'inheritTags': True, 'dimensions': {}})
        md = resp_data(r)
        if md.get('status') != 'completed' and not md.get('audioId'):
            raise GateFail(f'merge 未完成: {json.dumps(md, ensure_ascii=False)[:300]}')

    # 0b-1. 用例分组（testcases 创建要求 group_id）
    r = httpx.post(f'{API_BASE}/groups', headers=h, **CK,
                   json={'name': f'{TAG}_组'})
    grp_id = resp_data(r).get('id')
    if not grp_id:
        raise GateFail(f'分组创建失败: {r.text[:300]}')
    created['group_ids'].append(grp_id)

    # 0c. 创建 voice_llm API 用例：2 轮 × (dry 音频 + turn_eval 主维度)
    rounds = [{'round_number': i + 1,
               'audios': [{'audio_id': aid, 'spl': 65, 'play_order': 1}],
               'evaluation': {'dimensions': [{'id': turn_eval_dim_id, 'name': '逐轮话轮评估'}]}}
              for i, aid in enumerate(created['audio_ids'])]
    r = httpx.post(f'{API_BASE}/testcases', headers=h, **CK,
                   json={'name': f'{TAG}_API用例',
                         'description': 'INT-314 冒烟门禁用例（自建自清）',
                         'algorithm_type': 'voice_llm',
                         'group_id': grp_id,
                         'config': {'rounds': rounds}})
    tc = resp_data(r)
    tc_id = tc.get('id') or tc.get('case_id')
    if not tc_id:
        raise GateFail(f'用例创建失败: {r.text[:400]}')
    created['tc_ids'].append(tc_id)
    step('S2 建用例（dry 样例上传 + voice_llm API 用例 + turn_eval 维度绑定）', True,
         f'audio={created["audio_ids"]} tc={tc_id}')
    created['tc_id'] = tc_id
    created['api_cfg_id'] = api_cfg_id
    return created


# ── S3 dry 执行（api 任务 + MockDialogAdapter → 终态 → 执行/评估双断言）
def s3_execute(token: str, created: dict) -> int:
    h = H(token)
    tc_id = created['tc_id']
    r = httpx.post(f'{API_BASE}/tasks', headers=h, **CK,
                   json={'name': f'{TAG}_任务', 'type': 'api',
                         'description': 'INT-314 冒烟门禁 dry 执行',
                         'case_ids': [tc_id],
                         'api_ids': [created['api_cfg_id']]})
    task_id = resp_data(r).get('id')
    if not task_id:
        raise GateFail(f'任务创建失败: {r.text[:400]}')
    created['task_id'] = task_id

    r = httpx.patch(f'{API_BASE}/tasks/{task_id}/cases', headers=h, **CK,
                    json={'action': 'add', 'caseIds': [tc_id],
                          'caseDevices': [{'caseId': tc_id,
                                           'deviceType': 'http_api',
                                           'deviceId': str(created['api_cfg_id'])}]})
    resp_data(r)

    r = httpx.post(f'{API_BASE}/tasks/{task_id}/start', headers=h, **CK)
    resp_data(r)

    deadline = time.time() + 420
    final_status = None
    while time.time() < deadline:
        rr = httpx.get(f'{API_BASE}/tasks/{task_id}/progress', headers=h, **CK)
        final_status = (resp_data(rr).get('status') or '').lower()
        if final_status in ('completed', 'failed', 'cancelled', 'stopped',
                            'partial_completed'):
            break
        time.sleep(3)
    if final_status not in ('completed', 'partial_completed'):
        raise GateFail(f'任务 {task_id} 未到完成终态（final={final_status}，420s 超时）。'
                       f'排查: GET {API_BASE}/tasks/{task_id}/progress 与 logs/ui_stack/')

    # 复合断言：执行 + 评估双 completed（读 task_case_relations，防「执行完成
    # 评估空转」的假绿——INT-126 之前的口径盲区）
    conn = psycopg2.connect(_isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT execution_status, evaluation_status FROM task_case_relations '
                        'WHERE task_id=%s AND test_case_id=%s', (task_id, str(tc_id)))
            row = cur.fetchone()
            cur.execute('SELECT count(*) FROM test_results WHERE task_id=%s', (task_id,))
            result_count = cur.fetchone()[0]
    finally:
        conn.close()
    if not row:
        raise GateFail(f'任务 {task_id} 未找到用例关系行（用例未真正分发执行）')
    exec_st, eval_st = row
    if result_count < 1:
        raise GateFail(f'任务 {task_id} 无 test_results 行（执行链未落结果）')
    if (exec_st or '').lower() != 'completed' or (eval_st or '').lower() != 'completed':
        raise GateFail(f'任务 {task_id} 用例链状态异常: execution={exec_st} '
                       f'evaluation={eval_st}（dry 执行或评估链断裂）')
    step('S3 dry 执行（mock 适配器 api 任务 → 终态）', True,
         f'task={task_id} exec={exec_st} eval={eval_st} results={result_count}')
    return task_id


# ── S4 报告（generate-task 异步 → completed + summary 断言）──────────
def s4_report(token: str, created: dict) -> int:
    h = H(token)
    task_id = created['task_id']
    r = httpx.post(f'{API_BASE}/reports/generate-task', headers=h, **CK,
                   json={'taskId': task_id, 'name': f'{TAG}_报告',
                         'description': 'INT-314 冒烟门禁报告'})
    gd = resp_data(r)
    report_id = gd.get('reportId') or gd.get('report_id') or gd.get('id')
    deadline = time.time() + 180
    report = None
    while time.time() < deadline:
        if not report_id:
            rr = httpx.get(f'{API_BASE}/reports/by_task/{task_id}', headers=h, **CK)
            if rr.status_code == 200:
                try:
                    report_id = resp_data(rr).get('id')
                except GateFail:
                    report_id = None
            time.sleep(3)
            continue
        rr = httpx.get(f'{API_BASE}/reports/{report_id}', headers=h, **CK)
        report = resp_data(rr)
        if report.get('status') in ('completed', 'failed', 'published'):
            break
        time.sleep(3)
    if not report_id:
        raise GateFail(f'报告未生成（generate-task 响应: {json.dumps(gd, ensure_ascii=False)[:300]}）')
    if not report or report.get('status') not in ('completed', 'published'):
        st = report.get('status') if report else 'unknown'
        raise GateFail(f'报告 {report_id} 未达完成终态（status={st}，180s 超时）。'
                       f'排查: GET {API_BASE}/reports/{report_id} 与 report_service 日志')
    summary = report.get('summary') or {}
    if not isinstance(summary, dict) or not summary:
        raise GateFail(f'报告 {report_id} summary 为空: {json.dumps(summary, ensure_ascii=False)[:200]}')
    created['report_id'] = report_id
    step('S4 报告（generate-task → 完成终态 + summary）', True,
         f'report={report_id} status={report.get("status")} summary_keys={len(summary)}')
    return report_id


# ── 清理（自建自清；失败不掩盖主流程结果，只如实标注）────────────────
def cleanup(token: str, created: dict) -> list:
    h = H(token)
    residue = []
    if created.get('report_id'):
        try:
            httpx.delete(f'{API_BASE}/reports/{created["report_id"]}', headers=h, **CK)
        except Exception as e:
            residue.append(f'report {created["report_id"]}: {e}')
    if created.get('task_id'):
        try:
            httpx.delete(f'{API_BASE}/tasks/{created["task_id"]}', headers=h, **CK)
        except Exception as e:
            residue.append(f'task {created["task_id"]}: {e}')
    for tc_id in created.get('tc_ids', []):
        try:
            httpx.delete(f'{API_BASE}/testcases/{tc_id}', headers=h, **CK)
        except Exception as e:
            residue.append(f'tc {tc_id}: {e}')
    for aid in created.get('audio_ids', []):
        try:
            httpx.delete(f'{API_BASE}/audios/{aid}', headers=h, **CK)
        except Exception as e:
            residue.append(f'audio {aid}: {e}')
    for api_id in created.get('api_cfg_ids', []):
        try:
            httpx.delete(f'{API_BASE}/apis/{api_id}', headers=h, **CK)
        except Exception as e:
            residue.append(f'api_cfg {api_id}: {e}')
    for gid in created.get('group_ids', []):
        try:
            httpx.delete(f'{API_BASE}/groups/{gid}', headers=h, **CK)
        except Exception as e:
            residue.append(f'group {gid}: {e}')
    return residue


def residue_check() -> list:
    """数据零残留终检：按 run tag 扫隔离库全部冒烟触达表（未被清理 API
    覆盖到的行——软删语义不计残留，发布任务/任务报告含 tag 即漏网）。"""
    residue = []
    conn = None
    try:
        conn = psycopg2.connect(_isolated_db_url(), connect_timeout=5)
        with conn.cursor() as cur:
            for table, col, live in [('test_tasks', 'name', 'deleted=FALSE'),
                                     ('test_cases', 'name', 'deleted=FALSE'),
                                     ('apis', 'name', 'deleted=FALSE'),
                                     ('test_case_groups', 'name', 'deleted=FALSE'),
                                     ('test_reports', 'name', 'deleted=FALSE'),
                                     ('published_tasks', 'name', "status<>'archived'")]:
                try:
                    cur.execute(f'SELECT id FROM {table} WHERE {col} LIKE %s AND {live}',
                                (f'%{TAG}%',))
                    for (row_id,) in cur.fetchall():
                        residue.append(f'{table}:{row_id}')
                except psycopg2.Error:
                    conn.rollback()
    except Exception as e:
        residue.append(f'residue_check 异常: {e}')
    finally:
        if conn:
            conn.close()
    return residue


# ══════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description='INT-314 集成推送门禁·四步冒烟断言')
    parser.add_argument('--json', action='store_true', help='输出 JSON（供推送卡留证）')
    parser.add_argument('--keep-data', action='store_true',
                        help='调试保留冒烟数据（推送门禁禁用——数据零残留是验收标准）')
    args = parser.parse_args()

    judge_proc = None
    created = {}
    token = ''
    exit_code = 0
    fail_detail = ''
    residue = []
    try:
        ensure_stack()
        judge_proc, _reused = ensure_judge()
        bootstrap_db(_isolated_db_url())

        try:
            token = s1_login()
            s2_create_case(token, created)   # 创建即登记：中途失败已登记资源不丢（P1）
            s3_execute(token, created)
            s4_report(token, created)
        except GateFail as e:
            exit_code = 1
            fail_detail = str(e)
        except Exception as e:
            # 非 GateFail 异常（如 AssertionError）也收敛进失败路径，保证
            # --json 恒输出（验收标准 1/3 留证契约），并带 file:line 定位
            exit_code = 1
            fail_detail = f'异常逃逸（已收敛）: {_exc_detail(e)}'
        finally:
            if not args.keep_data:
                residue = cleanup(token, created)

        print()
        passed = sum(1 for _, ok, _ in _STEPS if ok)
        total = len(_STEPS)
        # 零残留终检：成功与失败路径都执行（验收 P1 修复点）；--keep-data 调试除外
        if not args.keep_data:
            leftover = residue_check()
            if leftover:
                exit_code = 1
                note = f'数据残留（零残留终检不满足，可按 tag {TAG} 手动清理后复跑）: {leftover}'
                fail_detail = note if not fail_detail else f'{fail_detail}；{note}'
        if residue:
            exit_code = 1
            note = f'清理失败（未删资源，可按 tag {TAG} 手动清理后复跑）: {residue}'
            fail_detail = note if not fail_detail else f'{fail_detail}；{note}'
        print(f'==== INT-314 冒烟门禁: {passed}/{total} 步 PASS '
              f'{"—— 门禁通过，可推送" if exit_code == 0 else "—— 门禁不通过，暂停推送"} ====')
        if exit_code != 0:
            print(f'失败定位: {fail_detail}')
        if args.keep_data and exit_code == 0:
            print(f'[--keep-data] 冒烟数据已保留（tag={TAG}），推送门禁禁用此选项')
    except GateFail as e:
        # 前置失败（栈/替身/引导）——一步未跑即中止
        exit_code = 1
        fail_detail = f'前置失败: {e}'
        print(f'[FAIL] {fail_detail}')
        print('==== INT-314 冒烟门禁: 前置失败 —— 门禁不通过，暂停推送 ====')
    except Exception as e:
        # 前置阶段非 GateFail 异常同样收敛（--json 恒输出）
        exit_code = 1
        fail_detail = f'前置异常: {_exc_detail(e)}'
        print(f'[FAIL] {fail_detail}')
        print('==== INT-314 冒烟门禁: 前置异常 —— 门禁不通过，暂停推送 ====')
    finally:
        if judge_proc is not None:
            try:
                judge_proc.terminate()
                judge_proc.wait(timeout=10)
                print(f'[收尾] 自起裁判替身已回收（pid {judge_proc.pid}）')
            except Exception as e:
                print(f'[收尾][WARN] 裁判替身回收异常（请手动检查 :{MOCK_JUDGE_PORT}）: {e}')

    if args.json:
        print(json.dumps({
            'gate': 'INT-314', 'pass': exit_code == 0,
            'steps': [{'step': n, 'ok': ok, 'detail': d} for n, ok, d in _STEPS],
            'fail_detail': fail_detail, 'residue': residue, 'tag': TAG,
        }, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
