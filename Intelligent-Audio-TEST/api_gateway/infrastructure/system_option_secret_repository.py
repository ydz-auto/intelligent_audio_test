# -*- coding: utf-8 -*-
"""系统选项密钥仓储实现（SQLAlchemy）。

表：system_option_secrets（密钥只存密文 + 掩码）。
DB session 走 shared get_db_session()（与 system_options 同口径）。
"""
from typing import Dict, List

from shared.models.database import get_db_session
from api_gateway.domain.repositories.system_option_secret_repository import (
    SystemOptionSecretRepository,
)
from api_gateway.infrastructure.models.system_option_secret_model import (
    SystemOptionSecret,
)


class SystemOptionSecretRepositoryImpl(SystemOptionSecretRepository):
    """SQLAlchemy 实现（读侧只读、写侧显式 commit）。"""

    def list_meta(self) -> List[Dict]:
        session = get_db_session()
        rows = session.query(SystemOptionSecret).all()
        return [
            {
                'key': row.key,
                'mask': row.value_mask,
                'updated_by': row.updated_by,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

    def get_ciphertext(self, key: str) -> Dict:
        session = get_db_session()
        row = session.query(SystemOptionSecret).filter_by(key=key).one_or_none()
        if row is None:
            return {}
        return {
            'key': row.key,
            'ciphertext': row.ciphertext,
            'key_version': row.key_version,
        }

    def upsert(self, key: str, ciphertext: str, key_version: int,
               value_mask: str, updated_by: int) -> None:
        session = get_db_session()
        row = session.query(SystemOptionSecret).filter_by(key=key).one_or_none()
        if row is None:
            session.add(SystemOptionSecret(
                key=key, ciphertext=ciphertext, key_version=key_version,
                value_mask=value_mask, updated_by=updated_by))
        else:
            row.ciphertext = ciphertext
            row.key_version = key_version
            row.value_mask = value_mask
            row.updated_by = updated_by
        session.commit()
