# -*- coding: utf-8 -*-
"""种子/补齐：标签分类数据（INT-2099 阶段 1）

背景（INT-2099，方案一致性审计员在 INT-2096 裁定契约）：
- 分类来源 = 用户自建数据表 `tag_categories`（全 CRUD），不是固定枚举；
- 标签 `tags.category_id` FK → `tag_categories.id`，可空，NULL = 未分类；
- 真实库现状（2026-10-30 实测）：`tag_categories` 105 行**全部软删**（活跃 0），
  活跃 `tags` 88 条 `category_id` 全 NULL —— 接口 `GET /tags/categories` 空、
  `GET /tags/by-category` 只有 `category: null` 一组。
- 本脚本补活跃分类 + 按名称规则给活跃标签补 `category_id`。

口径（提案，负责人确认后阶段 2 才应用到真实栈主库）：
  人工录制 > 打断 > 拒识 > 接管 > 恢复前文 > 环境理解，其余保持未分类。
  优先级 = 下面 `CATEGORY_RULES` 的**列表顺序**；每个分类的关键字命中即归类。
  负责人调整口径时只改这份配置，不改逻辑。

幂等与安全边界（卡面契约）：
- 分类按**名称** upsert：已有同名**活跃**分类即复用（不改它的展示字段，保留运营
  手工改过的描述/颜色）；没有才插入。软删行一律不动（不复用、不复活、不改写），
  所以重跑不会产生重复活跃分类。
  注：同名活跃分类若是私有（visibility=private），复用后挂到它下面的标签只对拥有者
  可见 —— 阶段 2 执行前先确认真实库活跃分类为空（2026-10-30 实测为 0）。
- 标签只补 `category_id`，且**只写当前为 NULL 的活跃标签**：已经分配过（哪怕
  指向别的分类）的标签不重复改；软删标签不动；其它字段（name/description/color/
  visibility/updated_at 等）一律不改。
- 不删除任何行；不写审计/操作人字段（系统回填，created_by_user_id 留 NULL，
  visibility 取默认 shared）。

用法：
    python scripts/migrations/202610/seed_tag_categories_int2099.py           # 预览（默认 dry-run）
    python scripts/migrations/202610/seed_tag_categories_int2099.py --apply   # 执行

连接串：`DATABASE_URL`（缺省回落 `DATABASE_URI`）。
幂等性：重复执行应全 SKIP / 0 变更（分类已齐、标签已分配或本就未分类）。

本脚本**不进 docker 引导链**：它是真实库用户数据的定向补齐，须由负责人在
INT-2096 确认分类口径后（本卡阶段 2）单独执行，见 scripts/migrations/README.md
「独立窗口」小节。
"""
import argparse
import os

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

TAG_CATEGORIES_TABLE = 'tag_categories'
TAGS_TABLE = 'tags'

# =====================================================================
# §口径 声明式配置块（负责人调整分类口径只改这里）
#
# - 列表顺序 = 规则优先级（越靠前越优先）；同名多规则命中取靠前者。
# - sort_order = 分类在 UI 列表中的展示顺序（与优先级同序）。
# - match_keywords：标签名称包含任一关键字即命中该分类（子串匹配）。
# - description / color 留空（NULL）：不臆造运营文案，需要时在分类 CRUD 里补。
# =====================================================================
CATEGORY_RULES = [
    {
        'name': '人工录制',
        'description': None,
        'color': None,
        'sort_order': 10,
        'match_keywords': ('人工录制',),
    },
    {
        'name': '打断',
        'description': None,
        'color': None,
        'sort_order': 20,
        'match_keywords': ('打断',),
    },
    {
        'name': '拒识',
        'description': None,
        'color': None,
        'sort_order': 30,
        'match_keywords': ('拒识',),
    },
    {
        'name': '接管',
        'description': None,
        'color': None,
        'sort_order': 40,
        'match_keywords': ('接管',),
    },
    {
        'name': '恢复前文',
        'description': None,
        'color': None,
        'sort_order': 50,
        'match_keywords': ('恢复前文',),
    },
    {
        'name': '环境理解',
        'description': None,
        'color': None,
        'sort_order': 60,
        'match_keywords': ('环境识别', '环境理解'),
    },
]

# 未分类（category_id 保持 NULL）的显式兜底说明：不匹配任何规则即未分类，
# 不需要额外配置项。


def match_category(tag_name):
    """按配置的优先级返回标签应归的分类名；不命中任何规则返回 None（未分类）。

    纯函数，供脚本与单测共用。子串匹配 + 首命中即返回（优先级 = 列表顺序），
    因此 `人工录制-话轮接管测试用例` 归「人工录制」、`拒识与环境理解-整理` 归「拒识」。
    """
    name = (tag_name or '').strip()
    if not name:
        return None
    for rule in CATEGORY_RULES:
        if any(keyword and keyword in name for keyword in rule['match_keywords']):
            return rule['name']
    return None


def plan_category_changes(existing_categories):
    """纯函数：按现存分类行给出分类侧待执行操作。

    Args:
        existing_categories: `tag_categories` 的行（dict，至少含 id/name/deleted；
            含软删行，软删行仅用于报告，不参与复用）。

    Returns:
        list[dict]：`{'op': 'insert'|'skip', 'name': str, 'id': int|None}`
        - skip：已有同名**活跃**分类 → 复用，不改它的任何字段
        - insert：没有同名活跃分类 → 插入（软删同名行不复活）
    """
    active_by_name = {}
    for row in existing_categories or []:
        if row.get('deleted'):
            continue
        name = row.get('name')
        if not name or name in active_by_name:
            continue
        # 同名多条活跃分类（唯一约束已在 202608 基线删除）：按加载顺序（id 升序）
        # 取首个，保证多次执行选定同一个分类、不新造重复行。
        active_by_name[name] = row

    ops = []
    for rule in CATEGORY_RULES:
        existing = active_by_name.get(rule['name'])
        if existing is not None:
            ops.append({'op': 'skip', 'name': rule['name'], 'id': existing.get('id')})
        else:
            ops.append({'op': 'insert', 'name': rule['name'], 'id': None})
    return ops


def plan_tag_assignments(tags):
    """纯函数：按名称规则给出标签侧待执行操作。

    Args:
        tags: `tags` 的行（dict，至少含 id/name/category_id/deleted）。

    Returns:
        list[dict]：每个标签一条
        - `assign`：命中规则且 `category_id IS NULL` → 补分类
        - `skip_assigned`：命中规则但已有 `category_id`（任意值）→ 不动
        - `keep_uncategorized`：不命中任何规则 → 保持未分类（有值也不动）
        - `skip_deleted`：软删标签 → 不动
    """
    ops = []
    for tag in tags or []:
        if tag.get('deleted'):
            ops.append({
                'op': 'skip_deleted', 'tag_id': tag.get('id'),
                'tag_name': tag.get('name'), 'category': None,
            })
            continue
        category_name = match_category(tag.get('name'))
        if category_name is None:
            ops.append({
                'op': 'keep_uncategorized', 'tag_id': tag.get('id'),
                'tag_name': tag.get('name'), 'category': None,
            })
        elif tag.get('category_id') is not None:
            ops.append({
                'op': 'skip_assigned', 'tag_id': tag.get('id'),
                'tag_name': tag.get('name'), 'category': category_name,
                'current_category_id': tag.get('category_id'),
            })
        else:
            ops.append({
                'op': 'assign', 'tag_id': tag.get('id'),
                'tag_name': tag.get('name'), 'category': category_name,
            })
    return ops


def summarize_tag_plan(ops):
    """标签计划汇总：{分类名: 待分配数}、跳过数、未分类数。"""
    by_category = {}
    assigned = skipped = uncategorized = deleted = 0
    for op in ops:
        if op['op'] == 'assign':
            by_category[op['category']] = by_category.get(op['category'], 0) + 1
            assigned += 1
        elif op['op'] == 'skip_assigned':
            skipped += 1
        elif op['op'] == 'keep_uncategorized':
            uncategorized += 1
        else:
            deleted += 1
    return {
        'by_category': by_category,
        'assign': assigned,
        'skip_assigned': skipped,
        'uncategorized': uncategorized,
        'skip_deleted': deleted,
    }


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _table_exists(cur, table) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (table,))
    return cur.fetchone() is not None


def _load_categories(cur):
    cur.execute(
        'SELECT id, name, deleted FROM tag_categories ORDER BY id')
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _load_tags(cur):
    cur.execute(
        'SELECT id, name, category_id, deleted FROM tags ORDER BY id')
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _print_summary(categories, tags, cat_ops, tag_ops):
    active_cats = [c for c in categories if not c['deleted']]
    deleted_cats = [c for c in categories if c['deleted']]
    active_tags = [t for t in tags if not t['deleted']]
    deleted_tags = [t for t in tags if t['deleted']]
    summary = summarize_tag_plan(tag_ops)

    print(f'\n== 现状（tag_categories / tags）==')
    print(f'  分类：活跃 {len(active_cats)} 条、软删 {len(deleted_cats)} 条（软删行不动）')
    print(f'  标签：活跃 {len(active_tags)} 条、软删 {len(deleted_tags)} 条（软删行不动）')

    print('\n== 分类计划 ==')
    inserts = [op for op in cat_ops if op['op'] == 'insert']
    skips = [op for op in cat_ops if op['op'] == 'skip']
    for op in cat_ops:
        if op['op'] == 'insert':
            print(f"  [INSERT] {op['name']}（新建活跃分类）")
        else:
            print(f"  [SKIP]   {op['name']}（活跃分类已存在，id={op.get('id')}，不动其字段）")
    print(f'  合计：新建 {len(inserts)} 个、复用 {len(skips)} 个')

    print('\n== 标签归类计划 ==')
    for name in [r['name'] for r in CATEGORY_RULES]:
        count = summary['by_category'].get(name, 0)
        print(f"  {name:<6} 待补 {count} 条")
    print(f"  保持未分类（不命中任何规则）{summary['uncategorized']} 条")
    print(f"  已分配跳过 {summary['skip_assigned']} 条、软删跳过 {summary['skip_deleted']} 条")
    print(f"  本次将写入 tags.category_id 共 {summary['assign']} 行")


def _apply_plan(cur, cat_ops, tag_ops):
    """执行计划：先补分类拿 id，再逐条补 category_id 为 NULL 的活跃标签。

    Returns:
        (新建分类数, 更新标签数)
    """
    rules = {rule['name']: rule for rule in CATEGORY_RULES}
    category_ids = {}
    inserted = 0

    for op in cat_ops:
        if op['op'] == 'skip':
            category_ids[op['name']] = op['id']
            continue
        rule = rules[op['name']]
        cur.execute(
            'INSERT INTO tag_categories '
            '  (name, description, color, sort_order, visibility, '
            '   deleted, created_at, updated_at) '
            'VALUES (%s, %s, %s, %s, %s, false, NOW(), NOW()) '
            'RETURNING id',
            (rule['name'], rule['description'], rule['color'],
             rule['sort_order'], 'shared'))
        category_ids[rule['name']] = cur.fetchone()[0]
        print(f"  [APPLY] INSERT 分类 {rule['name']}（id={category_ids[rule['name']]}）")
        inserted += 1

    updated = 0
    for op in tag_ops:
        if op['op'] != 'assign':
            continue
        # 只写仍为 NULL 的活跃行：并发/前置执行已分配者 0 行，天然幂等，
        # 且绝不可能覆盖别人刚写的分类。
        cur.execute(
            'UPDATE tags SET category_id = %s '
            'WHERE id = %s AND deleted = false AND category_id IS NULL',
            (category_ids[op['category']], op['tag_id']))
        if cur.rowcount != 1:
            raise RuntimeError(
                f"标签 {op['tag_id']}（{op['tag_name']}）更新行数 {cur.rowcount}，"
                '预期 1；可能被并发修改，已回滚')
        updated += 1
        print(f"  [APPLY] 标签 {op['tag_id']} 「{op['tag_name']}」→ {op['category']}")

    return inserted, updated


def migrate(dry_run=True):
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        for table in (TAG_CATEGORIES_TABLE, TAGS_TABLE):
            if not _table_exists(cur, table):
                print(f'[SKIP] 表 {table} 不存在（空库请先 create_all_tables.py）')
                return

        categories = _load_categories(cur)
        tags = _load_tags(cur)
        cat_ops = plan_category_changes(categories)
        tag_ops = plan_tag_assignments(tags)
        _print_summary(categories, tags, cat_ops, tag_ops)

        if dry_run:
            print('\n[DRY] 未写入；加 --apply 执行')
            conn.rollback()
            return

        print('\n[APPLY] 执行计划：')
        inserted, updated = _apply_plan(cur, cat_ops, tag_ops)
        conn.commit()

        after_categories = _load_categories(cur)
        after_tags = _load_tags(cur)
        active_after = [c for c in after_categories if not c['deleted']]
        assigned_after = [
            t for t in after_tags if not t['deleted'] and t['category_id'] is not None]
        unclassified_after = [
            t for t in after_tags if not t['deleted'] and t['category_id'] is None]
        print(
            f'\n[APPLY] 新建分类 {inserted} 个、更新标签 {updated} 行；'
            f'执行后活跃分类 {len(active_after)} 个、'
            f'已归类标签 {len(assigned_after)} 条 / 未分类 {len(unclassified_after)} 条'
            f'（幂等：重复执行应全 SKIP / 0 变更）')
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='标签分类数据补齐种子（INT-2099 阶段 1）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
