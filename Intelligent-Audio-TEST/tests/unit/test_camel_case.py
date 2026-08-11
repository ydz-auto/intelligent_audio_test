# -*- coding: utf-8 -*-
"""shared.utils.camel_case 驼峰转换函数测试。

测试：
- camel_to_snake(): 驼峰 → 蛇形
- snake_to_camel(): 蛇形 → 驼峰
"""
import pytest

from shared.utils.camel_case import camel_to_snake, snake_to_camel


class TestCamelToSnake:
    @pytest.mark.parametrize("camel,expected", [
        ('camelCase', 'camel_case'),
        ('taskName', 'task_name'),
        ('getStatus', 'get_status'),
        ('simple', 'simple'),
        ('HTTPRequest', 'http_request'),
        ('taskId', 'task_id'),
        ('evaluationStatus', 'evaluation_status'),
    ])
    def test_camel_to_snake(self, camel, expected):
        assert camel_to_snake(camel) == expected

    def test_single_word(self):
        assert camel_to_snake('task') == 'task'

    def test_all_uppercase(self):
        assert camel_to_snake('WER') == 'wer'

    def test_consecutive_uppercase_then_lowercase(self):
        # WEREn -> wer_en
        assert camel_to_snake('WEREn') == 'wer_en'

    def test_empty_string(self):
        assert camel_to_snake('') == ''

    def test_with_spaces(self):
        # 空格替换为下划线
        assert camel_to_snake('task Name') == 'task_name'

    def test_already_snake(self):
        assert camel_to_snake('task_name') == 'task_name'

    def test_with_digits(self):
        assert camel_to_snake('task123Name') == 'task123_name'


class TestSnakeToCamel:
    @pytest.mark.parametrize("snake,expected", [
        ('task_name', 'taskName'),
        ('get_status', 'getStatus'),
        ('evaluation_status', 'evaluationStatus'),
        ('simple', 'simple'),
    ])
    def test_snake_to_camel(self, snake, expected):
        assert snake_to_camel(snake) == expected

    def test_snake_to_camel_capitalize_first(self):
        assert snake_to_camel('task_name', capitalize_first=True) == 'TaskName'

    def test_single_word(self):
        assert snake_to_camel('task') == 'task'

    def test_single_word_capitalize(self):
        assert snake_to_camel('task', capitalize_first=True) == 'Task'

    def test_empty_string(self):
        assert snake_to_camel('') == ''

    def test_leading_underscore(self):
        # split('_') 对 '_name' 产生 ['', 'name']
        assert snake_to_camel('_name') == 'Name'

    def test_multiple_underscores(self):
        assert snake_to_camel('a_b_c') == 'aBC'

    def test_double_underscore_capitalize(self):
        assert snake_to_camel('a__b', capitalize_first=True) == 'AB'


class TestRoundtrip:
    @pytest.mark.parametrize("camel", [
        'taskName',
        'getStatus',
        'evaluationStatus',
        'simple',
        'taskId',
    ])
    def test_camel_snake_camel_roundtrip(self, camel):
        assert snake_to_camel(camel_to_snake(camel)) == camel

    @pytest.mark.parametrize("snake", [
        'task_name',
        'get_status',
        'evaluation_status',
        'simple',
    ])
    def test_snake_camel_snake_roundtrip(self, snake):
        assert camel_to_snake(snake_to_camel(snake)) == snake
