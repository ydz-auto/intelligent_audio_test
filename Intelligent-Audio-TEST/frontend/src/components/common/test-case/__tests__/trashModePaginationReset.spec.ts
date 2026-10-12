/**
 * INT-215/S3 回归：回收站模式进出必须重置容器前端分组分页。
 *
 * 缺陷：toggleTrashMode 仅刷新数据，容器 currentPage 不重置——
 * 普通态翻页加载多页分组后进入回收站，分页状态与回收站数据集脱钩
 * （对照报告侧 toggleTrashMode 的 currentPage=1 口径）。
 * 同时锁定数据集切换时选中集清空（防止活跃项选中集流入回收站态）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reactive, nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';

import { createContainerState } from '../testCaseListContainer.state';
import { createGroupExpandModule } from '../testCaseListContainer.groupExpand';

beforeEach(() => {
  setActivePinia(createPinia());
});

const setup = () => {
  const props = reactive({ viewMode: 'group', trashMode: false });
  const state = createContainerState(props);
  const emit = vi.fn();
  const mod = createGroupExpandModule(props, emit, state);
  return { props, state, mod };
};

describe('INT-215/S3：回收站模式切换重置容器分页', () => {
  it('进入回收站态：currentPage 重置为 1 且选中集清空', async () => {
    const { props, state, mod } = setup();

    // 模拟普通态翻页与勾选
    mod.currentPage.value = 4;
    state.selectedCases.value = ['c1', 'c2', 3];

    props.trashMode = true;
    await nextTick();

    expect(mod.currentPage.value).toBe(1);
    expect(state.selectedCases.value).toEqual([]);
  });

  it('退出回收站态：同样重置分页与选中集', async () => {
    const { props, state, mod } = setup();

    props.trashMode = true;
    await nextTick();
    mod.currentPage.value = 3;
    state.selectedCases.value = ['d1'];

    props.trashMode = false;
    await nextTick();

    expect(mod.currentPage.value).toBe(1);
    expect(state.selectedCases.value).toEqual([]);
  });

  it('trashMode 未变化时不触发重置（普通筛选下翻页不受影响）', async () => {
    const { props, mod } = setup();

    mod.currentPage.value = 2;
    await nextTick();

    expect(mod.currentPage.value).toBe(2);
  });
});
