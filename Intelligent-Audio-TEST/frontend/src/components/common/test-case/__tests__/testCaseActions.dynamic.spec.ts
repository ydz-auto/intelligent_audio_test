/**
 * INT-216：用例卡片操作项动态化回归（testCaseListContainer.selection，INT-215 P6）。
 *
 * 锁定：普通模式返回按卡片用例求值的工厂函数——收藏星标按 isFavorite 动态生成
 * fas/far + 着色 + 标题（收藏态在列表可见）；回收站模式为静态 恢复/彻底删除 两项。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { computed, reactive, ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';

import { createContainerState } from '../testCaseListContainer.state';
import { createSelectionModule } from '../testCaseListContainer.selection';

const makeDeps = () => ({
  debouncedSearchQuery: ref(''),
  groupSelectionStates: computed<Record<string, boolean>>(() => ({})),
  filteredTagCases: computed<Record<string, any[]>>(() => ({})),
});

const setup = () => {
  const props = reactive({ viewMode: 'group', trashMode: false });
  const state = createContainerState(props);
  const emit = vi.fn();
  const mod = createSelectionModule(props, emit, state, makeDeps());
  return { props, mod };
};

beforeEach(() => {
  setActivePinia(createPinia());
});

describe('getTestCaseActions：星标动态化（INT-215 P6 回归）', () => {
  it('普通模式：未收藏 → far fa-star、无着色、标题「收藏」', () => {
    const { mod } = setup();
    const actions = (mod.getTestCaseActions() as Function)({ id: 'c1', isFavorite: false });

    const fav = actions.find((a: any) => a.id === 'favorite');
    expect(fav.iconClass).toBe('far fa-star');
    expect(fav.iconStyle).toBe('');
    expect(fav.title).toBe('收藏');
  });

  it('普通模式：已收藏 → fas fa-star + 收藏态着色、标题「取消收藏」（收藏态可见）', () => {
    const { mod } = setup();
    const actions = (mod.getTestCaseActions() as Function)({ id: 'c1', isFavorite: true });

    const fav = actions.find((a: any) => a.id === 'favorite');
    expect(fav.iconClass).toBe('fas fa-star');
    expect(fav.iconStyle).toContain('var(--favorite-star)');
    expect(fav.title).toBe('取消收藏');
  });

  it('普通模式：星标与其他卡片操作并存（预览/复制/编辑/删除）', () => {
    const { mod } = setup();
    const actions = (mod.getTestCaseActions() as Function)({ id: 'c1' });
    expect(actions.map((a: any) => a.id)).toEqual(['preview', 'copy', 'favorite', 'edit', 'delete']);
  });

  it('回收站模式：静态 恢复/彻底删除 两项，无收藏项', () => {
    const { props, mod } = setup();
    props.trashMode = true;

    const actions = mod.getTestCaseActions() as any[];
    expect(actions.map((a: any) => a.id)).toEqual(['restore', 'purge']);
    expect(actions.find((a: any) => a.id === 'restore').title).toContain('恢复');
    expect(actions.find((a: any) => a.id === 'purge').title).toContain('不可恢复');
  });
});
