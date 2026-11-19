# -*- coding: utf-8 -*-
"""系统选项密钥仓储接口（ABC）。

对齐 DDD 红线：应用服务只依赖本接口；基础设施层持有 SQLAlchemy 实现。
"""
from abc import ABC, abstractmethod
from typing import Dict, List


class SystemOptionSecretRepository(ABC):
    """评估配置密钥仓储接口（密文与掩码，不暴露明文）。"""

    @abstractmethod
    def list_meta(self) -> List[Dict]:
        """全部密钥的元信息（key/mask/updated_at/updated_by，无密文明文）。"""

    @abstractmethod
    def get_ciphertext(self, key: str) -> Dict:
        """单键密文（key/ciphertext/key_version），不存在返回空 dict。"""

    @abstractmethod
    def upsert(self, key: str, ciphertext: str, key_version: int,
               value_mask: str, updated_by: int) -> None:
        """写入/覆盖密钥（写侧）。"""
