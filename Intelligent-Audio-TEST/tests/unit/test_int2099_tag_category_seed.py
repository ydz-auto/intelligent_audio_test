# -*- coding: utf-8 -*-
"""INT-2099 标签分类补齐种子（seed_tag_categories_int2099.py）契约测试。

卡面（阶段 1）验收口径：
1. 规则优先级：人工录制 > 打断 > 拒识 > 接管 > 恢复前文 > 环境理解；
   交叉命名按优先级归类（`人工录制-话轮接管测试用例` → 人工录制、
   `拒识与环境理解-整理` → 拒识）。
2. 幂等重跑：分类按名称 upsert 不产生重复；已分配标签不重复改。
3. 未分类保持 NULL（不命中规则的标签不写 category_id）。
4. 软删行不参与复用、不被改；只补 category_id，其它字段不动。

数据快照：`ACTIVE_TAG_NAMES_20261030` 是 2026-10-30 真实库
（docker :15000 / `intelligent_audio_test`）88 条活跃标签的名称快照，
仅作为规则口径的回归基准；真实库标签会随走查/测试残留漂移，脚本本身
**不写死标签 id / 名称清单**，按名称规则匹配。
"""
import importlib.util
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_SEED_PATH = os.path.join(
    _REPO_ROOT, 'scripts', 'migrations', '202610',
    'seed_tag_categories_int2099.py',
)


def _load_seed_module():
    spec = importlib.util.spec_from_file_location('seed_int2099_tag_categories', _SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed = _load_seed_module()


# 2026-10-30 真实库活跃标签快照（按 id 升序）。
ACTIVE_TAG_NAMES_20261030 = [
    '接管准确率',
    '拒识与环境理解-整理',
    '非目标人拒识率',
    '目标人非交互意图拒识率',
    '环境音拒识率',
    '打断能力-整理',
    '打断成功率',
    '误接管率',
    '人工录制-话轮接管测试用例',
    '话轮接管',
    '打断真人语音',
    '打断样例真人',
    '打断真人',
    '拒识测试',
    '打断用例',
    '打断与恢复',
    '恢复前文-多次插入',
    '恢复前文-多次停止',
    '恢复前文-一次插入',
    '恢复前文-一次停止',
    '多次打断',
    '一次打断-追问解释型打断',
    '一次打断-纠正否定型打断',
    '一次打断-切换话题打断',
    '一次打断-停止指令打断',
    '拒识多轮',
    '多轮接管-语义',
    '多轮接管-快回复',
    '多轮接管-上下文',
    '单轮接管-长句接管',
    '单轮接管-误接管',
    '单轮接管-正常接管',
    '拒识',
    '静默状态一次拒识-非目标人拒识-打电话拒识',
    '静默状态一次拒识-非目标人拒识-上指代拒识',
    '静默状态一次拒识-非目标人拒识-上下文拒识',
    '静默状态一次拒识-目标人非交互意图拒识-打电话',
    '静默状态一次拒识-目标人非交互意图拒识-对他人讲话有指代',
    '静默状态一次拒识-目标人非交互意图拒识-对他人讲话上下文判断',
    '静默状态一次拒识-环境音拒识',
    '多轮拒识-非目标人拒识-指代拒识',
    '多轮拒识-非目标人拒识-打电话拒识',
    '多轮拒识-非目标人拒识-上下文拒识',
    '多轮拒识-目标人非交互意图拒识-对他人讲话有指代',
    '多轮拒识-用户Backchannel拒识',
    '多次拒识-用户Backchannel拒识',
    '回复状态一次拒识-非目标人拒识-指代拒识',
    '回复状态一次拒识-非目标人拒识-上下文拒识',
    '回复状态一次拒识-目标人非交互意图拒识-打电话',
    '回复状态一次拒识-目标人非交互意图拒识-对他人讲话有指代',
    '回复状态一次拒识-用户Backchannel拒识',
    '回复状态一次拒识-环境音拒识',
    '单轮拒识-非目标人拒识-指代拒识',
    '单轮拒识-非目标人拒识-上下文',
    '单轮拒识-目标人非交互意图拒识-打电话',
    '单轮拒识-目标人非交互意图拒识-对他人讲话有指代',
    '单轮拒识-目标人非交互意图拒识-对他人讲话上下文判断',
    '单轮拒识-环境音拒识',
    '环境理解',
    '单一环境识别-有语义',
    '单一环境识别-无语义',
    '批量_初始_0_153843_5721',
    '批量_初始_1_153843_5721',
    '批量_初始_2_153843_5721',
    '批量X',
    '批量Y',
    '走查改甲',
    '走查改乙',
    'test',
    'INT1332',
    'INT1417_c02872a8',
    'INT1417_6f1a835c',
    'probe',
    '接线测试_INT1673',
    '乙标签',
    '导入根',
    '组1',
    '子目录',
    '甲标签',
    '手填审',
    'B乙标签',
    '审根B',
    'B甲标签',
    'J标签',
    '审根P',
    '组P',
    '子P',
    '接线测试',
]

# 卡面 §分类口径 的期望命中数（当前 88 条活跃标签口径）。
EXPECTED_COUNTS = {
    '人工录制': 1,
    '打断': 12,
    '拒识': 32,
    '接管': 9,
    '恢复前文': 4,
    '环境理解': 3,
}
EXPECTED_UNCATEGORIZED = 27


def _tag(tag_id, name, category_id=None, deleted=False):
    return {
        'id': tag_id, 'name': name, 'category_id': category_id, 'deleted': deleted,
    }


def _category(cat_id, name, deleted=False):
    return {'id': cat_id, 'name': name, 'deleted': deleted}


# =====================================================================
# 1. 配置块与卡面口径一致
# =====================================================================

def test_config_matches_card_spec():
    """声明式配置 = 卡面 §分类口径：6 个分类、优先级顺序、关键字、展示顺序。"""
    names = [rule['name'] for rule in _seed.CATEGORY_RULES]
    assert names == ['人工录制', '打断', '拒识', '接管', '恢复前文', '环境理解']
    # 优先级 = 列表顺序：sort_order 与之同序，UI 展示顺序与规则优先级一致
    assert [rule['sort_order'] for rule in _seed.CATEGORY_RULES] == [10, 20, 30, 40, 50, 60]
    keywords = {rule['name']: rule['match_keywords'] for rule in _seed.CATEGORY_RULES}
    assert keywords['环境理解'] == ('环境识别', '环境理解')
    assert keywords['拒识'] == ('拒识',)
    # 不臆造运营文案/颜色：留空由分类 CRUD 维护
    assert all(rule['description'] is None and rule['color'] is None
               for rule in _seed.CATEGORY_RULES)


# =====================================================================
# 2. 规则优先级（卡面验收 3：人工录制 vs 接管、拒识 vs 环境理解）
# =====================================================================

def test_rule_priority_conflicts():
    """交叉命名按优先级归类：人工录制 > 接管、拒识 > 环境理解。"""
    assert _seed.match_category('人工录制-话轮接管测试用例') == '人工录制'
    assert _seed.match_category('拒识与环境理解-整理') == '拒识'
    # 打断优先于拒识/接管
    assert _seed.match_category('打断与恢复') == '打断'
    # 接管优先于环境理解
    assert _seed.match_category('多轮接管-语义') == '接管'
    assert _seed.match_category('话轮接管') == '接管'


def test_rule_single_category_matches():
    """各分类的典型命中。"""
    assert _seed.match_category('打断成功率') == '打断'
    assert _seed.match_category('环境音拒识率') == '拒识'
    assert _seed.match_category('恢复前文-一次停止') == '恢复前文'
    assert _seed.match_category('环境理解') == '环境理解'
    assert _seed.match_category('单一环境识别-无语义') == '环境理解'


def test_rule_no_match_keeps_uncategorized():
    """不命中任何规则（含空名/None）→ None = 未分类。"""
    for name in ('接线测试', 'probe', 'test', 'INT1417_c02872a8', '走查改甲', '批量X'):
        assert _seed.match_category(name) is None
    assert _seed.match_category('') is None
    assert _seed.match_category(None) is None


# =====================================================================
# 3. 真实快照口径：61 归类 / 27 未分类（卡面验收 1）
# =====================================================================

def test_snapshot_counts_match_card():
    """2026-10-30 快照 88 条活跃标签：61 归类（1/12/32/9/4/3）+ 27 未分类。"""
    assert len(ACTIVE_TAG_NAMES_20261030) == 88
    tags = [_tag(i + 1, name) for i, name in enumerate(ACTIVE_TAG_NAMES_20261030)]
    ops = _seed.plan_tag_assignments(tags)
    summary = _seed.summarize_tag_plan(ops)

    assert summary['by_category'] == EXPECTED_COUNTS
    assert summary['assign'] == 61
    assert summary['uncategorized'] == EXPECTED_UNCATEGORIZED
    assert summary['assign'] + summary['uncategorized'] == 88
    assert summary['skip_assigned'] == 0 and summary['skip_deleted'] == 0


def test_snapshot_unclassified_are_known_residue():
    """未分类 27 条 = 卡面列出的走查/测试残留标签，无遗漏无重复。"""
    unclassified = sorted(
        name for name in ACTIVE_TAG_NAMES_20261030
        if _seed.match_category(name) is None)
    assert len(unclassified) == EXPECTED_UNCATEGORIZED
    expected = sorted([
        '接线测试', '接线测试_INT1673', 'INT1332',
        'INT1417_c02872a8', 'INT1417_6f1a835c',
        'B甲标签', 'B乙标签', '甲标签', '乙标签', 'J标签', 'probe', 'test',
        '子P', '子目录', '审根B', '审根P', '导入根', '手填审',
        '批量X', '批量Y', '批量_初始_0_153843_5721', '批量_初始_1_153843_5721',
        '批量_初始_2_153843_5721', '组1', '组P', '走查改甲', '走查改乙',
    ])
    assert unclassified == expected


# =====================================================================
# 4. 分类侧：按名称 upsert，软删行不复活、不产生重复
# =====================================================================

def test_plan_categories_on_empty_db_inserts_all():
    """活跃分类为 0（真实库现状）→ 6 个分类全部 insert。"""
    ops = _seed.plan_category_changes([])
    assert [op['op'] for op in ops] == ['insert'] * 6
    assert [op['name'] for op in ops] == [r['name'] for r in _seed.CATEGORY_RULES]


def test_plan_categories_reuses_active_by_name():
    """已有同名活跃分类 → skip 复用（不改其展示字段、不新建）。"""
    existing = [_category(101 + i, rule['name'])
                for i, rule in enumerate(_seed.CATEGORY_RULES)]
    ops = _seed.plan_category_changes(existing)
    assert [op['op'] for op in ops] == ['skip'] * 6
    assert [op['id'] for op in ops] == [101, 102, 103, 104, 105, 106]


def test_plan_categories_ignores_soft_deleted_rows():
    """同名行全是软删（真实库 105 行现状）→ 仍 insert，不复活软删行。"""
    soft_deleted = [_category(1 + i, rule['name'], deleted=True)
                    for i, rule in enumerate(_seed.CATEGORY_RULES)]
    ops = _seed.plan_category_changes(soft_deleted)
    assert [op['op'] for op in ops] == ['insert'] * 6
    # 计划里不出现任何软删行 id → 脚本不会改写软删行
    assert all(op['id'] is None for op in ops)


def test_plan_categories_duplicate_active_names_pick_first():
    """同名多条活跃分类（唯一约束已删）→ 取首个，不新造重复，重跑选同一个。"""
    existing = [
        _category(10, '打断'), _category(20, '打断'),
        _category(30, '拒识'),
    ]
    ops = _seed.plan_category_changes(existing)
    by_name = {op['name']: op for op in ops}
    assert by_name['打断'] == {'op': 'skip', 'name': '打断', 'id': 10}
    assert by_name['拒识']['op'] == 'skip'
    assert by_name['接管']['op'] == 'insert'


# =====================================================================
# 5. 标签侧：只补 NULL、已分配/软删/未命中都不动（卡面验收 2、3）
# =====================================================================

def test_plan_tags_assigns_only_null_category():
    """命中规则且 category_id IS NULL → assign；已有分类（任意值）→ skip。"""
    tags = [
        _tag(1, '打断真人'),
        _tag(2, '打断真人', category_id=99),   # 运营已分配（哪怕别的分类）→ 不动
        _tag(3, '接线测试'),
        _tag(4, '回复状态一次拒识-环境音拒识', category_id=None),
    ]
    ops = _seed.plan_tag_assignments(tags)
    by_id = {op['tag_id']: op for op in ops}
    assert by_id[1]['op'] == 'assign' and by_id[1]['category'] == '打断'
    assert by_id[2]['op'] == 'skip_assigned'
    assert by_id[2]['current_category_id'] == 99
    assert by_id[3]['op'] == 'keep_uncategorized'
    assert by_id[4]['op'] == 'assign' and by_id[4]['category'] == '拒识'


def test_plan_tags_leaves_soft_deleted_untouched():
    """软删标签即使命中规则也不动（卡面：不动软删除行）。"""
    tags = [_tag(1, '打断真人', deleted=True), _tag(2, '拒识', deleted=True)]
    ops = _seed.plan_tag_assignments(tags)
    assert [op['op'] for op in ops] == ['skip_deleted', 'skip_deleted']
    assert all(op['category'] is None for op in ops)


# =====================================================================
# 6. 幂等：应用一次后重跑计划全 skip
# =====================================================================

def test_rerun_after_apply_is_noop():
    """模拟执行后（分类已建、标签已归类）再规划 → 0 写入、0 插入。"""
    tags = [_tag(i + 1, name) for i, name in enumerate(ACTIVE_TAG_NAMES_20261030)]
    first_ops = _seed.plan_tag_assignments(tags)
    assert _seed.summarize_tag_plan(first_ops)['assign'] == 61

    # 模拟 apply：分类按名称建成 id 201..206，命中的标签写入对应分类 id
    ids = {rule['name']: 201 + i for i, rule in enumerate(_seed.CATEGORY_RULES)}
    applied = []
    for tag, op in zip(tags, first_ops):
        if op['op'] == 'assign':
            applied.append(_tag(tag['id'], tag['name'], category_id=ids[op['category']]))
        else:
            applied.append(tag)

    second_ops = _seed.plan_tag_assignments(applied)
    summary = _seed.summarize_tag_plan(second_ops)
    assert summary['assign'] == 0
    assert summary['skip_assigned'] == 61
    assert summary['uncategorized'] == EXPECTED_UNCATEGORIZED
    assert summary['skip_deleted'] == 0

    # 分类侧同样幂等：6 个活跃分类已存在 → 全 skip、0 插入
    existing = [_category(ids[rule['name']], rule['name'])
                for rule in _seed.CATEGORY_RULES]
    cat_ops = _seed.plan_category_changes(existing)
    assert [op['op'] for op in cat_ops] == ['skip'] * 6
