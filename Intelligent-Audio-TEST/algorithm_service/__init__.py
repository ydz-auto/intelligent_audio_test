# -*- coding: utf-8 -*-
"""algorithm_service — 算法配置微服务

P5 阶段新建骨架。持有 Algorithm 全套 PO 的数据所有权。
后续 P6 阶段会从 api_gateway/algorithm/ 下沉 CRUD 逻辑到本服务。

当前 api_gateway/application/algorithm/* 仍可直接通过本服务的 PO 引用读写，
后续改为 gRPC 调用。
"""
