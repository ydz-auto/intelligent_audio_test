# -*- coding: utf-8 -*-
"""全链路 HTTP 出站请求捕获（sitecustomize，随 Python 启动自动加载）。

被 run_capture.py 通过 PYTHONPATH 注入到 后端/eval_server/asr_server 进程。
patch requests.Session.request / httpx.Client.request / httpx.AsyncClient.request，
把每次出站 HTTP 的 method/url/请求体摘要/响应状态/响应体摘要 写成 JSONL 到 IAT_HTTP_LOG。

覆盖链路: 后端 ->eval_server(后端出站) ; eval_server ->asr_server/LLM judge(eval_server出站)。
asr_server 是叶节点、无出站,注入它无害。
wav 等二进制 body 只记大小/字段名,不记内容;auth 头脱敏。
"""
import os, json, time, traceback

_HTTP_LOG = os.environ.get('IAT_HTTP_LOG')
_SVC = os.environ.get('IAT_SERVICE', 'svc')
_MAX = 8000  # 单字段截断长度


def _write(entry):
    if not _HTTP_LOG:
        return
    entry['_t'] = time.strftime('%Y-%m-%d %H:%M:%S')
    entry['_svc'] = _SVC
    entry['_pid'] = os.getpid()
    try:
        with open(_HTTP_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass


def _fsize(fobj):
    try:
        if hasattr(fobj, 'len'):
            return fobj.len
        if hasattr(fobj, 'seek') and hasattr(fobj, 'tell'):
            cur = fobj.tell(); fobj.seek(0, 2); sz = fobj.tell(); fobj.seek(cur)
            return sz
    except Exception:
        pass
    return '?'


def _summarize_req(kwargs):
    sm = {}
    if kwargs.get('json') is not None:
        try:
            sm['req_json'] = json.dumps(kwargs['json'], ensure_ascii=False, default=str)[:_MAX]
        except Exception:
            sm['req_json'] = str(kwargs['json'])[:_MAX]
    if kwargs.get('data') is not None:
        d = kwargs['data']
        sm['req_data'] = ({k: str(v)[:300] for k, v in d.items()} if isinstance(d, dict)
                          else str(d)[:_MAX])
    if kwargs.get('files'):
        fl = []
        for item in (kwargs['files'] or []):
            try:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    field = item[0]; fn = item[1]; fobj = item[2] if len(item) > 2 else None
                    fl.append({'field': str(field), 'name': str(fn), 'size': _fsize(fobj) if fobj else '?'})
                else:
                    fl.append(str(item)[:200])
            except Exception:
                fl.append('<?>')
        sm['req_files'] = fl
    if kwargs.get('params'):
        sm['req_params'] = str(kwargs['params'])[:500]
    headers = kwargs.get('headers') or {}
    sm['req_headers'] = {k: ('<redacted>' if ('auth' in k.lower() or 'key' in k.lower())
                            else str(v)[:200]) for k, v in headers.items()}
    return sm


def _summarize_resp(resp, entry):
    try:
        entry['status'] = resp.status_code
        ct = (resp.headers.get('content-type') or '')
        entry['resp_ct'] = ct
        if 'json' in ct.lower() or 'text' in ct.lower() or 'html' in ct.lower():
            try:
                entry['resp_body'] = resp.text[:_MAX]
            except Exception:
                pass
        else:
            try:
                entry['resp_size'] = len(resp.content)
            except Exception:
                pass
    except Exception:
        pass


def _patch_requests():
    try:
        import requests
        if getattr(requests.Session.request, '_iat_patched', False):
            return
        orig = requests.Session.request

        def wrapped(self, method, url, **kwargs):
            entry = {'direction': 'out', 'lib': 'requests', 'method': method, 'url': url}
            entry.update(_summarize_req(kwargs))
            t0 = time.time()
            try:
                resp = orig(self, method, url, **kwargs)
                _summarize_resp(resp, entry)
                return resp
            except Exception as e:
                entry['error'] = repr(e)[:500]
                raise
            finally:
                entry['elapsed_ms'] = int((time.time() - t0) * 1000)
                _write(entry)

        wrapped._iat_patched = True
        requests.Session.request = wrapped
    except Exception:
        pass


def _patch_httpx():
    try:
        import httpx
    except Exception:
        return
    for cls_name, is_async in (('Client', False), ('AsyncClient', True)):
        cls = getattr(httpx, cls_name, None)
        if not cls:
            continue
        if getattr(cls.request, '_iat_patched', False):
            continue
        orig = cls.request

        if is_async:
            async def wrapped(self, method, url, **kwargs):
                entry = {'direction': 'out', 'lib': 'httpx-async', 'method': method, 'url': url}
                entry.update(_summarize_req(kwargs))
                t0 = time.time()
                try:
                    resp = await orig(self, method, url, **kwargs)
                    _summarize_resp(resp, entry)
                    return resp
                except Exception as e:
                    entry['error'] = repr(e)[:500]
                    raise
                finally:
                    entry['elapsed_ms'] = int((time.time() - t0) * 1000)
                    _write(entry)
        else:
            def wrapped(self, method, url, **kwargs):
                entry = {'direction': 'out', 'lib': 'httpx', 'method': method, 'url': url}
                entry.update(_summarize_req(kwargs))
                t0 = time.time()
                try:
                    resp = orig(self, method, url, **kwargs)
                    _summarize_resp(resp, entry)
                    return resp
                except Exception as e:
                    entry['error'] = repr(e)[:500]
                    raise
                finally:
                    entry['elapsed_ms'] = int((time.time() - t0) * 1000)
                    _write(entry)
        wrapped._iat_patched = True
        cls.request = wrapped


_patch_requests()
_patch_httpx()
