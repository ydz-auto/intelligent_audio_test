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
from typing import Dict, List, Optional

from shared.models.database import get_db_session
from shared.utils.dto_utils import dto_to_dict

# 跨服务 gRPC 调用经 ACL 仓储（返回 DTO），本仓储仅保留本地 API PO 的 DB 访问
from api_test_service.infrastructure.acl import TaskDataAclRepositoryImpl

# API PO 归属本服务（shared.models.models.API 已改为从此处 re-export）
from api_test_service.infrastructure.persistence.models import API
# 领域聚合根
from api_test_service.domain.entities import APIAggregate
from api_test_service.domain.entities.api import (
    derive_api_keys_summary,
    normalize_output_types,
    redact_endpoint_keys,
)
from api_test_service.domain.repositories.api_test_repository_abc import (
    APITestRepositoryABC,
)

logger = logging.getLogger(__name__)

# 跨服务 ACL 仓储单例
_task_data_acl = TaskDataAclRepositoryImpl()


# ========== PO ↔ Entity 转换 ==========

def _api_po_to_entity(po: API) -> APIAggregate:
    """API PO → APIAggregate 聚合根。

    PO 上聚合根承载的字段全量映射；`_api_to_dict` 经 getattr 兜底直取，
    未承载的字段读回恒 None / []（INT-1338 读侧回显缺口根因）。

    字段映射说明：
    - po.max_timeout    → aggregate.timeout_seconds（复用 PO 的超时配置）
    - po.status         → aggregate.status（PO 使用 online/offline，聚合根 status
                          字段为 str，直接透传以保留前端可读词汇）
    - po.meta.api_keys  → aggregate.api_keys_summary（INT-1177 密钥池非敏感
                          摘要 {count, tails[]}；完整密钥不承载，零响应）
    - po.meta           → aggregate.meta（INT-1338：承载但剥离 api_keys，
                          聚合根零明文；摘要继续经 api_keys_summary 承载）
    - po.api_endpoints  → aggregate.endpoint_keys_summary（INT-1230 审计 D6'：
                          逐端点内嵌 api_keys_summary、完整 api_keys 剥离，
                          聚合根零明文；读侧序列化逐端点输出）
    - po.api_endpoints  → aggregate.api_endpoints（唯一端点来源，INT-1361）
    - 其余 PO 无对应列的字段（method / headers / body_template / retry_count）
      使用聚合根默认值
    """
    # INT-1177：聚合根不承载完整 api_keys（零明文），映射时剥离
    raw_meta = po.meta or {}
    if isinstance(raw_meta, dict) and 'api_keys' in raw_meta:
        raw_meta = {k: v for k, v in raw_meta.items() if k != 'api_keys'}
    endpoint_summaries = []
    for ep in (po.api_endpoints or []):
        redacted = redact_endpoint_keys(ep)
        if redacted is not None:
            endpoint_summaries.append(redacted)
    return APIAggregate(
        id=po.id,
        name=po.name,
        timeout_seconds=po.max_timeout or 30,
        status=po.status or "active",
        deleted=po.deleted or False,
        output_types=normalize_output_types(po.output_types),
        # INT-1799：协议 × 流式性正交两列（执行道只由 streaming 决定）
        protocol=po.protocol or "http",
        streaming=bool(po.streaming),
        adapter_class=po.adapter_class,
        audio_config=po.audio_config,
        rms_spl_mapping_id=po.rms_spl_mapping_id,
        proxy_type=po.proxy_type,
        proxy_url=po.proxy_url,
        api_keys_summary=derive_api_keys_summary((po.meta or {}).get('api_keys')),
        # INT-1338 读侧回显字段：PO 全字段承载到聚合根
        vendor=po.vendor,
        meta=raw_meta,
        description=po.description,
        algorithm_type=po.algorithm_type,
        default_max_process=po.default_max_process,
        default_max_timeout=po.default_max_timeout,
        default_max_audio_duration=po.default_max_audio_duration,
        health_score=po.health_score,
        api_endpoints=po.api_endpoints or [],
        created_at=po.created_at,
        updated_at=po.updated_at,
        endpoint_keys_summary=endpoint_summaries,
    )


def _apply_aggregate_to_po(aggregate: APIAggregate, po: API) -> None:
    """将聚合根的可写字段映射回 PO（不含 id / created_at / deleted_at 等元数据）。

    聚合根中无 PO 对应列的字段（method / headers / body_template /
    retry_count）不回写。rms_spl_mapping_id 回写保持与 set-default /
    update_api 直改 PO 同源（聚合根承载后经 save 路径不丢指针）。

    INT-1338：读侧新增承载字段同步回写（save 路径一致性）；NOT NULL 列
    （meta / default_max_* / health_score / api_endpoints）仅在聚合根有值
    时回写，避免手工构造的空缺值破坏约束。
    """
    po.name = aggregate.name
    po.status = aggregate.status
    po.deleted = aggregate.deleted
    po.max_timeout = aggregate.timeout_seconds
    # INT-1799：协议 × 流式性回写（device_type 不再回写——已废弃）
    po.protocol = aggregate.protocol or 'http'
    po.streaming = bool(aggregate.streaming)
    po.rms_spl_mapping_id = aggregate.rms_spl_mapping_id
    po.proxy_type = aggregate.proxy_type
    po.proxy_url = aggregate.proxy_url
    po.vendor = aggregate.vendor
    po.description = aggregate.description
    po.algorithm_type = aggregate.algorithm_type
    if aggregate.meta is not None:
        new_meta = dict(aggregate.meta)
        # 聚合根不承载完整 api_keys（零明文），回写时保留 PO 既有密钥池
        if isinstance(po.meta, dict) and po.meta.get('api_keys') is not None:
            new_meta['api_keys'] = po.meta['api_keys']
        po.meta = new_meta
    if aggregate.default_max_process is not None:
        po.default_max_process = aggregate.default_max_process
    if aggregate.default_max_timeout is not None:
        po.default_max_timeout = aggregate.default_max_timeout
    if aggregate.default_max_audio_duration is not None:
        po.default_max_audio_duration = aggregate.default_max_audio_duration
    if aggregate.health_score is not None:
        po.health_score = aggregate.health_score
    if aggregate.api_endpoints is not None:
        po.api_endpoints = aggregate.api_endpoints


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
                status=aggregate.status or "online",
                meta=dict(aggregate.meta or {}),  # PO 必填字段；聚合根承载（api_keys 已剥离）
                deleted=aggregate.deleted,
                max_timeout=aggregate.timeout_seconds,
                proxy_type=aggregate.proxy_type,
                proxy_url=aggregate.proxy_url,
                vendor=aggregate.vendor,
                description=aggregate.description,
                algorithm_type=aggregate.algorithm_type,
                default_max_process=aggregate.default_max_process or 5,
                default_max_timeout=aggregate.default_max_timeout or 30,
                default_max_audio_duration=aggregate.default_max_audio_duration or 60,
                health_score=aggregate.health_score if aggregate.health_score is not None else 100,
                api_endpoints=aggregate.api_endpoints or [],
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
        """软删除 API。

        apis 表无 deleted_by_user_id 列（INT-842 现状注记），软删操作人
        以 updated_by_user_id 记录（对齐 api_gateway laboratory 仓储口径）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        try:
            po = session.get(API, api_id)
            if po is None:
                return False
            po.deleted = True
            po.updated_by_user_id = get_current_user_id()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    # ==================== 兼容应用层 CRUD 接口 ====================

    def create_api(self, data: dict) -> APIAggregate:
        """创建 API 配置，返回聚合根。

        Args:
            data: 包含 API 字段的字典（name, vendor, description, ...）

        Returns:
            创建后的 APIAggregate 聚合根（含 id）。
        """
        session = get_db_session()
        try:
            from shared.infrastructure.user_context import get_current_user_id
            new_api = API(
                name=data['name'],
                vendor=data.get('vendor'),
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
                output_types=data.get('output_types', []),
                # INT-1799：协议 × 流式性（写侧已校验；此处只做缺省兜底，
                # device_type 不再写入——列保留但废弃）
                protocol=data.get('protocol') or 'http',
                streaming=bool(data.get('streaming', False)),
                adapter_class=data.get('adapter_class'),
                audio_config=data.get('audio_config'),
                created_by_user_id=get_current_user_id(),
                proxy_type=data.get('proxy_type'),
                proxy_url=data.get('proxy_url'),            )
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
            from shared.infrastructure.user_context import get_current_user_id
            api = session.query(API).filter(API.id == api_id, API.deleted == False).first()
            if not api:
                return None

            for key, value in data.items():
                if hasattr(api, key):
                    setattr(api, key, value)

            # 操作人以上下文为准（客户端自报值不充当操作人）；最后设置覆盖 data 中同名键
            api.updated_by_user_id = get_current_user_id()

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
                 algorithm_type: str = None,
                 protocol: str = None, streaming: bool = None) -> dict:
        """分页查询 API 列表，items 为 APIAggregate 聚合根列表。

        Args:
            page: 页码（从 1 开始）
            per_page: 每页条数
            keyword: 搜索关键字（name/description）
            status: 状态过滤
            algorithm_type: 算法类型过滤
            protocol: 协议等值过滤（INT-1799；规范值 http/websocket/sse/grpc）
            streaming: 流式性等值过滤（INT-1799；None = 不过滤）

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
        # INT-1799：协议 / 流式性两维等值筛选（两者相互独立，可单用可组合）
        if protocol:
            query = query.filter(API.protocol == protocol)
        if streaming is not None:
            query = query.filter(API.streaming == bool(streaming))

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

    def get_api_meta(self, api_id: int) -> Optional[Dict]:
        """读取 API 存储的 meta 原始 dict（写侧合并密钥池用，PO 不出仓储）。

        INT-1177 返工(2)：update 合并语义——入参 meta 未含 api_keys 时保留
        既有密钥池。聚合根不承载完整 meta（仅摘要），故写侧经本方法读取
        存储原始 meta；返回拷贝，外部修改不影响 PO。
        """
        session = get_db_session()
        try:
            po = session.query(API).filter(
                API.id == api_id, API.deleted == False).first()
            if po is None:
                return None
            return dict(po.meta or {})
        finally:
            pass

    def get_api_endpoints(self, api_id: int) -> Optional[List[Dict]]:
        """读取 API 存储的 api_endpoints 原始列表（写侧合并端点级密钥池用，
        PO 不出仓储）。

        INT-1230 审计 D2'/D6'（endpoint 级返工）：读侧剥离完整 api_keys，
        编辑表单不会重发密钥池——整块覆盖会静默清空既有池。update 经本方法
        读取存储原始端点（含完整 api_keys）以按 URL 匹配保留未重发的池；
        返回深拷贝，外部修改不影响 PO。
        """
        session = get_db_session()
        try:
            po = session.query(API).filter(
                API.id == api_id, API.deleted == False).first()
            if po is None:
                return None
            import copy
            return copy.deepcopy(list(po.api_endpoints or []))
        finally:
            pass

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
