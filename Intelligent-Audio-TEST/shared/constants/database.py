# -*- coding: utf-8 -*-
"""数据库名称常量与解析（INT-246 测试/业务库隔离）——单一取值来源。

共享业务库（负责人数据，测试/agent 禁写）与隔离测试库（pytest 实机链路/
冒烟/验收专用）的库名唯一来源，消费方：
- tests/conftest.py 会话级守卫：pytest 生效 DATABASE_URL 指向共享业务库即
  拒绝启动（宁可拒绝，绝不静默写业务库）
- api_gateway /health 暴露 database 字段供 tests/api 实机门禁校验
- stack.py --test-db 一键把整栈切到隔离库
- scripts/reset_test_db.py 冒烟后清库（仅清隔离库，硬拒共享库）

本模块不读任何环境变量、零依赖，可在 conftest 顶层与任何进程安全导入。
"""
from urllib.parse import unquote, urlsplit

# 共享业务库：负责人数据所在库，pytest 与 agent 冒烟一律禁写
SHARED_BUSINESS_DB_NAME = 'intelligent_audio_test'
# 隔离测试库：实机链路回归 / 集成冒烟 / 验收专用，冒烟后清库
ISOLATED_TEST_DB_NAME = 'intelligent_audio_test_test'

_POSTGRES_SCHEMES = ('postgresql', 'postgres')


def database_name_of(url: str):
    """从 DATABASE_URL 解析库名；非 Postgres URL（如 sqlite）返回 None。

    兼容 driver 修饰（postgresql+psycopg2://）与 query 参数；
    解析失败（畸形 URL）返回 None，由调用方决定语义。
    """
    try:
        parts = urlsplit(url or '')
    except ValueError:
        return None
    if parts.scheme.split('+', 1)[0] not in _POSTGRES_SCHEMES:
        return None
    path = unquote(parts.path or '')
    name = path.lstrip('/').split('/', 1)[0].split('?', 1)[0]
    return name or None
