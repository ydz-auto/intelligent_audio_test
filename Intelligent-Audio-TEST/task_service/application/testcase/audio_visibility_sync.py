# -*- coding: utf-8 -*-
"""用例建/改后音频可见性跟随同步（INT-464 数据可见性 audio_service 域）。

task_service 是同步发起方：用例建/改/复制后，把用例引用音频的 visibility
同步到 audio_service（经 ACL gRPC `UpdateAudioVisibility`，DDD 红线——
禁止直写 audio 表）。audio_service 读路径不跨服务判定，音频的
`visibility` 列是跟随同步后的落库结果。

规则（唯一方案，无降级分支）：
- 音频可见性 = 所有引用该音频的用例可见性的**最宽松值**（任一 shared → shared，
  避免过度隐藏）
- 本用例 shared → 该音频必然 shared
- 本用例 private → 仅当不存在其他 shared 用例引用该音频时置 private
- 同步为尽力而为：gRPC 失败记录告警，不影响用例建/改主流程

实现口径：
- 引用音频来源：config.rounds[].audios[].audio_id + 各级背景噪音
  （background_noise / backgroundNoise）
- 最宽松聚合在 task_service 完成（audio_service 无用例视角，读路径不跨服务）；
  audio_service 侧 `UpdateAudioVisibility` 仅按值落列
- 用例自身可见性优先取请求载荷（`data['visibility']`），回落读取 PO
  `visibility` 列（本卡补最小列，与迁移 add_visibility_columns_int423 对齐）；
  NULL/缺失按迁移默认全 shared 聚合——避免过度隐藏
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shared.models.common_enums import Visibility
from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import TestCase

logger = logging.getLogger(__name__)

_SHARED_VALUE = Visibility.SHARED.value  # 'shared'
_PRIVATE_VALUE = Visibility.PRIVATE.value  # 'private'


def _collect_audio_ids_from_config(config) -> List[int]:
    """从用例 config 提取引用音频 ID 集合（rounds[].audios + 各级背景噪音）。"""
    if not isinstance(config, dict):
        return []
    audio_ids: List[int] = []

    def _add_bg_noise(bg_noise) -> None:
        if isinstance(bg_noise, dict) and bg_noise.get('audio_id') is not None:
            audio_ids.append(bg_noise['audio_id'])

    for round_item in config.get('rounds') or []:
        if not isinstance(round_item, dict):
            continue
        for audio_item in round_item.get('audios') or []:
            if isinstance(audio_item, dict) and audio_item.get('audio_id') is not None:
                audio_ids.append(audio_item['audio_id'])
        # 轮次级背景噪音（rounds[].backgroundNoise / background_noise 双命名兼容）
        _add_bg_noise(round_item.get('backgroundNoise') or round_item.get('background_noise'))
    # 顶层 audios（平面形态兜底）
    for audio_item in config.get('audios') or []:
        if isinstance(audio_item, dict) and audio_item.get('audio_id') is not None:
            audio_ids.append(audio_item['audio_id'])
    # 顶层背景噪音
    _add_bg_noise(config.get('background_noise') or config.get('backgroundNoise'))
    return audio_ids


def _other_shared_cases_reference(session, audio_id, exclude_case_id: Optional[str]) -> bool:
    """是否存在其他共享用例引用该音频（取最宽松聚合的查询侧）。

    test_cases.visibility 列为 INT-464 跟随用例同步的最小列（迁移已加列）。
    NULL 视为共享（存量行未回填，保持共享现状）：列缺失的旧环境同样按
    "任一非删除用例引用即视为共享"聚合——避免过度隐藏。
    """
    query = session.query(TestCase).filter(
        TestCase.deleted == False,  # noqa: E712
        TestCase.id != exclude_case_id,
    )
    has_vis_col = 'visibility' in TestCase.__table__.columns
    if has_vis_col:
        query = query.filter(
            (TestCase.visibility == _SHARED_VALUE) | (TestCase.visibility.is_(None))
        )
    for case in query.all():
        if audio_id in _collect_audio_ids_from_config(case.config):
            return True
    return False


def _most_permissive_visibility(audio_id, case_id, case_visibility, session) -> str:
    """计算音频目标可见性（所有引用用例的最宽松值）。

    - 本用例 shared → shared（任一 shared 即最宽松）
    - 本用例 private → 仅当无其他 shared 用例引用时 private，否则 shared
    """
    if case_visibility == _SHARED_VALUE:
        return _SHARED_VALUE
    if _other_shared_cases_reference(session, audio_id, case_id):
        return _SHARED_VALUE
    return _PRIVATE_VALUE


def sync_case_audio_visibility(case_id: str, case_visibility: Optional[str], config) -> None:
    """用例建/改/复制后同步引用音频可见性（尽力而为，不抛出）。

    Args:
        case_id: 本用例 ID（聚合查询排除自身）
        case_visibility: 本用例可见性（'shared'/'private'；None 按 shared 处理）
        config: 本用例 config（提取引用音频）

    Returns:
        None；gRPC 失败仅告警，不影响调用方主流程。
    """
    if not case_id or not config:
        return
    audio_ids = _collect_audio_ids_from_config(config)
    if not audio_ids:
        return
    case_visibility = case_visibility or _SHARED_VALUE
    if case_visibility not in (_SHARED_VALUE, _PRIVATE_VALUE):
        case_visibility = _SHARED_VALUE

    from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository

    # DB 未初始化（如单测 FakeRepo 场景 init_db 未调用）时不取 session：
    # 取之会在 scoped_session 里缓存一个无绑定 engine 的会话，污染后续
    # init_db 测试（缓存会话持有旧 bind=None）。此时无法聚合其他用例，
    # 按本用例可见性直传（尽力而为）。
    from shared.models.database import get_engine
    session = get_db_session() if get_engine() is not None else None

    seen: set = set()
    for audio_id in audio_ids:
        if audio_id in seen:
            continue
        seen.add(audio_id)
        try:
            if session is None:
                target = case_visibility
            else:
                target = _most_permissive_visibility(audio_id, case_id, case_visibility, session)
            audio_acl_repository.update_audio_visibility(audio_id, target)
        except Exception:
            logger.warning(
                "用例 %s 同步音频可见性失败 (audio_id=%s): ",
                case_id, audio_id, exc_info=True,
            )
