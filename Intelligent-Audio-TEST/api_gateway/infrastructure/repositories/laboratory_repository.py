# -*- coding: utf-8 -*-
"""api_gateway 基础设施层 —— 实验室仓储实现（INT-493/INT-537 拆分①）

实验室是网关自有域（设计文档 §7.2 授权），本仓储直连共享库 laboratories 表，
复用 shared.models.database.get_db_session()（与 read_models TODO(DB穿透)
先例一致）。命令/查询均在调用方（application service）管理事务。

表结构见 scripts/migrations/202608/add_laboratory_tables.py Step1：
id/code/name/building/floor/room_number/description/status/deleted/
deleted_at/created_by_user_id/updated_by_user_id/created_at/updated_at。
"""
from typing import Optional, Tuple

from sqlalchemy import text

from shared.models.database import get_db_session, utc8now
from api_gateway.domain.entities.laboratory import Laboratory
from api_gateway.domain.repositories.laboratory_repository import LaboratoryRepository

# 查询列清单（RETURNING / SELECT 复用），保持与实体字段一致
_LAB_COLUMNS = (
    'id, code, name, building, floor, room_number, description, status, '
    'deleted, deleted_at, created_by_user_id, updated_by_user_id, '
    'created_at, updated_at'
)


def _row_to_lab(row) -> Laboratory:
    return Laboratory.from_row(row)


class LaboratoryRepositoryImpl(LaboratoryRepository):
    """SQLAlchemy 实现（raw SQL，无 ORM PO —— laboratories 为网关自有域）。"""

    def list(self, status: Optional[str] = None, page: int = 1,
             per_page: int = 20) -> Tuple[list[Laboratory], int]:
        session = get_db_session()
        where = 'deleted = FALSE'
        params = {}
        if status:
            where += ' AND status = :status'
            params['status'] = status

        total = session.execute(
            text(f'SELECT COUNT(*) FROM laboratories WHERE {where}'), params
        ).scalar_one()

        offset = (page - 1) * per_page
        rows = session.execute(
            text(
                f'SELECT {_LAB_COLUMNS} FROM laboratories '
                f'WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset'
            ),
            {**params, 'limit': per_page, 'offset': offset},
        ).fetchall()
        return [_row_to_lab(r) for r in rows], int(total or 0)

    def get(self, lab_id: int) -> Optional[Laboratory]:
        row = get_db_session().execute(
            text(
                f'SELECT {_LAB_COLUMNS} FROM laboratories '
                'WHERE id = :lab_id AND deleted = FALSE'
            ),
            {'lab_id': lab_id},
        ).first()
        return _row_to_lab(row) if row else None

    def get_by_code(self, code: str) -> Optional[Laboratory]:
        row = get_db_session().execute(
            text(
                f'SELECT {_LAB_COLUMNS} FROM laboratories WHERE code = :code'
            ),
            {'code': code},
        ).first()
        return _row_to_lab(row) if row else None

    def create(self, data: dict) -> Laboratory:
        now = utc8now()
        row = get_db_session().execute(
            text(
                f'INSERT INTO laboratories '
                '(code, name, building, floor, room_number, description, status, '
                ' created_by_user_id, created_at, updated_at) '
                'VALUES (:code, :name, :building, :floor, :room_number, '
                '        :description, :status, :created_by_user_id, '
                '        :created_at, :updated_at) '
                f'RETURNING {_LAB_COLUMNS}'
            ),
            {
                'code': data['code'],
                'name': data['name'],
                'building': data.get('building'),
                'floor': data.get('floor'),
                'room_number': data.get('room_number'),
                'description': data.get('description'),
                'status': data.get('status', 'active'),
                'created_by_user_id': data.get('created_by_user_id'),
                'created_at': now,
                'updated_at': now,
            },
        ).first()
        return _row_to_lab(row)

    def update(self, lab_id: int, data: dict) -> Optional[Laboratory]:
        if not data:
            return self.get(lab_id)

        setters = []
        params = {'lab_id': lab_id}
        for col in ('code', 'name', 'building', 'floor', 'room_number',
                    'description', 'status'):
            if col in data:
                setters.append(f'{col} = :{col}')
                params[col] = data[col]
        params['updated_by_user_id'] = data.get('updated_by_user_id')
        params['updated_at'] = utc8now()
        setters.append('updated_by_user_id = :updated_by_user_id')
        setters.append('updated_at = :updated_at')

        row = get_db_session().execute(
            text(
                f'UPDATE laboratories SET {", ".join(setters)} '
                'WHERE id = :lab_id AND deleted = FALSE '
                f'RETURNING {_LAB_COLUMNS}'
            ),
            params,
        ).first()
        return _row_to_lab(row) if row else None

    def delete(self, lab_id: int, deleted_by_user_id: Optional[int] = None) -> bool:
        result = get_db_session().execute(
            text(
                'UPDATE laboratories SET deleted = TRUE, deleted_at = :deleted_at, '
                'updated_by_user_id = :updated_by_user_id '
                'WHERE id = :lab_id AND deleted = FALSE'
            ),
            {
                'lab_id': lab_id,
                'deleted_at': utc8now(),
                'updated_by_user_id': deleted_by_user_id,
            },
        )
        return result.rowcount > 0
