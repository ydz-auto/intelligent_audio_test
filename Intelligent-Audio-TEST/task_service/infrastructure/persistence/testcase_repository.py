# -*- coding: utf-8 -*-
"""测试用例仓储 — 聚合模块（P4-5 大文件拆分）。

原单文件 1054 行，按职责拆分为 4 个内部模块，本文件保持
`from task_service.infrastructure.persistence.testcase_repository import ...`
的全部导入路径不变：

- _testcase_repo_common.py：公共小工具（维度 JSON 过滤 / 转义模糊匹配 / 时间）
- _testcase_crud_query_mixin.py：TestCaseCrudMixin（TestCase CRUD / 用例-标签关联）
- _testcase_query_mixin.py：TestCaseQueryMixin（分页查询 / 全量 ID / 统计）
- _testcase_group_mixin.py：TestCaseGroupMixin（分组 CRUD 与多维筛选）
- _tag_repository_mixin.py：TagRepositoryMixin（标签 / 标签分类 / 引用计数）

跨域查询（Audio / Dimension）通过 ACL 仓储委托 gRPC 完成。
"""
from typing import Any, Dict, Optional

from shared.models.database import get_db_session
from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence._testcase_crud_query_mixin import (
    TestCaseCrudMixin,
)
from task_service.infrastructure.persistence._testcase_query_mixin import (
    TestCaseQueryMixin,
)
from task_service.infrastructure.persistence._testcase_group_mixin import (
    TestCaseGroupMixin,
)
from task_service.infrastructure.persistence._tag_repository_mixin import (
    TagRepositoryMixin,
)


class TestCaseRepository(
    TestCaseCrudMixin,
    TestCaseQueryMixin,
    TestCaseGroupMixin,
    TagRepositoryMixin,
    TestCaseGroupRepositoryABC,
):
    """测试用例仓储（组合各职责 Mixin）"""

    # ========== 跨域查询：Audio / Dimension ==========

    def get_audio_by_id(self, audio_id) -> Optional[dict]:
        """按 ID 查询单个音频，返回 dict（含 id/name/duration 等字段）。

        P3 改造：Audio 是 e2e_test_service 自有 PO，通过
        AudioConfigService.GetAudio gRPC 查询，替代直连 DB。
        失败时返回 None（仅日志告警）。
        """
        if not audio_id:
            return None

        from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
        return audio_acl_repository.get_audio_by_id(audio_id)

    def list_audios_by_ids(self, audio_ids: set) -> Dict[Any, dict]:
        """按 ID 集合批量查询音频，返回 {id: audio_dict} 映射。

        P3 改造：Audio 是 e2e_test_service 自有 PO，通过
        AudioConfigService.GetAudiosByIds gRPC 批量查询，替代直连 DB。
        失败时返回空 dict（仅日志告警）。
        """
        if not audio_ids:
            return {}

        from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
        return audio_acl_repository.list_audios_by_ids(audio_ids)

    def list_dimensions_by_ids(self, dim_ids):
        """按 ID 列表批量查询评价维度基础信息。

        P1.7 改造：Dimension 是 evaluation_service 自有 PO，通过 gRPC 调
        evaluation_service.EvaluationConfigService.GetDimensionByIds 获取。

        Args:
            dim_ids: list[int]，Dimension.id 列表

        Returns:
            list[dict]: [{'id': int, 'name': str, 'type': str, 'description': str}, ...]
            调用失败时返回空列表（仅日志告警）。
        """
        if not dim_ids:
            return []

        from task_service.infrastructure.acl.evaluation_config_acl_repository import evaluation_config_acl_repository
        return evaluation_config_acl_repository.list_dimensions_by_ids(dim_ids)

    # ========== 事务控制 ==========

    def commit(self):
        """提交事务。"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务。"""
        get_db_session().rollback()

    def flush(self):
        """flush session。"""
        get_db_session().flush()


# 模块级单例，供 application 层导入
testcase_repository = TestCaseRepository()
