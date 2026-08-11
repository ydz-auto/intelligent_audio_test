# -*- coding: utf-8 -*-
"""跨机器 HTTP 捕获代理 + DB api_url 自动改/回滚。

配置在 prod_capture/capture_config.env(各服务 IP/端口 + DB 连接)。
启动: 连后端 DB -> 备份匹配的 dimensions.api_url -> 改指向代理(PROXY_URL) -> 起代理转发到真实 eval_server。
停止(Ctrl-C/stop.flag): 代理停 -> 从备份回滚 api_url -> 拷后端日志 -> 打包 zip。
备份文件 api_url_backup.json 落在 CAPTURE_DIR,脚本崩溃也可用它手动恢复。

配置项见 capture_config.env;环境变量同名项可覆盖配置文件。

用法:
  cd D:\\work\\20260630
  # 1. 编辑 prod_capture\\capture_config.env 填真实 eval_server IP/端口 + DB 密码
  # 2. 启动(自动改 DB 指向代理)
  python prod_capture\\capture_proxy.py
  # 3. 在平台跑用例(维度 api_url 已自动指向代理)
  # 4. 停止: Ctrl-C 或建 stop.flag(自动回滚 DB)
"""
import os
import sys
import time
import json
import shutil
import zipfile
import pathlib
import datetime
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = pathlib.Path(__file__).resolve().parent
CONFIG_FILE = HERE / 'capture_config.env'
CAPTURE_DIR = pathlib.Path(os.environ.get('CAPTURE_DIR') or
                           (HERE / ('run_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))))
MAX_FIELD = int(os.environ.get('CAPTURE_MAX_FIELD', '8000'))
STOP_FLAG = None
HTTP_LOG = None


# ---------------------------------------------------------------- config
def _parse_env_file(path):
    d = {}
    if not path.exists():
        return d
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        d[k.strip()] = v.strip()
    return d


def load_config():
    cfg = _parse_env_file(CONFIG_FILE)
    # 环境变量覆盖配置文件
    for k in list(cfg.keys()):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    # DB 留空则读 backend/.env
    if not cfg.get('DB_HOST'):
        be = _parse_env_file(ROOT / 'Intelligent-Audio-TEST' / 'backend' / '.env')
        for k in ('DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'):
            if not cfg.get(k) and be.get(k):
                cfg[k] = be[k]
    cfg.setdefault('EVAL_SERVER_HOST', '')
    cfg.setdefault('EVAL_SERVER_PORT', '5001')
    cfg.setdefault('PROXY_LISTEN_PORT', '15001')
    cfg.setdefault('PROXY_URL', 'http://127.0.0.1:15001')
    cfg.setdefault('MATCH_HOST', cfg.get('EVAL_SERVER_HOST', ''))
    cfg.setdefault('BACKEND_APPLOG', 'Intelligent-Audio-TEST/logs/app.log')
    cfg.setdefault('BACKEND_STDOUT', '')
    return cfg


# ---------------------------------------------------------------- log
def dlog(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    try:
        with open(CAPTURE_DIR / 'proxy.log', 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def write_http(entry):
    entry['_t'] = time.strftime('%Y-%m-%d %H:%M:%S')
    entry['_pid'] = os.getpid()
    try:
        with open(HTTP_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------- DB repoint/restore
def _db_connect(cfg):
    import psycopg2
    return psycopg2.connect(host=cfg.get('DB_HOST') or 'localhost',
                            port=cfg.get('DB_PORT') or '5432',
                            user=cfg.get('DB_USER') or 'intelligent_audio_test',
                            password=cfg.get('DB_PASSWORD') or '',
                            dbname=cfg.get('DB_NAME') or 'intelligent_audio_test')


def backup_and_repoint(cfg):
    """备份匹配维度的 api_url 并改指向代理。返回 [(id, old_api_url), ...]。"""
    match = (cfg.get('MATCH_HOST') or '').strip()
    proxy_url = cfg['PROXY_URL']
    conn = _db_connect(cfg)
    cur = conn.cursor()
    if match:
        cur.execute("SELECT id, api_url FROM dimensions "
                    "WHERE api_url IS NOT NULL AND api_url <> '' AND api_url LIKE %s",
                    (f'%{match}%',))
    else:
        cur.execute("SELECT id, api_url FROM dimensions "
                    "WHERE api_url IS NOT NULL AND api_url <> ''")
    rows = [(r[0], r[1]) for r in cur.fetchall()]
    backup_path = CAPTURE_DIR / 'api_url_backup.json'
    backup_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    if not rows:
        dlog(f'!! 未匹配到 api_url 含 {match!r} 的维度(确认 MATCH_HOST 与 DB 里 api_url 一致);不改动')
        cur.close(); conn.close()
        return rows
    ids = [r[0] for r in rows]
    cur.execute("UPDATE dimensions SET api_url = %s WHERE id = ANY(%s)", (proxy_url, ids))
    conn.commit()
    cur.close(); conn.close()
    dlog(f'已备份 {len(rows)} 条 dimensions.api_url -> {backup_path}')
    dlog(f'已把这 {len(rows)} 条 api_url 改为 {proxy_url}')
    for i, u in rows[:5]:
        dlog(f'  dim {i}: {u}')
    if len(rows) > 5:
        dlog(f'  ... 共 {len(rows)} 条')
    return rows


def restore_from_backup(cfg, backup_path):
    """从备份文件回滚 api_url。"""
    if not backup_path.exists():
        dlog('无备份文件,跳过回滚')
        return
    rows = json.loads(backup_path.read_text(encoding='utf-8'))
    if not rows:
        dlog('备份为空,跳过回滚')
        return
    conn = _db_connect(cfg)
    cur = conn.cursor()
    for dim_id, old_url in rows:
        cur.execute("UPDATE dimensions SET api_url = %s WHERE id = %s", (old_url, dim_id))
    conn.commit()
    cur.close(); conn.close()
    dlog(f'已回滚 {len(rows)} 条 dimensions.api_url')
    try:
        backup_path.rename(backup_path.with_suffix('.json.restored'))
    except Exception:
        pass


# ---------------------------------------------------------------- proxy handler
def parse_multipart(content_type, body):
    out = []
    try:
        raw = b'Content-Type: ' + content_type.encode('utf-8') + b'\r\nMIME-Version: 1.0\r\n\r\n' + body
        from email.parser import BytesParser
        msg = BytesParser().parsebytes(raw)
        for part in msg.walk():
            if part.is_multipart():
                continue
            cd = part.get('Content-Disposition', '')
            name = filename = None
            for kv in cd.split(';'):
                kv = kv.strip()
                if kv.lower().startswith('name='):
                    name = kv[5:].strip().strip('"')
                elif kv.lower().startswith('filename='):
                    filename = kv[9:].strip().strip('"')
            payload = part.get_payload(decode=True) or b''
            out.append({'field': name, 'filename': filename, 'size': len(payload)})
    except Exception as e:
        out.append({'parse_error': repr(e)[:200]})
    return out


def summarize_request(content_type, body):
    sm = {}
    if body is None:
        return sm
    ct = (content_type or '').lower()
    if 'multipart/form-data' in ct:
        sm['multipart'] = parse_multipart(content_type, body)
    elif 'application/json' in ct:
        try:
            sm['json'] = json.dumps(json.loads(body), ensure_ascii=False, default=str)[:MAX_FIELD]
        except Exception:
            sm['text'] = body.decode('utf-8', 'replace')[:MAX_FIELD]
    elif 'x-www-form-urlencoded' in ct or 'text' in ct:
        try:
            sm['text'] = body.decode('utf-8', 'replace')[:MAX_FIELD]
        except Exception:
            sm['size'] = len(body)
    else:
        sm['size'] = len(body)
    return sm


def summarize_response(resp):
    sm = {'status': resp.status_code}
    ct = resp.headers.get('content-type', '')
    sm['resp_ct'] = ct
    if 'json' in ct.lower() or 'text' in ct.lower() or 'html' in ct.lower():
        try:
            sm['resp_body'] = resp.text[:MAX_FIELD]
        except Exception:
            sm['resp_size'] = len(resp.content)
    else:
        sm['resp_size'] = len(resp.content)
    return sm


HOP_BY_HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
              'te', 'trailers', 'transfer-encoding', 'upgrade'}
TARGET_HOST = ''
TARGET_PORT = ''


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _handle(self):
        if HTTP_LOG is None:
            self.send_error(503, 'proxy not ready'); return
        try:
            length = int(self.headers.get('Content-Length', 0))
        except Exception:
            length = 0
        body = self.rfile.read(length) if length > 0 else b''
        ct = self.headers.get('Content-Type', '')
        entry = {'direction': 'backend->eval(via proxy)', 'method': self.command,
                 'target': f'{TARGET_HOST}:{TARGET_PORT}', 'path': self.path.split('?')[0],
                 'query': self.path.split('?', 1)[1] if '?' in self.path else '', 'req_ct': ct}
        entry.update(summarize_request(ct, body))
        fwd_headers = {}
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP or k.lower() in ('content-length', 'host'):
                continue
            fwd_headers[k] = v
        url = f'http://{TARGET_HOST}:{TARGET_PORT}{self.path}'
        t0 = time.time()
        try:
            resp = requests.request(self.command, url, data=body if body else None,
                                    headers=fwd_headers, timeout=300)
            entry.update(summarize_response(resp))
        except Exception as e:
            entry['error'] = repr(e)[:500]
            entry['elapsed_ms'] = int((time.time() - t0) * 1000)
            write_http(entry)
            msg = repr(e).encode('utf-8')
            self.send_response(502); self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(msg))); self.end_headers()
            try: self.wfile.write(msg)
            except Exception: pass
            return
        entry['elapsed_ms'] = int((time.time() - t0) * 1000)
        write_http(entry)
        content = resp.content
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() in HOP_BY_HOP or k.lower() in ('content-length', 'content-encoding'):
                continue
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        try: self.wfile.write(content)
        except Exception: pass

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _handle

    def log_message(self, fmt, *args):
        pass


def collect_backend_logs(cfg):
    ap = pathlib.Path(cfg.get('BACKEND_APPLOG') or '')
    if ap and not ap.is_absolute():
        ap = ROOT / ap
    if ap.exists():
        try:
            shutil.copy2(ap, CAPTURE_DIR / 'backend_app.log'); dlog(f'已拷贝 {ap.name}')
        except Exception as e:
            dlog(f'拷贝 backend_app.log 失败: {e}')
    else:
        dlog(f'后端日志不存在: {ap}(跳过)')
    so = cfg.get('BACKEND_STDOUT') or ''
    if so:
        p = pathlib.Path(so)
        if not p.is_absolute():
            p = ROOT / p
        if p.exists():
            try:
                shutil.copy2(p, CAPTURE_DIR / 'backend_stdout.log'); dlog('已拷贝 backend_stdout.log')
            except Exception as e:
                dlog(f'拷贝 backend_stdout 失败: {e}')


def zip_capture():
    zip_path = HERE / ('capture_' + CAPTURE_DIR.name.replace('run_', '') + '.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in CAPTURE_DIR.iterdir():
            if f.is_file():
                z.write(f, f.name)
    dlog(f'打包完成: {zip_path}')
    return zip_path


def main():
    global HTTP_LOG, STOP_FLAG, TARGET_HOST, TARGET_PORT
    cfg = load_config()
    TARGET_HOST = cfg['EVAL_SERVER_HOST']
    TARGET_PORT = str(cfg['EVAL_SERVER_PORT'])
    listen_port = int(cfg['PROXY_LISTEN_PORT'])
    if not TARGET_HOST:
        print('!! capture_config.env 里 EVAL_SERVER_HOST 必填'); sys.exit(2)

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    HTTP_LOG = CAPTURE_DIR / 'http_requests.jsonl'
    HTTP_LOG.write_text('', encoding='utf-8')
    STOP_FLAG = CAPTURE_DIR / 'stop.flag'
    backup_path = CAPTURE_DIR / 'api_url_backup.json'

    dlog('=' * 64)
    dlog(f'捕获代理  listen=0.0.0.0:{listen_port}  -> {TARGET_HOST}:{TARGET_PORT}')
    dlog(f'CAPTURE_DIR={CAPTURE_DIR}')
    dlog('=' * 64)

    # 若存在上次崩溃残留备份,先回滚
    if backup_path.exists():
        dlog('!! 发现上次残留备份,先回滚 api_url 再开始')
        try:
            restore_from_backup(cfg, backup_path)
        except Exception as e:
            dlog(f'残留回滚失败(继续): {e}')

    # 启动:改 DB 指向代理
    repointed = 0
    try:
        rows = backup_and_repoint(cfg)
        repointed = len(rows)
    except Exception as e:
        dlog(f'!! DB 改指向失败: {e}\n{traceback.format_exc()}')
        dlog('代理仍会启动,但 DB api_url 未改 -> 需手动在平台改维度 api_url 指向 ' + cfg['PROXY_URL'])

    dlog('-' * 64)
    dlog(f'代理已就绪。去平台跑用例(已自动改 {repointed} 条维度 api_url 指向 {cfg["PROXY_URL"]})。')
    dlog('停止: Ctrl-C 或 创建 ' + str(STOP_FLAG) + '(自动回滚 DB)')
    dlog('-' * 64)

    server = ThreadingHTTPServer(('0.0.0.0', listen_port), ProxyHandler)
    server.daemon_threads = True
    import threading
    stop = threading.Event()

    def watch_stop():
        while not stop.is_set():
            if STOP_FLAG.exists():
                dlog('收到 stop.flag,停止...'); stop.set(); break
            time.sleep(2)
    threading.Thread(target=watch_stop, daemon=True).start()

    def serve():
        while not stop.is_set():
            server.handle_request()

    try:
        serve()
    except KeyboardInterrupt:
        dlog('Ctrl-C,停止...')
    except Exception as e:
        dlog('代理异常: ' + repr(e) + '\n' + traceback.format_exc())
    finally:
        stop.set()
        try: server.server_close()
        except Exception: pass
        # 回滚 DB
        try:
            restore_from_backup(cfg, backup_path)
        except Exception as e:
            dlog(f'!! 回滚失败: {e} -> 备份文件仍在 {backup_path},可手动恢复')
        collect_backend_logs(cfg)
        zip_capture()
        dlog('=' * 64)
        dlog(f'完成。日志目录: {CAPTURE_DIR}')
        dlog('分析: http_requests.jsonl(backend->eval) + backend_app.log + proxy.log')
        dlog('=' * 64)


if __name__ == '__main__':
    main()
