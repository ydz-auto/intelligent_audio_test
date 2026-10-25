// -*- coding: utf-8 -*-
/**
 * ContainerComposition 六态回归（INT-1837 · 规范 18 §7 空态 / 失效 / 加载，§5 计数，§11 文案）。
 *
 * 锁死：
 * ① 加载中：树骨架 3 层，不渲染工具行 / Alert（不闪「无来源记录」）；
 * ② 容器无来源记录：Empty（虚线框）+ §11 两行文案；
 * ③ 落点③补拉失败：Empty「组成加载失败」+「重试」（emit retry）；
 * ④ 筛选无命中：Empty「无符合筛选条件的来源结果」+「重置筛选」；
 * ⑤ 失效：叶行整行 muted + 删除线 + 徽章「已失效」，节点计数「· 失效 k」，
 *    顶部 Alert（warning）+「只看失效」与筛选联动（同一套 filterCompositionTree）；
 * ⑥ 无报告态在 ContainerReportCard 单测覆盖（本组件不承载报告区）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';

vi.mock('../../../../composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    loadAlgorithms: () => {},
    getAlgorithmLabel: (t: string) => t,
    algorithmOptions: [],
    algorithms: [],
  }),
}));

import ContainerComposition from '../ContainerComposition.vue';
import { resetDegradedHintDismissed } from '../compositionTree';
import type { CompositionEntry } from '../../../../domain/model/containerComposition';

function entry(overrides: Partial<CompositionEntry> & { resultId: number }): CompositionEntry {
  return {
    sourceTaskId: 419,
    sourceTaskName: '小艺拒识E2E测试任务',
    sourceCaseId: `case-${overrides.resultId}`,
    sourceCaseName: `用例 ${overrides.resultId}`,
    sourceDeviceId: 9,
    sourceDeviceName: 'pura90小艺',
    sourceApiId: null,
    sourceApiName: null,
    resultType: null,
    executionStatus: 'completed',
    evaluated: true,
    missing: false,
    resultCreatedAt: null,
    groupName: '拒识',
    tags: ['标签A'],
    statusFromCase: true,
    evaluationFromCase: true,
    ...overrides,
  };
}

/** 1 条正常 + 1 条失效（同来源任务，便于断言节点计数） */
const ENTRIES: CompositionEntry[] = [
  entry({ resultId: 5714 }),
  entry({ resultId: 5715, executionStatus: 'failed', missing: true }),
];

function mountComposition(props: Record<string, unknown> = {}) {
  return mount(ContainerComposition, {
    props: { entries: ENTRIES, sourceTaskCount: 1, ...props },
  });
}

beforeEach(() => {
  resetDegradedHintDismissed();
});

describe('加载中（§7 / §10.2）', () => {
  it('渲染 3 层树骨架，不渲染工具行与 Alert', () => {
    const wrapper = mountComposition({ loading: true });
    expect(wrapper.find('[data-testid="composition-skeleton"]').exists()).toBe(true);
    expect(wrapper.findAll('.cc-skeleton-row')).toHaveLength(3);
    expect(wrapper.find('.cc-toolbar').exists()).toBe(false);
    expect(wrapper.find('.cc-alert').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('该任务没有合并来源记录');
  });
});

describe('容器无来源记录（§7，200 且 groups=[]）', () => {
  it('Empty 虚线框 + 两行文案（含历史合并解释）', () => {
    const wrapper = mountComposition({ entries: [], sourceTaskCount: 0 });
    expect(wrapper.find('.cc-empty').exists()).toBe(true);
    expect(wrapper.text()).toContain('该任务没有合并来源记录');
    expect(wrapper.text()).toContain('若它是历史合并任务，来源关系可能在合并功能上线前生成');
    // 该态下工具行不出现（无可操作数据）
    expect(wrapper.find('.cc-toolbar').exists()).toBe(false);
  });
});

describe('落点③ 补拉失败（§7）', () => {
  it('Empty +「重试」，行本体计数由宿主保留（本组件照常接收 sourceTaskCount）', async () => {
    const wrapper = mountComposition({ error: true, entries: [] });
    expect(wrapper.find('.cc-empty').exists()).toBe(true);
    expect(wrapper.text()).toContain('组成加载失败');
    const retry = wrapper.findAll('button').find((b) => b.text() === '重试');
    expect(retry).toBeTruthy();
    await retry!.trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
    // 工具行 / Alert 都不渲染，避免与错误态并存
    expect(wrapper.find('.cc-toolbar').exists()).toBe(false);
  });
});

describe('筛选无命中（§7）', () => {
  it('Empty +「重置筛选」恢复全部条目', async () => {
    const wrapper = mountComposition();
    const select = wrapper.findAll('select')[0];
    await select.setValue('stopped');
    expect(wrapper.text()).toContain('无符合筛选条件的来源结果');
    const reset = wrapper.findAll('button').find((b) => b.text() === '重置筛选');
    expect(reset).toBeTruthy();
    await reset!.trigger('click');
    expect(wrapper.text()).not.toContain('无符合筛选条件的来源结果');
    // 工具行始终可见
    expect(wrapper.find('.cc-toolbar').exists()).toBe(true);
  });
});

describe('失效态（§7 / §5 / §10.4）', () => {
  it('顶部 Alert（warning）+ k 值文案 +「只看失效」操作', () => {
    const wrapper = mountComposition();
    const alert = wrapper.find('.cc-alert');
    expect(alert.exists()).toBe(true);
    expect(alert.text()).toContain('1 条源结果已失效（源任务或结果已被删除），仅保留溯源记录');
    expect(alert.find('[data-testid="composition-only-missing"]').text()).toBe('只看失效');
    // 必须带 data-layout-btn 退出全局 button catch-all，否则 12px / 1px 边框 / warning 色
    // 会被 button.css 的 0,6,1 基类压掉（INT-1837 复审 P2）
    expect(alert.find('[data-testid="composition-only-missing"]').attributes('data-layout-btn')).toBeDefined();
  });

  it('叶行整行 muted + 删除线 + 徽章「已失效」；节点计数追加「· 失效 1」', async () => {
    const wrapper = mountComposition();
    // 展开整棵树后叶行可见
    const expandAll = wrapper.findAll('.cc-btn').find((b) => b.text() === '全部展开');
    await expandAll!.trigger('click');
    const missingLeaf = wrapper.find('.ctr-leaf--missing');
    expect(missingLeaf.exists()).toBe(true);
    expect(missingLeaf.text()).toContain('已失效');
    // 计数后缀：失效 1（失败与失效同一叶时两者都显示）
    expect(wrapper.find('.branch-count-missing').text()).toContain('失效 1');
  });

  it('「只看失效」只留失叶片，再点「查看全部结果」恢复（同一套筛选语义）', async () => {
    const wrapper = mountComposition();
    const action = wrapper.find('[data-testid="composition-only-missing"]');
    await action.trigger('click');
    expect(action.text()).toBe('查看全部结果');
    expect(action.attributes('aria-pressed')).toBe('true');
    // 只留失效叶：节点计数按命中集重算
    expect(wrapper.text()).toContain('1 条');
    const expandAll = wrapper.findAll('.cc-btn').find((b) => b.text() === '全部展开');
    await expandAll!.trigger('click');
    const leaves = wrapper.findAll('.ctr-leaf--composition');
    expect(leaves).toHaveLength(1);
    expect(leaves[0].text()).toContain('源结果 #5715');
    // 再点恢复
    await action.trigger('click');
    expect(action.text()).toBe('只看失效');
    // 展开态是「全部展开」时的集合：恢复后重新展开即可见全部叶
    const expandAllAgain = wrapper.findAll('.cc-btn').find((b) => b.text() === '全部展开');
    await expandAllAgain!.trigger('click');
    const allLeaves = wrapper.findAll('.ctr-leaf--composition');
    expect(allLeaves).toHaveLength(2);
  });

  it('无失效条目时不渲染 Alert', () => {
    const wrapper = mountComposition({ entries: [entry({ resultId: 5714 })] });
    expect(wrapper.find('.cc-alert').exists()).toBe(false);
  });
});
