# -*- coding: utf-8 -*-
from app.controllers.api import _storage_id


def test_storage_id_accepts_int_and_unsafe_paths():
    assert _storage_id(339) == '339'
    assert _storage_id('339') == '339'
    assert _storage_id('../secret', 'task_abc') == 'task_abc'
    assert _storage_id(None, '') != ''
