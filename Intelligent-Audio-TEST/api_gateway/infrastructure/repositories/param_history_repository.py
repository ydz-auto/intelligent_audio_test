# -*- coding: utf-8 -*-
"""参数变更历史仓储（api_gateway infrastructure）。

职责：
1. 采集某作用域的**覆盖行快照**（只读 ``algorithm_*`` / ``param_mappings``，
   按 api_id / device_id 过滤，算法级默认行与策略行不在快照内）；
2. 追加 / 读取 / 裁剪版本记录（``param_change_history``，网关直管表）。

快照行字段与写接口同口径（snake_case），回滚时可直接回灌。
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from api_gateway.infrastructure.models.param_change_history_model import ParamChangeHistory
from shared.models.database import get_db_session

SCOPE_DEVICE = 'device'
SCOPE_API = 'api'

ACTION_SAVE = 'save'
ACTION_RESTORE = 'restore'

# 每个作用域保留的版本数（超出按 id 倒序裁掉）
MAX_VERSIONS_PER_SCOPE = 50

_PARAM_COLUMNS = (
    'id, param_code, param_name, label, param_type, direction, required, '
    'default_value, validation_rules, help_text, ui_order, hidden'
)
_API_PARAM_COLUMNS = _PARAM_COLUMNS + ', field_path'
_MAPPING_COLUMNS = (
    'id, source, source_param, source_direction, dimension_id, '
    'target_param, transform_type'
)

_SCOPE_SPECS = {
    SCOPE_API: {
        'params_table': 'algorithm_api_params',
        'params_columns': _API_PARAM_COLUMNS,
        'scope_column': 'api_id',
    },
    SCOPE_DEVICE: {
        'params_table': 'algorithm_device_params',
        'params_columns': _PARAM_COLUMNS,
        'scope_column': 'device_id',
    },
}


def _rows(result) -> List[Dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


class ParamHistoryRepository:
    """``param_change_history`` 读写 + 覆盖行快照。"""

    # ---- 快照 ----

    def snapshot(self, scope: str, scope_id: int, algorithm_type: str) -> Dict[str, Any]:
        """读取该作用域的覆盖行（params / mappings），不含算法级与策略层。"""
        spec = _SCOPE_SPECS.get(scope)
        if spec is None:
            raise ValueError(f'未知作用域: {scope}')
        session = get_db_session()
        params = _rows(session.execute(
            text(
                f"SELECT {spec['params_columns']} FROM {spec['params_table']} "
                f"WHERE algorithm_type = :algo AND {spec['scope_column']} = :scope_id "
                f"AND deleted = false ORDER BY ui_order, id"
            ),
            {'algo': algorithm_type, 'scope_id': int(scope_id)},
        ))
        mappings = _rows(session.execute(
            text(
                f"SELECT {_MAPPING_COLUMNS} FROM param_mappings "
                f"WHERE algorithm_type = :algo AND {spec['scope_column']} = :scope_id "
                f"AND deleted = false ORDER BY id"
            ),
            {'algo': algorithm_type, 'scope_id': int(scope_id)},
        ))
        return {'params': params, 'mappings': mappings}

    # ---- 版本 ----

    def add(
        self,
        scope: str,
        scope_id: int,
        algorithm_type: str,
        payload: Dict[str, Any],
        action: str = ACTION_SAVE,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """追加一个版本；同作用域 version 自增，并裁剪到最近 N 个版本。"""
        session = get_db_session()
        next_version = int(session.execute(
            text(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM param_change_history "
                "WHERE scope = :scope AND scope_id = :scope_id "
                "AND algorithm_type = :algo"
            ),
            {'scope': scope, 'scope_id': int(scope_id), 'algo': algorithm_type},
        ).scalar_one())
        row = ParamChangeHistory(
            scope=scope,
            scope_id=int(scope_id),
            algorithm_type=algorithm_type,
            version=next_version,
            action=action,
            payload=payload,
            operator=operator,
        )
        session.add(row)
        session.flush()
        session.execute(
            text(
                "DELETE FROM param_change_history WHERE scope = :scope "
                "AND scope_id = :scope_id AND algorithm_type = :algo AND id NOT IN ("
                "  SELECT id FROM param_change_history WHERE scope = :scope "
                "  AND scope_id = :scope_id AND algorithm_type = :algo "
                "  ORDER BY id DESC LIMIT :keep)"
            ),
            {
                'scope': scope, 'scope_id': int(scope_id), 'algo': algorithm_type,
                'keep': MAX_VERSIONS_PER_SCOPE,
            },
        )
        session.commit()
        return {
            'id': row.id,
            'version': row.version,
            'action': row.action,
        }

    def record_snapshot(
        self,
        scope: str,
        scope_id: int,
        algorithm_type: str,
        action: str = ACTION_SAVE,
        operator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """采集当前覆盖行并追加版本（写操作成功后的统一入口）。"""
        payload = self.snapshot(scope, scope_id, algorithm_type)
        return self.add(scope, scope_id, algorithm_type, payload, action, operator)

    def list_versions(
        self, scope: str, scope_id: int, algorithm_type: str,
        limit: int = MAX_VERSIONS_PER_SCOPE,
    ) -> List[Dict[str, Any]]:
        session = get_db_session()
        rows = session.query(ParamChangeHistory).filter_by(
            scope=scope, scope_id=int(scope_id), algorithm_type=algorithm_type,
        ).order_by(ParamChangeHistory.id.desc()).limit(limit).all()
        return [
            {
                'id': row.id,
                'version': row.version,
                'action': row.action,
                'operator': row.operator,
                'createdAt': row.created_at.isoformat() if row.created_at else None,
                'paramCount': len((row.payload or {}).get('params') or []),
                'mappingCount': len((row.payload or {}).get('mappings') or []),
                'payload': row.payload or {},
            }
            for row in rows
        ]

    def get(self, history_id: int) -> Optional[Dict[str, Any]]:
        row = get_db_session().get(ParamChangeHistory, int(history_id))
        if row is None:
            return None
        return {
            'id': row.id,
            'scope': row.scope,
            'scopeId': row.scope_id,
            'algorithmType': row.algorithm_type,
            'version': row.version,
            'action': row.action,
            'payload': row.payload or {},
        }

    # ---- 删除前定位作用域 ----

    def lookup_scope(self, table: str, row_id: int) -> Optional[Tuple[str, int, str]]:
        """查参数 / 映射行所属作用域：返回 (scope, scope_id, algorithm_type)。

        ``table`` 只接受 ``params`` / ``mappings``；删除接口没有 body，
        需要先定位再记录版本。

        参数表（``algorithm_device_params`` / ``algorithm_api_params``）各自
        独立自增 id，同号行很常见，且软删行会长期占号。判定必须与
        ``ParamRepository.soft_delete`` 的删除口径一致：**设备表优先、只认
        未删除行**，否则会把一个设备参数字段的历史记到同号的 API / 其它算法
        作用域上（INT-2344 实测：设备参数 id=238 与某 API 的软删行同号，
        历史被写到 device/17/voice_llm）。
        """
        session = get_db_session()
        if table == 'params':
            for scope in (SCOPE_DEVICE, SCOPE_API):
                spec = _SCOPE_SPECS[scope]
                row = session.execute(
                    text(
                        f"SELECT algorithm_type, {spec['scope_column']} AS scope_id "
                        f"FROM {spec['params_table']} WHERE id = :id "
                        f"AND deleted = false"
                    ),
                    {'id': int(row_id)},
                ).mappings().first()
                if row is not None and row['scope_id'] is not None:
                    return scope, int(row['scope_id']), row['algorithm_type']
            return None
        row = session.execute(
            text(
                "SELECT algorithm_type, api_id, device_id FROM param_mappings "
                "WHERE id = :id AND deleted = false"
            ),
            {'id': int(row_id)},
        ).mappings().first()
        if row is None:
            return None
        if row['device_id'] is not None:
            return SCOPE_DEVICE, int(row['device_id']), row['algorithm_type']
        if row['api_id'] is not None:
            return SCOPE_API, int(row['api_id']), row['algorithm_type']
        return None


param_history_repository = ParamHistoryRepository()
