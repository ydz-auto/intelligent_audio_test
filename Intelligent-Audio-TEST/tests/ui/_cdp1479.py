# -*- coding: utf-8 -*-
"""最小 CDP 客户端（websocket-client），绕过卡死的 chromedriver。"""
import json
import time

import websocket


class CDP:
    def __init__(self, ws_url, timeout=30):
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self.mid = 0
        self.events = []

    def pump(self):
        """非阻塞收事件（socket 超时即返回）。"""
        self.ws.settimeout(0.05)
        try:
            while True:
                msg = json.loads(self.ws.recv())
                if 'method' in msg:
                    self.events.append(msg)
        except Exception:
            pass
        finally:
            self.ws.settimeout(30)

    def send(self, method, params=None, wait=True):
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        if not wait:
            return None
        end = time.time() + 30
        while time.time() < end:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})
            if 'method' in msg:
                self.events.append(msg)
        raise TimeoutError(method)

    def eval(self, expr, await_promise=False):
        res = self.send('Runtime.evaluate', {
            'expression': expr, 'returnByValue': True, 'awaitPromise': await_promise})
        if res.get('exceptionDetails'):
            raise RuntimeError('JS: ' + json.dumps(res['exceptionDetails'])[:300])
        return res.get('result', {}).get('value')

    def screenshot(self, path):
        data = self.send('Page.captureScreenshot', {'format': 'png'})['data']
        import base64
        with open(path, 'wb') as f:
            f.write(base64.b64decode(data))
        return path
