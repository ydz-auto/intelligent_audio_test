# -*- coding: utf-8 -*-
"""task_service ACL 仓储层

跨域 gRPC 适配器，封装对其他服务（algorithm_service / evaluation_service）的访问。
返回 dict / list，绝不返回 ORM 对象。
"""
