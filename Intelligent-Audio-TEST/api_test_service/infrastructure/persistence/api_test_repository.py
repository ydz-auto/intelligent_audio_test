# -*- coding: utf-8 -*-
"""API 测试仓储 — 持久化访问 API / TaskAPI / Task 关联数据。

封装 DB 访问细节，向上层（application/interfaces）提供领域可读的接口。
通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库。

P5+DOMAIN 改造：移除直接返回 ORM PO 的写法，改为 PO ↔ Entity 显式转换。
- 仓储方法返回 APIAggregate 聚合根，不再泄漏 ORM
- 通过 _api_po_to_entity / _apply_aggregate_to_po 完成双向映射
- 领域层与 ORM 完全隔离

P2.1 改造：task_service 的 PO（Task / TaskAPI）查询改为通过 gRPC 调用
TaskDataService，本仓储仅保留本地 API PO 的 DB 访问。
"""
import logging
from typing import List, Optional

from shared.models.database import get_db_session
from shared.utils.dto_utils import dto_to_dict

# 跨服务 gRPC 调用经 ACL 仓储（返回 DTO），本仓储仅保留本地 API PO 的 DB 访问
from api_test_service.infrastructure.acl import TaskDataAclRepositoryImpl

# API PO 归属本服务（shared.models.models.API 已改为从此处 re-export）
from api_test_service.infrastructure.persistence.models import API
# 领域聚合根
from api_test_service.domain.entities import APIAggregate
from api_test_service.domain.repositories.api_test_repository_abc import (
    APITestRepositoryABC,
)

logger = logging.getLogger(__name__)

# 跨服务 ACL 仓储单例
_task_data_acl = TaskDataAclRepositoryImpl()


# ========== PO ↔ Entity 转换 ==========

def _api_po_to_entity(po: API) -> APIAggregate:
    """API PO → APIAggregate 聚合根。

    仅映射聚合根承载的字段；PO 上聚合根不需要的字段（如 vendor / meta /
    api_endpoints / health_score / default_max_* 等）在此处丢弃。

    字段映射说明：
    - po.api_url        → aggregate.url
    - po.max_timeout    → aggregate.timeout_seconds（复用 PO 的超时配置）
    - po.status         → aggregate.status（PO 使用 online/offline，聚合根 status
                          字段为 str，直接透传以保留前端可读词汇）
    - 其余 PO 无对应列的字段（method / headers / body_template / retry_count）
      使用聚合根默认值
    """
    return APIAggregate(
        id=po.id,
        name=po.name,
        url=po.api_url or "",
        timeout_seconds=po.max_timeout or 30,
        status=po.status or "active",
        deleted=po.deleted or False,
    )


def _apply_aggregate_to_po(aggregate: APIAggregate, po: API) -> None:
    """将聚合根的可写字段映射回 PO（不含 id / created_at / deleted_at 等元数据）。

    聚合根中无 PO 对应列的字段（method / headers / body_template /
    retry_count）不回写。
    """
    po.name = aggregate.name
    po.api_url = aggregate.url
    po.status = aggregate.status
    po.deleted = aggregate.deleted
    po.max_timeout = aggregate.timeout_seconds


class APITestRepository(APITestRepositoryABC):
    """API 测试仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    每个方法内部通过 get_db_session() 获取 scoped_session 访问数据库；
    scoped_session 由请求/线程生命周期统一 remove，方法内不主动 close。

    提供两类接口：
    1. 聚合根生命周期接口（参考 task_repository 模式）：
       get_by_id / save / add / soft_delete —— 输入输出均为 APIAggregate
    2. 兼容应用层 dict 风格的 CRUD 接口：
       create_api / update_api / delete_api / get_api / list_apis 等
    """

    # ==================== 聚合根生命周期接口 ====================

    def get_by_id(self, api_id: int) -> Optional[APIAggregate]:
        """按 ID 加载 API 聚合根（PO → Entity）。

        Returns:
            APIAggregate 或 None（API 不存在）。
        """
        session = get_db_session()
        try:
            po = session.get(API, api_id)
            if po is None:
                return None
            return _api_po_to_entity(po)
        finally:
            # scoped_session 由请求/线程生命周期统一 remove，此处不主动 remove
            pass

    def save(self, aggregate: APIAggregate) -> None:
        """持久化聚合根变更（Entity → PO）。

        通过 _apply_aggregate_to_po 将聚合根字段写回 PO，不再依赖 ORM 引用。
        """
        session = get_db_session()
        try:
            po = session.get(API, aggregate.id)
            if po is None:
                # 不应发生（save 只更新已存在的聚合），但容错处理
                raise ValueError(f"API id={aggregate.id} 不存在，无法 save")
            _apply_aggregate_to_po(aggregate, po)
            session.commit()
        except Exception:
            session.rollback()
            raise

    def add(self, aggregate: APIAggregate) -> int:
        """新增 API 聚合根，返回新 ID。

        从聚合根字段构造新 PO；PO 必填但聚合根未承载的字段（如 meta）使用
        合理默认值以满足 NOT NULL 约束。
        """
        session = get_db_session()
        try:
            po = API(
                name=aggregate.name,
                api_url=aggregate.url,
                status=aggregate.status or "online",
                meta={},  # PO 必填字段，聚合根未承载，使用空对象
                deleted=aggregate.deleted,
                max_timeout=aggregate.timeout_seconds,
            )
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            # 将生成的 ID 回写聚合根
            aggregate.id = new_id
            return new_id
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, api_id: int) -> bool:
        """软删除 API。"""
        session = get_db_session()
        try:
            po = session.get(API, api_id)
            if po is None:
                return False
            po.deleted = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    # ==================== 兼容应用层 CRUD 接口 ====================

    def create_api(self, data: dict) -> APIAggregate:
        """创建 API 配置，返回聚合根。

        Args:
            data: 包含 API 字段的字典（name, vendor, api_url, ...）

        Returns:
            创建后的 APIAggregate 聚合根（含 id）。
        """
        session = get_db_session()
        try:
            new_api = API(
                name=data['name'],
                vendor=data.get('vendor'),
                api_url=data.get('api_url'),
                description=data.get('description'),
                meta=data.get('meta', {}),
                algorithm_type=data.get('algorithm_type'),
                max_process=data.get('max_process', 5),
                max_timeout=data.get('max_timeout', 30),
                max_audio_duration=data.get('max_audio_duration', 60),
                default_max_process=data.get('default_max_process', 5),
                default_max_timeout=data.get('default_max_timeout', 30),
                default_max_audio_duration=data.get('default_max_audio_duration', 60),
                status=data.get('status', 'online'),
                health_score=100,
                api_endpoints=data.get('api_endpoints', []),
            )
            session.add(new_api)
            session.commit()
            # PO → Entity 显式转换后再返回，避免泄漏 ORM
            return _api_po_to_entity(new_api)
        except Exception:
            session.rollback()
            raise

    def update_api(self, api_id: int, data: dict) -> Optional[APIAggregate]:
        """更新 API 配置，返回聚合根。

        Args:
            api_id: API ID
            data: 需要更新的字段字典

        Returns:
            更新后的 APIAggregate 聚合根，未找到返回 None。
        """
        session = get_db_session()
        try:
            api = session.query(API).filter(API.id == api_id, API.deleted == False).first()
            if not api:
                return None

            for key, value in data.items():
                if hasattr(api, key):
                    setattr(api, key, value)

            session.commit()
            return _api_po_to_entity(api)
        except Exception:
            session.rollback()
            raise

    def delete_api(self, api_id: int) -> bool:
        """软删除 API 配置（委托 soft_delete）。

        Args:
            api_id: API ID

        Returns:
            是否删除成功。
        """
        return self.soft_delete(api_id)

    def list_apis(self, page: int = 1, per_page: int = 10,
                 keyword: str = None, status: str = None,
                 algorithm_type: str = None) -> dict:
        """分页查询 API 列表，items 为 APIAggregate 聚合根列表。

        Args:
            page: 页码（从 1 开始）
            per_page: 每页条数
            keyword: 搜索关键字（name/description）
            status: 状态过滤
            algorithm_type: 算法类型过滤

        Returns:
            dict: {items, total, page, per_page, pages}
            其中 items 为 List[APIAggregate]。
        """
        session = get_db_session()
        query = session.query(API).filter(API.deleted == False)
        if keyword:
            query = query.filter(
                (API.name.like(f"%{keyword}%")) |
                (API.description.like(f"%{keyword}%"))
            )
        if status:
            query = query.filter(API.status == status)
        if algorithm_type:
            query = query.filter(API.algorithm_type == algorithm_type)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        # PO → Entity 显式转换后再返回
        return {
            'items': [_api_po_to_entity(po) for po in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def get_api(self, api_id: int) -> Optional[APIAggregate]:
        """查询单个 API 配置详情（仅未删除），返回聚合根。

        Args:
            api_id: API ID

        Returns:
            APIAggregate 聚合根，未找到返回 None。
        """
        session = get_db_session()
        try:
            po = session.query(API).filter(API.id == api_id, API.deleted == False).first()
            if po is None:
                return None
            return _api_po_to_entity(po)
        finally:
            pass

    def find_api_by_id(self, api_id: int) -> Optional[APIAggregate]:
        """根据 ID 查询 API，返回聚合根（不过滤 deleted）。"""
        return self.get_by_id(api_id)

    # ==================== 关联数据查询（不返回 API PO） ====================

    def find_api_ids_by_task(self, task_id: int) -> List[int]:
        """查询任务关联的 API ID 列表（通过 ACL 仓储调用 task_service.GetTaskApis）。"""
        try:
            return [ta.api_id for ta in _task_data_acl.get_task_apis(task_id) if ta.api_id]
        except Exception as e:
            logger.exception('find_api_ids_by_task failed: %s', e)
            return []

    def find_task_by_id(self, task_id: int) -> Optional[dict]:
        """根据 ID 查询测试任务（通过 ACL 仓储调用 task_service.GetTaskById，返回 dict）。"""
        try:
            return dto_to_dict(_task_data_acl.get_task_by_id(task_id))
        except Exception as e:
            logger.exception('find_task_by_id failed: %s', e)
            return None

    def task_exists(self, task_id: int) -> bool:
        """判断任务是否存在（通过 ACL 仓储调用 task_service.GetTaskById）。"""
        return self.find_task_by_id(task_id) is not None

    def check_api_in_running_tasks(self, api_id: int) -> list:
        """检查 API 是否被正在运行的任务引用。

        通过 ACL 仓储查询 task_service 的 TaskApis 和 Task，
        返回引用此 API 的运行中任务列表（dict 列表）。

        由于没有直接按 api_id 反查 Task 的 RPC，
        通过 APITestService 单例获取正在运行的任务列表，
        逐个查询其 TaskApis 检查是否引用此 api_id。
        """
        try:
            running_tasks = []

            # 从 APITestService 单例获取正在运行的任务 ID
            try:
                from api_test_service.core.api_test_service import api_test_service
                running_task_ids = list(api_test_service._running_tasks)
            except Exception:
                running_task_ids = []

            for tid in running_task_ids:
                try:
                    # 查询该任务关联的 API
                    api_ids = [ta.api_id for ta in _task_data_acl.get_task_apis(tid) if ta.api_id]
                    if api_id in api_ids:
                        # 查询 Task 详情
                        task_data = dto_to_dict(_task_data_acl.get_task_by_id(tid))
                        if task_data:
                            running_tasks.append(task_data)
                except Exception:
                    continue

            return running_tasks
        except Exception as e:
            logger.exception('check_api_in_running_tasks failed: %s', e)
            return []


# 模块级实例，便于直接注入
api_test_repository = APITestRepository()
