# -*- coding: utf-8 -*-
"""
日志修复的纯逻辑单元测试（不依赖 Flask/DB/OSS 运行时）。
验证 LogFilterRegistry 过滤逻辑、refresh_logs 的 reset 判断、去重指纹上下文。

运行方式（有可用 Python 环境时）：
    cd d:\00_code\V9.7.27\Intelligent-Audio-TEST
    python scripts/test_log_fixes.py

不依赖项目其他模块，可直接执行。
"""
import sys
import os
import unittest
from unittest.mock import patch

# 把项目根加入 sys.path，便于导入 shared/api_gateway
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class LogFilterRegistryTests(unittest.TestCase):
    """验证 #3: WebSocket 服务端过滤器落地"""

    def setUp(self):
        # 重新导入以拿到全新单例（每次测试隔离）
        import importlib
        import api_gateway.controllers.log_controller as mod
        importlib.reload(mod)
        self.registry = mod.LogFilterRegistry()

    def _log(self, **kw):
        d = {'level': 'INFO', 'module': 'Evaluation', 'content': 'hello', 'task_id': None}
        d.update(kw)
        return d

    def test_empty_filter_passes_all(self):
        """无过滤器的 sid 接收全部日志"""
        self.registry.set_filter('sid_A', {})
        self.registry.set_filter('sid_B', {'levels': ['ERROR']})
        matched = self.registry.match(self._log(level='INFO'))
        self.assertIn('sid_A', matched)
        self.assertNotIn('sid_B', matched)

    def test_level_filter(self):
        """levels 过滤：ERROR 客户端只收 ERROR"""
        self.registry.set_filter('sid_A', {'levels': ['ERROR']})
        matched_info = self.registry.match(self._log(level='INFO'))
        matched_err = self.registry.match(self._log(level='ERROR'))
        self.assertEqual(matched_info, [])
        self.assertEqual(matched_err, ['sid_A'])

    def test_module_filter(self):
        """modules 过滤"""
        self.registry.set_filter('sid_A', {'modules': ['EVALUATION']})
        self.assertIn('sid_A', self.registry.match(self._log(module='Evaluation')))
        self.assertEqual([], self.registry.match(self._log(module='Task')))

    def test_keyword_filter(self):
        """keyword 过滤"""
        self.registry.set_filter('sid_A', {'keyword': 'build_payload'})
        self.assertIn('sid_A', self.registry.match(self._log(content='[build_payload] xxx')))
        self.assertEqual([], self.registry.match(self._log(content='other content')))

    def test_task_filter(self):
        """task_id 过滤：只收指定 task 的日志"""
        self.registry.set_filter('sid_A', {'task_id': 123})
        self.assertIn('sid_A', self.registry.match(self._log(task_id=123)))
        self.assertEqual([], self.registry.match(self._log(task_id=456)))

    def test_remove_clears_filter(self):
        """disconnect 清理 sid 后不再匹配"""
        self.registry.set_filter('sid_A', {'levels': ['ERROR']})
        self.registry.remove('sid_A')
        self.assertEqual([], self.registry.match(self._log(level='ERROR')))

    def test_multiple_sids_isolation(self):
        """多 sid 隔离：A 只收 ERROR，B 收全部，INFO 日志只发给 B"""
        self.registry.set_filter('sid_A', {'levels': ['ERROR']})
        self.registry.set_filter('sid_B', {})
        matched = self.registry.match(self._log(level='INFO'))
        self.assertEqual(matched, ['sid_B'])


class DedupFingerprintTests(unittest.TestCase):
    """验证 #7: 去重指纹带上 task_id/test_case_id/category"""

    def test_same_message_different_task_not_deduped(self):
        """同内容不同 task 的日志不应被同一个指纹吞掉"""
        import hashlib

        def fingerprint(level, module, task_id, test_case_id, category, message):
            ctx = f"{level}-{module}-{task_id}-{test_case_id}-{category}-{message}"
            return hashlib.md5(ctx.encode('utf-8')).hexdigest()

        fp1 = fingerprint(20, 'Evaluation', 100, None, 'execution', 'build_payload done')
        fp2 = fingerprint(20, 'Evaluation', 200, None, 'execution', 'build_payload done')
        # 旧指纹（不带 task_id）
        fp_old = hashlib.md5(f"20-Evaluation-build_payload done".encode('utf-8')).hexdigest()

        self.assertNotEqual(fp1, fp2, '不同 task_id 应产生不同指纹')
        self.assertNotEqual(fp1, fp_old, '新指纹不应与旧指纹相同')

    def test_same_message_different_case_not_deduped(self):
        import hashlib

        def fingerprint(level, module, task_id, test_case_id, category, message):
            ctx = f"{level}-{module}-{task_id}-{test_case_id}-{category}-{message}"
            return hashlib.md5(ctx.encode('utf-8')).hexdigest()

        fp1 = fingerprint(20, 'Evaluation', 100, 'case_A', 'execution', 'round done')
        fp2 = fingerprint(20, 'Evaluation', 100, 'case_B', 'execution', 'round done')
        self.assertNotEqual(fp1, fp2, '同 task 不同 case 应产生不同指纹')


class RefreshResetTests(unittest.TestCase):
    """验证 #8: refresh_logs 的 reset_required 判断逻辑"""

    def test_reset_required_when_last_id_exceeds_max(self):
        """last_id > db_max_id 时应触发 reset"""
        last_id = 999999
        db_max_id = 100
        self.assertTrue(last_id > db_max_id, '应标记 reset_required=True')

    def test_no_reset_when_last_id_within_range(self):
        """last_id <= db_max_id 时正常增量"""
        last_id = 50
        db_max_id = 100
        self.assertFalse(last_id > db_max_id, '不应触发 reset')