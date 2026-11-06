# -*- coding: utf-8 -*-
"""e2e_test_service PO 模型包。

DDD 改造后：Audio/Device/Upload/SPL 等 PO 归属各自的服务（audio_service /
device_service），e2e_test_service 不再持有这些 PO，通过 infrastructure/acl/
下的 ACL 仓储经 gRPC 访问。
"""
