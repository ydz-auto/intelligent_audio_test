# -*- coding: utf-8 -*-
import os
from app.controllers.api import _storage_id


def test_storage_id_accepts_int_and_unsafe_paths():
    assert _storage_id(339) == '339'
    assert _storage_id('339') == '339'
    # 无有效 task_id 且无 fallback → 随机段，非空
    assert _storage_id('../secret', 'task_abc') != ''
    assert _storage_id(None, '') != ''


def test_storage_id_nested_by_task_and_case():
    assert _storage_id(407, '444fe803-aa11', 'task_x') == os.path.join('407', '444fe803-aa11')
    # 用例 id 缺失 → 回退到任务级目录
    assert _storage_id(407, None, 'task_x') == '407'
    # 用例 id 非法（路径分隔符）→ 回退到任务级目录
    assert _storage_id(407, 'a/b', 'task_x') == '407'
    # 任务 id 非法 → 用 fallback
    assert _storage_id('../secret', '444fe803', 'task_abc') == 'task_abc'
