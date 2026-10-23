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

import logging

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

logger = logging.getLogger(__name__)


class TestCaseRepository(
    TestCaseCrudMixin,
    TestCaseQueryMixin,
    TestCaseGroupMixin,
    TagRepositoryMixin,
    TestCaseGroupRepositoryABC,
):
    """测试用例仓储（组合各职责 Mixin）"""

    # ========== 跨域查询：Audio / Dimension ==========

    def get_evaluation_strategy(self, strategy_id):
        """按 ID 查询单个未删除评估策略（INT-590 用例引用策略）。

        策略实体归 task_service 本地（evaluation_strategies 表），经
        evaluation_strategy_repository 读取，供用例创建/更新时写时物化合并。
        返回 PO 或 None（策略不存在/已删除）。
        """
        if not strategy_id:
            return None
        from task_service.infrastructure.persistence.evaluation_strategy_repository import (
            evaluation_strategy_repository,
        )
        return evaluation_strategy_repository.get_strategy(strategy_id)

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

    def list_laboratories_by_ids(self, lab_ids) -> Dict[int, str]:
        """按 ID 集合批量查询实验室名称，返回 {lab_id: lab_name}（INT-539）。

        laboratories 表归属 api_gateway 实验室域（共享库，INT-493 口径④），
        本服务仅读展示用（lab_name join），不定义 ORM PO —— 避免跨服务同表
        映射冲突；用原生 SQL 查询，软删行排除（引用已删实验室的用例
        lab_name 返回 None，与设计文档「空 lab 返回 null」一致）。
        失败（如表不存在 / DB 异常）返回空 dict，仅日志告警，不阻断用例列表。
        """
        if not lab_ids:
            return {}
        from sqlalchemy import bindparam, text

        session = get_db_session()
        try:
            stmt = text(
                "SELECT id, name FROM laboratories "
                "WHERE deleted = false AND id IN :ids"
            ).bindparams(bindparam('ids', expanding=True))
            rows = session.execute(stmt, {'ids': [int(i) for i in lab_ids]}).fetchall()
            return {row.id: row.name for row in rows}
        except Exception as e:
            logger.warning(f"按 ID 查询实验室名称失败: {e}")
            return {}

    def check_audio_referenced(self, audio_id: int, user_id=None) -> dict:
        """按 audio_id 定点统计引用数（INT-1449）。

        替代旧 ACL 检查的全表分页 + config 字符串客户端扫描（gRPC
        ListTestCases/ListTasks 逐页拉取后 Python 侧 json.dumps 匹配）：
        - testcases: 用例 config 文本中出现 `"audio_id": {id}`（主音频/
          干扰人/段级背景噪声，等价旧 check_audio_in_testcases）
        - background_noise: 用例 config 文本出现 `"background_noise":
          {"audio_id": {id}}`（等价旧 check_audio_in_testcase_noise）
        - tasks: 非删除可见任务，其 task_case_relations 关联用例 config
          引用该音频（等价旧 check_audio_in_tasks 的「任务引用」语义，
          旧实现扫 Task.config 的字符串因任务 config 不含 audio_id 恒为 0）

        可见性口径与 ListTestCases/ListTasks 一致（visible_condition）。
        返回 {'testcases': int, 'background_noise': int, 'tasks': int}。
        """
        if not audio_id:
            return {'testcases': 0, 'background_noise': 0, 'tasks': 0}

        from sqlalchemy import Text, func, or_

        from shared.infrastructure.visibility_filter import visible_condition
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TestCase,
        )
        from task_service.infrastructure.visibility_context import visibility_identity

        session = get_db_session()
        _vis_uid, _vis_admin = visibility_identity(user_id)

        audio_str = str(int(audio_id))
        # JSON 数字值后紧跟 , 或 }（兼容 jsonb 紧凑文本 `"audio_id": 5,`
        # 与 JSON 原文 `"audio_id":5}` 两种冒号后空格的排列；显式列出逗号/
        # 闭括号两种收尾，避免把 audio_id 5 误匹配成 50/500 的前缀）。
        # LIKE 不支持 `[...]` 字符类（sqlite/Postgres 均按字面量处理），故展开。
        tc_like = or_(
            TestCase.config.cast(Text).like(f'%"audio_id": {audio_str},%'),
            TestCase.config.cast(Text).like(f'%"audio_id": {audio_str}}}%'),
            TestCase.config.cast(Text).like(f'%"audio_id":{audio_str},%'),
            TestCase.config.cast(Text).like(f'%"audio_id":{audio_str}}}%'),
        )
        bg_like = or_(
            TestCase.config.cast(Text).like(f'%"background_noise": {{"audio_id": {audio_str},%'),
            TestCase.config.cast(Text).like(f'%"background_noise": {{"audio_id": {audio_str}}}}}%'),
            TestCase.config.cast(Text).like(f'%"background_noise":{{"audio_id":{audio_str},%'),
            TestCase.config.cast(Text).like(f'%"background_noise":{{"audio_id":{audio_str}}}}}%'),
        )

        _case_visible = (
            TestCase.deleted == False,  # noqa: E712
            visible_condition(
                TestCase.created_by_user_id, TestCase.visibility, _vis_uid, _vis_admin),
        )

        testcases = session.query(func.count(TestCase.id)).filter(
            _case_visible[0], _case_visible[1], tc_like,
        ).scalar() or 0

        background_noise = session.query(func.count(TestCase.id)).filter(
            _case_visible[0], _case_visible[1], bg_like,
        ).scalar() or 0

        # 任务引用：task_case_relations → 关联用例 config 引用该音频
        # （主音频或背景噪声任一命中即可阻断删除）
        case_ref_ids = session.query(TaskCase.task_id).join(
            TestCase, TestCase.id == TaskCase.test_case_id,
        ).filter(
            _case_visible[0], _case_visible[1], tc_like,
        )
        tasks = session.query(func.count(func.distinct(Task.id))).filter(
            Task.deleted == False,  # noqa: E712
            visible_condition(
                Task.created_by_user_id, Task.visibility, _vis_uid, _vis_admin),
            Task.id.in_(case_ref_ids),
        ).scalar() or 0

        return {
            'testcases': int(testcases),
            'background_noise': int(background_noise),
            'tasks': int(tasks),
        }

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
