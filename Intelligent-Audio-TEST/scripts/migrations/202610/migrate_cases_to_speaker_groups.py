# -*- coding: utf-8 -*-
"""历史用例迁移到「逻辑音箱」（一次性脚本，幂等可重跑）。

背景：用例从此只关联逻辑音箱（playback_speaker_group_id），不再直接绑实体播放设备。
本脚本做两件事：

1. 补建逻辑音箱组：所有在用播放设备都要有一个同名逻辑音箱（名字与音箱名一致）。
   同名设备（不同实验室）进同一个逻辑音箱；设备已有组则跳过；
   没有 lab_id 的设备仍建组（无法绑定实验室，只报不绑），无名设备跳过并报告。
2. 改写用例里的实体设备引用：
   - ``rounds[].audios[].playback_device_id`` → ``playback_speaker_group_id``
   - ``background_noise.device_ids[]`` → ``playback_speaker_group_ids[]``
   - ``interferers[].playback_device_id`` / ``interferers[].device.id`` → ``playback_speaker_group_id``
   - ``algorithm_params`` 里的 ``voiceprint.playback_device_id`` → ``playback_speaker_group_id``
   找不到对应逻辑音箱的引用**保持原样**并列入报告（执行侧仍按老路径「所属组 → 同名 →
   在线 → 任一」换绑，不会静默换错音箱）。

用法：
    python scripts/migrate_cases_to_speaker_groups.py --dry-run   # 只统计，不写库
    python scripts/migrate_cases_to_speaker_groups.py             # 执行迁移
"""

import argparse
import copy
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 迁移写入的组描述
AUTO_GROUP_DESCRIPTION = '由历史播放设备名称自动迁移'
GROUP_NAME_MAX_LEN = 100


def _as_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _new_stats():
    return {
        'groups_created': [],
        'items_created': 0,
        'unbound_devices': [],
        'cases_updated': 0,
        'device_refs': 0,
        'bg_refs': 0,
        'unmapped_devices': set(),
        'skipped_devices': [],
    }


def ensure_speaker_groups(session, dry_run, stats):
    """所有播放设备都建同名逻辑音箱，返回 {playback_device_id: group_id}（含已有映射）。

    组名与音箱名一致；同名设备（跨实验室同一物理位置）共用一个逻辑音箱。
    无 lab_id 的音箱照样建组，但无法写「组—实验室—设备」条目，记入 unbound_devices。
    """
    from device_service.infrastructure.persistence.models import (
        PlaybackDevice,
        PlaybackSpeakerGroup,
        PlaybackSpeakerGroupItem,
    )

    device_to_group = {
        item.playback_device_id: item.group_id
        for item in session.query(PlaybackSpeakerGroupItem).all()
    }
    group_id_by_name = {
        group.name: group.id for group in session.query(PlaybackSpeakerGroup).all()
    }
    devices = (
        session.query(PlaybackDevice)
        .filter(PlaybackDevice.is_deleted == 0)
        .order_by(PlaybackDevice.lab_id, PlaybackDevice.id)
        .all()
    )

    virtual_seq = 0
    for device in devices:
        if device.id in device_to_group:
            continue
        name = (device.name or '').strip()[:GROUP_NAME_MAX_LEN]
        if not name:
            stats['skipped_devices'].append(device.id)
            continue

        group_id = group_id_by_name.get(name)
        if group_id is None:
            virtual_seq += 1
            if dry_run:
                # 干跑：用负 id 占位，保证同名设备共用同一占位组且不落库
                group_id = -virtual_seq
            else:
                group = PlaybackSpeakerGroup(name=name, description=AUTO_GROUP_DESCRIPTION)
                session.add(group)
                session.flush()
                group_id = group.id
            group_id_by_name[name] = group_id
            stats['groups_created'].append(name)
        device_to_group[device.id] = group_id

        lab_id = _as_int(device.lab_id)
        if lab_id is None:
            stats['unbound_devices'].append(device.id)
            continue
        if not dry_run:
            session.add(PlaybackSpeakerGroupItem(
                group_id=group_id, lab_id=lab_id, playback_device_id=device.id))
        stats['items_created'] += 1

    return device_to_group


def _migrate_node(node, device_to_group, stats):
    """递归改写实体设备引用为逻辑音箱引用；返回是否有改动"""
    changed = False
    if isinstance(node, dict):
        device_id = _as_int(node.get('playback_device_id'))
        if device_id is not None:
            group_id = device_to_group.get(device_id)
            if group_id is not None:
                node['playback_speaker_group_id'] = group_id
                node.pop('playback_device_id', None)
                node.pop('playback_device_name', None)
                stats['device_refs'] += 1
                changed = True
            else:
                stats['unmapped_devices'].add(device_id)

        device_ids = node.get('device_ids')
        # 背景噪声段：{audio_id, spl, device_ids[], loop}；限制 audio_id 存在，避免误伤其它数组
        if isinstance(device_ids, list) and 'audio_id' in node:
            group_ids, unmapped = [], set()
            for raw in device_ids:
                did = _as_int(raw)
                if did is None:
                    continue
                group_id = device_to_group.get(did)
                if group_id is None:
                    unmapped.add(did)
                    continue
                group_ids.append(group_id)
            if group_ids:
                node['playback_speaker_group_ids'] = list(dict.fromkeys(group_ids))
                node.pop('device_ids', None)
                stats['bg_refs'] += len(group_ids)
                stats['unmapped_devices'] |= unmapped
                changed = True

        # 干扰人嵌套结构：interferer.device.id
        nested = node.get('device')
        if isinstance(nested, dict):
            nested_id = _as_int(nested.get('id'))
            group_id = device_to_group.get(nested_id) if nested_id is not None else None
            if group_id is not None:
                node['playback_speaker_group_id'] = group_id
                node.pop('device', None)
                stats['device_refs'] += 1
                changed = True
            elif nested_id is not None:
                stats['unmapped_devices'].add(nested_id)

        for value in list(node.values()):
            if _migrate_node(value, device_to_group, stats):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _migrate_node(item, device_to_group, stats):
                changed = True
    return changed


def migrate_cases(session, device_to_group, dry_run, stats):
    """把 test_cases.config / algorithm_params 迁移到逻辑音箱引用"""
    from task_service.infrastructure.persistence.models import TestCase

    for case in session.query(TestCase).all():
        case_changed = False

        if isinstance(case.config, dict):
            new_config = copy.deepcopy(case.config)
            if _migrate_node(new_config, device_to_group, stats):
                case_changed = True
                if not dry_run:
                    case.config = new_config

        if case.algorithm_params:
            new_params = copy.deepcopy(case.algorithm_params)
            if _migrate_node(new_params, device_to_group, stats):
                case_changed = True
                if not dry_run:
                    case.algorithm_params = new_params

        if case_changed:
            stats['cases_updated'] += 1

    if not dry_run:
        session.commit()


def _print_report(dry_run, stats):
    prefix = '[dry-run] ' if dry_run else ''
    print(f"\n{prefix}逻辑音箱组新建 {len(stats['groups_created'])} 个，"
          f"绑定实验室设备 {stats['items_created']} 条")
    if stats['groups_created']:
        print(f"{prefix}新建组: {', '.join(stats['groups_created'])}")
    print(f"{prefix}用例改写 {stats['cases_updated']} 条，"
          f"设备引用 {stats['device_refs']} 处，背景噪声引用 {stats['bg_refs']} 处")
    if stats['unmapped_devices']:
        print(f"{prefix}未找到逻辑音箱的设备（保持原样，执行侧老路径兜底）: "
              f"{sorted(stats['unmapped_devices'])}")
    if stats['unbound_devices']:
        print(f"{prefix}已建同名逻辑音箱但音箱未绑定实验室（无法绑定设备）: "
              f"{sorted(stats['unbound_devices'])}")
    if stats['skipped_devices']:
        print(f"{prefix}跳过设备（无名称，无法同名建组）: {sorted(stats['skipped_devices'])}")
    if dry_run:
        print('干跑结束，未写库')


def main():
    parser = argparse.ArgumentParser(description='历史用例迁移到逻辑音箱')
    parser.add_argument('--dry-run', action='store_true', help='只统计不写库')
    args = parser.parse_args()

    # 导入全部 PO，保证 relationship / 元数据完整
    import scripts.create_all_tables  # noqa: F401
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_project_root, '.env'))
    from shared.models.database import init_db, get_db_session

    init_db(pool_size=5)
    session = get_db_session()
    stats = _new_stats()
    try:
        device_to_group = ensure_speaker_groups(session, args.dry_run, stats)
        migrate_cases(session, device_to_group, args.dry_run, stats)
        _print_report(args.dry_run, stats)
    finally:
        session.close()


if __name__ == '__main__':
    main()
