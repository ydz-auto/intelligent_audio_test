# -*- coding: utf-8 -*-
"""INT-2099 隔离库标签 CRUD 回读探针（供集成测试以子进程方式调用）。

为什么单独一个进程：`TagCrudService` 经 `shared.models.database` 的全局
scoped_session 取连接，连接串由 `BaseConfig` 在**模块导入时**固化。同进程
改绑定会污染同一 pytest 会话里的其它用例（INT-90 踩过），故由集成测试以
独立进程调用，进程内只连隔离库（`DATABASE_URL` 由调用方注入）。

覆盖卡面阶段 1 验收 2「现有标签 CRUD（创建 / 编辑 / 删除）不受影响，接口
回读一致」的服务层部分：
- 贴种子落库后的分类/分组读回（6 个活跃分类 + category:null 未分类组）；
- 标签创建（挂到种子分类下）→ 改名 + 换分类 → 删除 → 分组回读复原；
- 批量更新分类（含清空 category_id）；
- 分类创建 → 改名 → 删除（空分类可删；有标签的分类拒绝删除）。

用法：
    DATABASE_URL=postgresql://... python tests/integration/int2099_tag_crud_probe.py

输出：stdout 一行 JSON 摘要；任一断言失败即非零退出（stderr 带原因）。
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


def _counts(svc):
    """by-category 回读 → {分类名: 标签数}（未分类组用 None 作键）。"""
    result = svc.get_tags_by_category()
    assert result.get('success'), result
    counts = {}
    for group in result['data']['items']:
        category = group['category']
        key = category['name'] if category else None
        counts[key] = len(group['tags'])
    return counts


def main():
    from shared.models.database import init_db, remove_db_session
    from task_service.application.testcase.tag_crud_service import TagCrudService

    init_db(pool_size=1)
    svc = TagCrudService()
    summary = {}
    try:
        # 1) 分类列表：种子落库后恰 6 个活跃分类，按 sort_order 展示
        cats = svc.list_categories(per_page=100)
        assert cats.get('success'), cats
        cat_items = cats['data']['items']
        summary['categories'] = [c['name'] for c in cat_items]
        assert summary['categories'] == [
            '人工录制', '打断', '拒识', '接管', '恢复前文', '环境理解'], summary['categories']
        assert cats['data']['total'] == 6, cats['data']['total']
        cat_ids = {c['name']: c['id'] for c in cat_items}
        assert [c['tag_count'] for c in cat_items] == [1, 12, 32, 9, 4, 3], \
            [c['tag_count'] for c in cat_items]

        # 2) 分组回读：6 个分类组 + 未分类组 27
        base_counts = _counts(svc)
        assert base_counts == {
            '人工录制': 1, '打断': 12, '拒识': 32, '接管': 9,
            '恢复前文': 4, '环境理解': 3, None: 27}, base_counts
        summary['by_category_before'] = {
            ('未分类' if key is None else key): value
            for key, value in base_counts.items()}

        # 3) 标签创建：挂到种子分类「打断」下
        created = svc.create_tag({'name': 'INT2099_probe_tag',
                                  'category_id': cat_ids['打断']})
        assert created.get('success'), created
        probe_tag_id = created['data']['id']
        assert _counts(svc)['打断'] == 13

        # 4) 标签编辑：改名 + 换分类到「接管」
        updated = svc.update_tag(probe_tag_id, {
            'name': 'INT2099_probe_tag_renamed', 'category_id': cat_ids['接管']})
        assert updated.get('success'), updated
        assert updated['data']['name'] == 'INT2099_probe_tag_renamed'
        assert updated['data']['category_id'] == cat_ids['接管']
        counts = _counts(svc)
        assert counts['接管'] == 10 and counts['打断'] == 12, counts

        # 5) 标签删除（无引用）→ 分组复原
        deleted = svc.delete_tag(probe_tag_id)
        assert deleted.get('success'), deleted
        assert svc.get_tag(probe_tag_id).get('code') == 404
        assert _counts(svc) == base_counts

        # 6) 批量更新分类：把 2 条未分类标签挂到「环境理解」，再清空回去
        # （list_tags 的 category_id=None 语义是「不过滤」，未分类组只能从
        #   分组回读取 —— by-category 的最后一组即 category: null）
        groups = svc.get_tags_by_category()['data']['items']
        uncategorized_ids = [t['id'] for t in groups[-1]['tags'][:2]]
        assert len(uncategorized_ids) == 2
        moved = svc.batch_update_category(
            {'tag_ids': uncategorized_ids, 'category_id': cat_ids['环境理解']})
        assert moved.get('success'), moved
        counts = _counts(svc)
        assert counts['环境理解'] == 5 and counts[None] == 25, counts
        cleared = svc.batch_update_category({'tag_ids': uncategorized_ids,
                                             'category_id': None})
        assert cleared.get('success'), cleared
        assert _counts(svc) == base_counts

        # 7) 分类 CRUD：创建 → 改名 → 删除（空分类可删）
        new_cat = svc.create_category({'name': 'INT2099_probe_cat'})
        assert new_cat.get('success'), new_cat
        new_cat_id = new_cat['data']['id']
        renamed = svc.update_category(new_cat_id, {'name': 'INT2099_probe_cat_renamed'})
        assert renamed.get('success'), renamed
        assert renamed['data']['name'] == 'INT2099_probe_cat_renamed'
        removed = svc.delete_category(new_cat_id)
        assert removed.get('success'), removed
        assert svc.list_categories(per_page=100)['data']['total'] == 6

        # 8) 种子分类非空 → 删除被拒（既有保护语义不被种子数据破坏）
        refused = svc.delete_category(cat_ids['打断'])
        assert refused.get('code') == 400 and '还有 12 个标签' in refused['message'], refused

        summary['ok'] = True
    finally:
        remove_db_session()
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f'[PROBE-FAIL] {exc}', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - 异常也必须可诊断
        import traceback
        traceback.print_exc()
        print(f'[PROBE-FAIL] {exc}', file=sys.stderr)
        sys.exit(1)
