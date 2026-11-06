# -*- coding: utf-8 -*-
"""api_test_service 持久化对象（PO）包。

归属：api_test_service（API 测试上下文，被测 API 配置所有权）
表：apis

P5 改造：PO 定义真正下沉到本包，
shared/models/models/api_models.py 改为从这里 re-export。
"""
from .api_models import API

__all__ = ['API']
