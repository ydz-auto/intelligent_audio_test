# -*- coding: utf-8 -*-
"""INT-2460 用例 / 标签域测试环境。

agent_service 的配置在 import 时读取 DATABASE_URL / OSS_*；这里先给内存
SQLite 与占位 OSS，避免测试依赖真实基础设施（与 tests/agent_eval/domains/evaluation
同口径）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
