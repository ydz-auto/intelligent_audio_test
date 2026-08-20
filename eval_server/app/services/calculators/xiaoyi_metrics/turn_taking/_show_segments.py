import sys, json
sys.path.insert(0, r'E:\w60085971\intelligent_audio_test\eval_server\app\services\xiaoyi_metrics\turn_taking')
from non_interactive_latency import _to_chunks, _to_segments, SEG_MERGE_GAP_S

with open(r'E:\w60085971\新建文件夹\test\1\ai_wav.json', encoding='utf-8') as f:
    data = json.load(f)

chunks = _to_chunks(data)
print(f'原始 chunks 数: {len(chunks)}')
print(f'seg_merge_gap_s = {SEG_MERGE_GAP_S}s')
print()

# 展示原始 chunks 和间隙
print('── 原始 chunks ──')
for i, c in enumerate(chunks):
    ts = c.get('timestamp', [0, 0])
    gap = ts[0] - chunks[i-1]['timestamp'][1] if i > 0 else 0
    tag = '  >> 拆段(>0.7s)' if gap > 0.7 else ''
    print(f'  C{i}: [{ts[0]:.1f}-{ts[1]:.1f}] gap={gap:.1f}s{tag}  {c["text"][:50]}')

print()
segs = _to_segments(chunks, gap=0.7)
print(f'── 合并后段数: {len(segs)} ──')
for i, (s, e, t) in enumerate(segs):
    print(f'  S{i}: [{s:.1f}-{e:.1f}] ({e-s:.1f}s)  {t[:80]}')
