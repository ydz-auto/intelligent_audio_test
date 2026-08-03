# -*- coding: utf-8 -*-
"""算法领域共享模块

包含算法配置加载、字段映射、用例参数提取、参考参数生成、结果字段映射等领域逻辑。
供 api_gateway、task_service、e2e_test_service 等多服务直接 import 共享使用。

直接从子模块导入所需组件：
    from shared.algorithm.algorithm_config_loader import get_config_loader
    from shared.algorithm.field_mapper import get_field_mapper
"""
