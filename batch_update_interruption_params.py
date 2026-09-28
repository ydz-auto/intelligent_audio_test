# -*- coding: utf-8 -*-
"""批量给打断用例 JSON 添加 stop_intent 和 is_return_to_topic 字段"""
import json
import os
import glob

DIR = r'e:\w60085971\全双工测试序列-人工录制\打断、话轮、环境理解\打断与恢复'


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'y', '是')
    return False


updated = 0
for json_path in sorted(glob.glob(os.path.join(DIR, '*.json'))):
    fname = os.path.basename(json_path)
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rounds = data.get('rounds', [])
    n = len(rounds)

    is_stop_instruction = '停止指令打断' in fname
    is_stop_resume = '恢复前文' in fname and '停止' in fname and '暂停后继续' in fname
    is_resume = '恢复前文' in fname

    for i, rd in enumerate(rounds):
        segs = rd.get('segments', [])
        for seg in segs:
            is_marked = as_bool(seg.get('is_interruption', '0'))

            # actual interruption = previous round has is_interruption=true
            prev_marked = False
            if i > 0:
                prev_segs = rounds[i - 1].get('segments', [])
                if prev_segs:
                    prev_marked = as_bool(prev_segs[0].get('is_interruption', '0'))
            is_actual = prev_marked
            is_last = (i == n - 1)

            # stop_intent
            stop_intent = '0'
            if is_actual:
                if is_stop_instruction:
                    stop_intent = 'true'
                elif is_stop_resume and not is_last:
                    stop_intent = 'true'

            # is_return_to_topic
            is_return = '0'
            if is_resume and is_last and not is_marked:
                is_return = 'true'

            seg['stop_intent'] = stop_intent
            seg['is_return_to_topic'] = is_return

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

    updated += 1

print(f'Done: {updated} files updated')
