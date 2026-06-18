# -*- coding: utf-8 -*-
"""Unit tests for api_adapter_service."""

import sys
import os
import unittest
import json

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class TestSessionStore(unittest.TestCase):
    """Tests for SessionStore."""

    def setUp(self):
        from api_adapter_service.services.session_store import SessionStore
        self.store = SessionStore()

    def test_create_session(self):
        session = self.store.create_session(
            session_id='sess-001',
            task_id='task-001',
            context_mode='full',
            max_history_rounds=5,
            session_timeout=60,
        )
        self.assertEqual(session['session_id'], 'sess-001')
        self.assertEqual(session['task_id'], 'task-001')
        self.assertEqual(session['status'], 'active')
        self.assertEqual(session['context_mode'], 'full')
        self.assertEqual(self.store.get_session_count(), 1)

    def test_get_session(self):
        self.store.create_session('sess-002', 'task-002')
        session = self.store.get_session('sess-002')
        self.assertIsNotNone(session)
        self.assertEqual(session['session_id'], 'sess-002')
        # Returns copy
        session['status'] = 'modified'
        original = self.store.get_session('sess-002')
        self.assertEqual(original['status'], 'active')

    def test_get_nonexistent_session(self):
        session = self.store.get_session('nonexistent')
        self.assertIsNone(session)

    def test_ensure_session_creates(self):
        session = self.store.ensure_session('sess-ensure', 'task-e')
        self.assertEqual(session['session_id'], 'sess-ensure')
        self.assertEqual(self.store.get_session_count(), 1)

    def test_ensure_session_reuses(self):
        self.store.create_session('sess-reuse', 'task-r')
        session = self.store.ensure_session('sess-reuse', 'task-r')
        self.assertEqual(session['session_id'], 'sess-reuse')
        self.assertEqual(self.store.get_session_count(), 1)

    def test_add_round(self):
        self.store.create_session('sess-r', 'task-r')
        self.store.add_round('sess-r', 0, 'hello', 'hi there', 0.5)
        self.store.add_round('sess-r', 1, 'how are you', 'I am fine', 0.3)

        session = self.store.get_session('sess-r')
        self.assertEqual(len(session['round_results']), 2)
        self.assertEqual(len(session['context_history']), 4)  # 2 rounds * 2 messages

    def test_add_round_nonexistent(self):
        # Should not raise
        self.store.add_round('nonexistent', 0, 'hello', 'hi', 0.5)

    def test_get_context_full(self):
        self.store.create_session('sess-full', 'task-f', context_mode='full', max_history_rounds=2)
        for i in range(5):
            self.store.add_round('sess-full', i, f'input-{i}', f'output-{i}', 0.1)

        context = self.store.get_context('sess-full')
        self.assertEqual(len(context), 10)  # 5 rounds * 2

    def test_get_context_sliding_window(self):
        self.store.create_session('sess-sw', 'task-s', context_mode='sliding_window', max_history_rounds=2)
        for i in range(5):
            self.store.add_round('sess-sw', i, f'input-{i}', f'output-{i}', 0.1)

        context = self.store.get_context('sess-sw')
        # max_history_rounds=2 -> last 4 messages (2 rounds * 2)
        self.assertEqual(len(context), 4)
        self.assertEqual(context[0]['content'], 'input-3')
        self.assertEqual(context[1]['content'], 'output-3')

    def test_get_round_results(self):
        self.store.create_session('sess-rr', 'task-rr')
        self.store.add_round('sess-rr', 0, 'a', 'b', 0.2)
        results = self.store.get_round_results('sess-rr')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['round'], 0)
        self.assertEqual(results[0]['input'], 'a')

    def test_destroy_session(self):
        self.store.create_session('sess-d', 'task-d')
        self.assertEqual(self.store.get_session_count(), 1)
        self.store.destroy_session('sess-d')
        self.assertEqual(self.store.get_session_count(), 0)

    def test_destroy_nonexistent(self):
        # Should not raise
        self.store.destroy_session('nonexistent')

    def test_context_for_request_format(self):
        self.store.create_session('sess-fmt', 'task-fmt')
        self.store.add_round('sess-fmt', 0, 'hello', 'hi', 0.1)
        context = self.store.get_context('sess-fmt')
        self.assertEqual(context[0], {'role': 'user', 'content': 'hello'})
        self.assertEqual(context[1], {'role': 'assistant', 'content': 'hi'})


class TestTaskManager(unittest.TestCase):
    """Tests for TaskManager."""

    def setUp(self):
        from api_adapter_service.services.task_manager import TaskManager
        self.mgr = TaskManager()

    def test_create_task(self):
        task = self.mgr.create_task('t-001', session_id='s-001', vendor='mock')
        self.assertEqual(task['task_id'], 't-001')
        self.assertEqual(task['status'], 'pending')
        self.assertEqual(task['session_id'], 's-001')

    def test_update_status(self):
        self.mgr.create_task('t-002')
        self.mgr.update_task_status('t-002', 'processing')
        task = self.mgr.get_task('t-002')
        self.assertEqual(task['status'], 'processing')

    def test_update_status_with_error(self):
        self.mgr.create_task('t-003')
        self.mgr.update_task_status('t-003', 'failed', 'some error')
        task = self.mgr.get_task('t-003')
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['error_message'], 'some error')

    def test_add_round_result(self):
        self.mgr.create_task('t-004')
        self.mgr.add_round_result('t-004', 0, {'asr_text': 'hello', 'latency': 0.5})
        self.mgr.add_round_result('t-004', 1, {'asr_text': 'world', 'latency': 0.3})
        results = self.mgr.get_round_results('t-004')
        self.assertEqual(len(results), 2)

    def test_get_round_result(self):
        self.mgr.create_task('t-005')
        self.mgr.add_round_result('t-005', 0, {'asr_text': 'a'})
        self.mgr.add_round_result('t-005', 1, {'asr_text': 'b'})
        r = self.mgr.get_round_result('t-005', 1)
        self.assertIsNotNone(r)
        self.assertEqual(r['result']['asr_text'], 'b')

    def test_get_final_result_dialog(self):
        self.mgr.create_task('t-006', session_id='s-006')
        self.mgr.add_round_result('t-006', 0, {'asr_text': 'hello', 'trans_text': 'hi', 'latency': 0.5})
        self.mgr.add_round_result('t-006', 1, {'asr_text': 'world', 'trans_text': 'earth', 'latency': 0.3})

        result = self.mgr.get_final_result('t-006')
        self.assertIsNotNone(result)
        self.assertEqual(result['result_type'], 'dialog')
        self.assertEqual(result['total_rounds'], 2)
        self.assertAlmostEqual(result['total_latency'], 0.8)
        self.assertEqual(result['rounds'][0]['asr_text'], 'hello')

    def test_get_final_result_empty(self):
        self.mgr.create_task('t-007')
        result = self.mgr.get_final_result('t-007')
        self.assertIsNone(result)

    def test_delete_task(self):
        self.mgr.create_task('t-008')
        self.mgr.add_round_result('t-008', 0, {'latency': 0.1})
        self.mgr.delete_task('t-008')
        self.assertIsNone(self.mgr.get_task('t-008'))
        self.assertEqual(self.mgr.get_round_results('t-008'), [])


class TestMockDialogAdapter(unittest.TestCase):
    """Tests for MockDialogAdapter."""

    def setUp(self):
        from api_adapter_service.adapters.mock_adapter import MockDialogAdapter
        self.adapter = MockDialogAdapter()

    def test_text_input_echo(self):
        result = self.adapter.send_request(
            task_id='t1', session_id='s1',
            input_type='text', input_data='hello world',
        )
        self.assertEqual(result['asr_text'], 'hello world')
        self.assertIn('trans_text', result)
        self.assertGreater(result['latency'], 0)

    def test_audio_input_preset(self):
        result = self.adapter.send_request(
            task_id='t2', session_id='s2',
            input_type='audio', input_data=b'\x00' * 100,
        )
        # ASR should return preset response, not the audio bytes
        self.assertIsInstance(result['asr_text'], str)
        self.assertGreater(len(result['asr_text']), 0)

    def test_round_robin_responses(self):
        adapter = self.adapter
        results = []
        for i in range(3):
            r = adapter.send_request(
                task_id='t3', session_id='s3-rr',
                input_type='text', input_data=f'input-{i}',
            )
            results.append(r)

        # All should have different ASR (echo) but different trans (round-robin)
        for i, r in enumerate(results):
            self.assertEqual(r['asr_text'], f'input-{i}')

        # Trans should cycle through presets
        self.assertNotEqual(results[0]['trans_text'], results[1]['trans_text'])

    def test_destroy_session(self):
        self.adapter.send_request(
            task_id='t4', session_id='s4-d',
            input_type='text', input_data='test',
        )
        self.assertIn('s4-d', self.adapter._round_counter)
        self.adapter.destroy_session('s4-d')
        self.assertNotIn('s4-d', self.adapter._round_counter)


class TestAdapterFactory(unittest.TestCase):
    """Tests for adapter factory."""

    def test_mock_adapter(self):
        from api_adapter_service.adapters.factory import select_adapter
        from api_adapter_service.adapters.mock_adapter import MockDialogAdapter
        adapter = select_adapter('mock', {'protocol': 'mock'}, is_dialog=True)
        self.assertIsInstance(adapter, MockDialogAdapter)

    def test_http_adapter(self):
        from api_adapter_service.adapters.factory import select_adapter
        from api_adapter_service.adapters.http_adapter import HttpAdapter
        adapter = select_adapter('voice_llm', {'protocol': 'http', 'base_url': 'http://localhost:9000'})
        self.assertIsInstance(adapter, HttpAdapter)

    def test_default_http_adapter(self):
        from api_adapter_service.adapters.factory import select_adapter
        from api_adapter_service.adapters.http_adapter import HttpAdapter
        adapter = select_adapter('some_vendor', {'base_url': 'http://api.example.com'})
        self.assertIsInstance(adapter, HttpAdapter)


class TestConfig(unittest.TestCase):
    """Tests for Config loader."""

    def test_defaults_when_no_file(self):
        from api_adapter_service.utils.config import Config
        cfg = Config(config_path='/nonexistent/path.yml')
        # Should fall back to defaults
        self.assertIsNotNone(cfg.get('server.host'))

    def test_dot_path_access(self):
        from api_adapter_service.utils.config import Config
        cfg = Config(config_path='/nonexistent/path.yml')
        # Test non-existent path returns default
        self.assertEqual(cfg.get('nonexistent.deep.path', 'fallback'), 'fallback')
        # Test existing default path
        self.assertEqual(cfg.get('server.host', 'fallback'), '0.0.0.0')

    def test_get_vendor_config(self):
        from api_adapter_service.utils.config import Config
        cfg = Config(config_path='/nonexistent/path.yml')
        mock_config = cfg.get_vendor_config('mock')
        self.assertIsInstance(mock_config, dict)

    def test_load_real_config(self):
        from api_adapter_service.utils.config import Config
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'api_adapter_service', 'config', 'application.yml',
        )
        if os.path.exists(config_path):
            cfg = Config(config_path=config_path)
            port = cfg.get('server.port')
            self.assertEqual(port, 8000)
            voice_llm = cfg.get_vendor_config('voice_llm')
            self.assertEqual(voice_llm.get('protocol'), 'http')


class TestFlaskApp(unittest.TestCase):
    """Integration tests for Flask app."""

    def setUp(self):
        from api_adapter_service.app import create_app
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('dialog', data['supported_modes'])

    def test_v1_tasks_requires_body(self):
        resp = self.client.post('/api/v1/tasks', content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_v1_tasks_requires_session_id(self):
        resp = self.client.post(
            '/api/v1/tasks',
            json={'input': {'type': 'text', 'text': 'hello'}},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data['code'], 4000)

    def test_v1_tasks_mock_dialog(self):
        resp = self.client.post(
            '/api/v1/tasks',
            json={
                'session_id': 'test-sess-001',
                'round': 0,
                'total_rounds': 3,
                'task_type': 'voice_llm',
                'vendor': 'mock',
                'input': {'type': 'text', 'text': 'hello world'},
                'translation_direction': 'zh2en',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['code'], 0)
        self.assertEqual(data['asr_text'], 'hello world')
        self.assertIn('trans_text', data)
        self.assertIn('response_metrics', data)

    def test_v1_tasks_multi_round(self):
        session_id = 'test-sess-multi'
        results = []
        for i in range(3):
            resp = self.client.post(
                '/api/v1/tasks',
                json={
                    'session_id': session_id,
                    'round': i,
                    'total_rounds': 3,
                    'task_type': 'voice_llm',
                    'vendor': 'mock',
                    'input': {'type': 'text', 'text': f'round-{i}'},
                },
            )
            self.assertEqual(resp.status_code, 200)
            results.append(resp.get_json())

        # All rounds should succeed
        for r in results:
            self.assertEqual(r['code'], 0)

    def test_get_status_not_found(self):
        resp = self.client.get('/api/get_status/nonexistent')
        self.assertEqual(resp.status_code, 404)

    def test_get_final_result_not_found(self):
        resp = self.client.get('/api/get_final_result/nonexistent')
        self.assertEqual(resp.status_code, 404)

    def test_list_sessions(self):
        resp = self.client.get('/api/sessions')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('active_count', data['data'])

    def test_create_dialog_task_async(self):
        resp = self.client.post(
            '/api/create_dialog_task',
            json={
                'session_id': 'async-sess-001',
                'round': 0,
                'input_type': 'text',
                'input_data': 'async hello',
                'vendor': 'mock',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['code'], 0)
        self.assertIn('task_id', data['data'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
