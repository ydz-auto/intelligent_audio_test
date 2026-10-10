# -*- coding: utf-8 -*-
"""INT-106 单轮被测协议测试（api_adapter_service 侧）

覆盖：
1. POST /api/create_task：异步建任务立即返回 data.task_id；状态轮询收敛
   completed；GET /api/get_final_result 返回平铺结果字段；DELETE
   /api/delete_task 删除后 404 —— 与 api_test_service 单轮执行器默认
   api_paths 全族匹配
2. 参数校验：缺 audio_path / 音频不可解析 → 400
3. DDD 路由挂载：/api/adapter/tasks 存在（原缺陷：路由模块未注册 → 404）
4. CreateSingleTurnTaskCommand 参数解析
"""

import os
import sys
import time
import unittest

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from api_adapter_service.app import create_app
from api_adapter_service.application.commands.single_turn_commands import (
    CreateSingleTurnTaskCommand,
)

_TERMINAL = ('completed', 'failed', 'error')


class SingleTurnProtocolTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def _create_task(self, audio_path, vendor='mock'):
        resp = self.client.post('/api/create_task', json={
            'audio_path': audio_path,
            'audio_url': audio_path,
            'vendor': vendor,
            'max_process': 5,
            'max_timeout': 30,
        })
        return resp

    def _wait_terminal(self, task_id, timeout=6.0):
        deadline = time.time() + timeout
        status = 'processing'
        while time.time() < deadline:
            resp = self.client.get(f'/api/get_status/{task_id}')
            self.assertEqual(resp.status_code, 200)
            status = resp.json()['data']['status']
            if status in _TERMINAL:
                break
            time.sleep(0.1)
        return status

    def test_full_single_turn_chain(self):
        """建任务 → 轮询 completed → 平铺最终结果 → 删除。"""
        import tempfile
        tmp = tempfile.mktemp(suffix='.wav')
        with open(tmp, 'wb') as f:
            f.write(b'RIFF....WAVE')

        resp = self._create_task(tmp)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 0)
        task_id = body['data']['task_id']
        self.assertTrue(task_id)

        status = self._wait_terminal(task_id)
        self.assertEqual(status, 'completed')

        final = self.client.get(f'/api/get_final_result/{task_id}').json()
        self.assertEqual(final['code'], 0)
        data = final['data']
        self.assertEqual(data['result_type'], 'single_turn')
        self.assertTrue(data['asr_text'])
        self.assertTrue(data['trans_text'])

        deleted = self.client.delete(f'/api/delete_task/{task_id}')
        self.assertEqual(deleted.json()['code'], 0)
        self.assertEqual(
            self.client.get(f'/api/get_status/{task_id}').status_code, 404)

    def test_missing_audio_path_rejected(self):
        resp = self.client.post('/api/create_task', json={'vendor': 'mock'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('audio_path', resp.json()['msg'])

    def test_oss_storage_ref_audio_full_chain(self):
        """oss:// 存储引用音频（秒传/OSS 直传/URL 导入产物）走通单轮全链。"""
        from unittest import mock
        with mock.patch('shared.infrastructure.storage.storage.load_bytes',
                        return_value=b'RIFF....WAVE') as load_bytes:
            resp = self._create_task('oss://audios/uploaded/x.wav')
            self.assertEqual(resp.status_code, 200)
            task_id = resp.json()['data']['task_id']
            status = self._wait_terminal(task_id)
            self.assertEqual(status, 'completed')
            final = self.client.get(
                f'/api/get_final_result/{task_id}').json()
            self.assertEqual(final['code'], 0)
            self.assertTrue(final['data']['asr_text'])
        load_bytes.assert_called_with('oss://audios/uploaded/x.wav')

    def test_unresolvable_audio_rejected(self):
        resp = self._create_task('Z:/definitely/not/exist/x.wav')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('audio unavailable', resp.json()['msg'])

    def test_empty_body_rejected(self):
        resp = self.client.post('/api/create_task')
        self.assertEqual(resp.status_code, 400)

    def test_ddd_dialog_router_mounted(self):
        """原缺陷：interfaces 路由未注册 → /api/adapter/tasks 404。

        挂载后非空 body 缺 session_id 应得到协议级 400。
        """
        resp = self.client.post('/api/adapter/tasks', json={'input': {}})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('session_id', resp.json()['msg'])


class CreateSingleTurnCommandTest(unittest.TestCase):

    def test_from_request_flat_params(self):
        cmd = CreateSingleTurnTaskCommand.from_request({
            'audio_url': 'oss://audios/a.wav',
            'vendor': 'volc_ast',
        })
        self.assertEqual(cmd.audio_path, 'oss://audios/a.wav')
        self.assertEqual(cmd.vendor, 'volc_ast')

    def test_audio_path_preferred_over_audio_url(self):
        cmd = CreateSingleTurnTaskCommand.from_request({
            'audio_path': 'oss://audios/p.wav',
            'audio_url': 'oss://audios/u.wav',
        })
        self.assertEqual(cmd.audio_path, 'oss://audios/p.wav')

    def test_missing_audio_raises(self):
        with self.assertRaises(ValueError):
            CreateSingleTurnTaskCommand.from_request({'vendor': 'mock'})

    def test_empty_body_raises(self):
        with self.assertRaises(ValueError):
            CreateSingleTurnTaskCommand.from_request({})


if __name__ == '__main__':
    unittest.main()
