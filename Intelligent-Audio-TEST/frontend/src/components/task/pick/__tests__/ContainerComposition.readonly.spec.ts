// -*- coding: utf-8 -*-
/**
 * ContainerComposition 只读 / 叶行 / 组织提示回归（INT-1833 · 规范 18 §4.4/§4.5/§4.2）。
 *
 * 锁死：
 * ① 只读：组成区无三态复选框、无移除钮，展开 / 收起照常；
 * ② 叶行：源结果 #id + 用例名（缺名「未知用例」，不裸显 UUID）+ 设备名 + result_type 徽章
 *    （缺省「结果类型待补充」）+ 执行 / 评估徽章 + 源结果时间（仅 §11-8 有值才渲染）+ 溯源；
 * ③ 组织字段在场时不得显示「候选未返分组/标签字段…」兜底提示；
 * ④ 四视图切换 + 执行状态筛选纯客户端生效。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';

// TestCaseCard 会 loadAlgorithms（走 API），桩掉避免真实网络
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

const ENTRIES: CompositionEntry[] = [
  {
    resultId: 5714, sourceTaskId: 419, sourceTaskName: '小艺拒识E2E测试任务',
    sourceCaseId: 'case-1', sourceCaseName: 'JS177 拒识用例',
    sourceDeviceId: 9, sourceDeviceName: 'pura90小艺', sourceApiId: null, sourceApiName: null,
    resultType: null, executionStatus: 'completed', evaluated: true, missing: false,
    resultCreatedAt: null, groupName: '拒识', tags: ['标签A'],
    statusFromCase: true, evaluationFromCase: true,
  },
  {
    resultId: 5715, sourceTaskId: 419, sourceTaskName: '小艺拒识E2E测试任务',
    // 缺名用例：只保留 caseId，不得把 UUID 当用例名裸显
    sourceCaseId: '0dc13869-aaaa-bbbb', sourceCaseName: null,
    sourceDeviceId: 9, sourceDeviceName: 'pura90小艺', sourceApiId: null, sourceApiName: null,
    resultType: null, executionStatus: 'failed', evaluated: false, missing: false,
    // §11-8 落地后的源结果时间
    resultCreatedAt: '2026-10-13T09:32:59Z', groupName: '拒识', tags: ['标签A'],
    statusFromCase: true, evaluationFromCase: true,
  },
  {
    resultId: 3792, sourceTaskId: 384, sourceTaskName: 'E2E测试任务',
    sourceCaseId: 'case-3', sourceCaseName: 'JS161 拒识用例',
    sourceDeviceId: null, sourceDeviceName: null, sourceApiId: 12, sourceApiName: '用户登录API',
    resultType: null, executionStatus: 'failed', evaluated: true, missing: true,
    resultCreatedAt: null, groupName: '拒识', tags: ['标签A'],
    statusFromCase: true, evaluationFromCase: true,
  },
];

function mountComposition(entries: CompositionEntry[] = ENTRIES, sourceTaskCount = 2) {
  return mount(ContainerComposition, {
    props: { entries, sourceTaskCount },
  });
}

/** 全部展开（工具行按钮） */
async function expandAll(wrapper: ReturnType<typeof mountComposition>) {
  const btn = wrapper.findAll('.cc-btn').find((b) => b.text().includes('全部展开'));
  expect(btn).toBeTruthy();
  await btn!.trigger('click');
}

describe('ContainerComposition 只读语义（§4.4）', () => {
  it('不渲染任何三态复选框与移除钮，展开 / 收起照常', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(0);
    expect(wrapper.text()).not.toContain('移除该组');
    expect(wrapper.text()).not.toContain('移除');
    // 展开后叶行可见
    expect(wrapper.text()).toContain('源结果 #5714');
    // 收起后叶行隐藏（结构仍在，v-show/条件渲染二选一都要能收起）
    const collapse = wrapper.findAll('.cc-btn').find((b) => b.text().includes('全部收起'));
    await collapse!.trigger('click');
    expect(wrapper.text()).not.toContain('源结果 #5714');
  });

  it('用例卡不渲染勾选（PickCaseCard readonly）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    expect(wrapper.findAll('.pcc-check')).toHaveLength(0);
  });
});

describe('组成叶行内容（§4.5）', () => {
  it('源结果 #id / 用例名 / 设备 API 名 / result_type 徽章 / 状态徽章', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const leaf = wrapper.findAll('.ctr-leaf--composition');
    expect(leaf).toHaveLength(3);
    const text = wrapper.text();
    expect(text).toContain('源结果 #5714');
    expect(text).toContain('JS177 拒识用例');
    expect(text).toContain('pura90小艺');
    expect(text).toContain('用户登录API');
    // result_type 未落地统一折叠
    expect(wrapper.findAll('.ctr-leaf--composition .ctr-leaf-rt').map((n) => n.text()))
      .toEqual(['结果类型待补充', '结果类型待补充', '结果类型待补充']);
    expect(text).toContain('已完成');
    expect(text).toContain('已失败');
    expect(text).toContain('已评估');
    expect(text).toContain('未评估');
  });

  it('缺名用例降级「未知用例」，不裸显 UUID', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const leaf = wrapper.findAll('.ctr-leaf--composition');
    const unknownLeaf = leaf.find((n) => n.text().includes('源结果 #5715'));
    expect(unknownLeaf!.text()).toContain('未知用例');
    expect(unknownLeaf!.text()).not.toContain('0dc13869-aaaa-bbbb');
  });

  it('源结果时间仅 §11-8 有值时渲染（未落地不占位、不显示「—」）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const leaf = wrapper.findAll('.ctr-leaf--composition');
    const withTime = leaf.find((n) => n.text().includes('源结果 #5715'));
    expect(withTime!.find('.ctr-leaf-time').exists()).toBe(true);
    expect(withTime!.find('.ctr-leaf-time').text()).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    const withoutTime = leaf.find((n) => n.text().includes('源结果 #5714'));
    expect(withoutTime!.find('.ctr-leaf-time').exists()).toBe(false);
    expect(withoutTime!.text()).not.toContain('—');
  });

  it('失效叶行标注「已失效」并弱化', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const missing = wrapper.findAll('.ctr-leaf--missing');
    expect(missing).toHaveLength(1);
    expect(missing[0].text()).toContain('已失效');
    expect(missing[0].text()).toContain('源结果 #3792');
  });

  it('「溯源」按钮上抛 trace（resultId）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const leaf = wrapper.findAll('.ctr-leaf--composition').find((n) => n.text().includes('源结果 #5714'));
    await leaf!.find('.ctr-trace').trigger('click');
    expect(wrapper.emitted('trace')).toEqual([[5714]]);
  });
});

describe('组织提示（§4.2）', () => {
  it('真实分组 / 标签在场 → 不显示「候选未返分组/标签字段」兜底提示', async () => {
    const wrapper = mountComposition();
    expect(wrapper.find('.pco-hint').exists()).toBe(false);
    await expandAll(wrapper);
    // 组织层真实分组桶可见
    expect(wrapper.text()).toContain('拒识');
  });

  it('条目确实无组织字段 → 允许保留兜底提示（单兜底桶）', () => {
    const noOrg = ENTRIES.map((e) => ({ ...e, groupName: null, tags: [] }));
    const wrapper = mountComposition(noOrg);
    expect(wrapper.find('.pco-hint').exists()).toBe(true);
    expect(wrapper.find('.pco-hint').text()).toContain('候选未返分组/标签字段');
    expect(wrapper.text()).toContain('未分组');
  });
});

describe('四视图 / 筛选（§3.2/§5）', () => {
  it('切换用例视图：顶层变用例层组织', async () => {
    const wrapper = mountComposition();
    const caseTab = wrapper.findAll('[role="tab"]').find((t) => t.text().includes('用例视图'));
    await caseTab!.trigger('click');
    expect(wrapper.findAll('[role="tab"]').find((t) => t.text().includes('用例视图'))!.attributes('aria-selected')).toBe('true');
    await expandAll(wrapper);
    expect(wrapper.text()).toContain('拒识');
  });

  it('标签视图：按 tags 组织（标签A 桶）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const tagBtn = wrapper.findAll('.pco-btn').find((b) => b.text().includes('标签视图'));
    await tagBtn!.trigger('click');
    expect(wrapper.text()).toContain('标签A');
  });

  it('视图切换无障碍：role=tablist/tab + 方向键切换（§10.5）', async () => {
    const wrapper = mountComposition();
    const tablist = wrapper.find('[role="tablist"]');
    expect(tablist.exists()).toBe(true);
    await tablist.trigger('keydown', { key: 'ArrowRight' });
    const caseTab = wrapper.findAll('[role="tab"]').find((t) => t.text().includes('用例视图'));
    expect(caseTab!.attributes('aria-selected')).toBe('true');
  });

  it('执行状态筛选纯客户端生效（不命中叶与空祖先一并移除）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    expect(wrapper.findAll('.ctr-leaf--composition')).toHaveLength(3);
    const execSelect = wrapper.findAll('select')[0];
    await execSelect.setValue('failed');
    expect(wrapper.findAll('.ctr-leaf--composition')).toHaveLength(2);
    const text = wrapper.text();
    expect(text).toContain('源结果 #5715');
    expect(text).toContain('源结果 #3792');
    expect(text).not.toContain('源结果 #5714');
  });

  it('无来源记录空态（groups=[]）', () => {
    const wrapper = mountComposition([], 0);
    expect(wrapper.text()).toContain('该任务没有合并来源记录');
    expect(wrapper.text()).toContain('若它是历史合并任务，来源关系可能在合并功能上线前生成');
  });

  it('降级期提示：执行 / 评估状态取自用例行时显示，可关闭', async () => {
    const wrapper = mountComposition();
    expect(wrapper.find('.cc-hint').exists()).toBe(true);
    expect(wrapper.find('.cc-hint').text()).toContain('结果级执行 / 评估状态待后端补字段，当前按用例状态显示');
    await wrapper.find('.cc-hint-close').trigger('click');
    expect(wrapper.find('.cc-hint').exists()).toBe(false);
  });
});

/**
 * INT-1836 · 规范 18 §5：部分失败 / 未评估呈现与筛选联动。
 *
 * - 分支节点计数「{n} 条 · 失败 {f}」/「· 失效 {k}」，按过滤后叶实时重算
 * - 用例卡一致性 info 图标 + Tooltip（用例继承状态 ≠ 叶状态）
 * - 降级期提示会话内一次性关闭（组件重挂不再出现）
 * - 文案纪律：失败条目是正常业务态，无「异常」「不可合并」
 */
describe('部分失败呈现（§5，INT-1836）', () => {
  beforeEach(() => resetDegradedHintDismissed());

  it('分支节点计数：失败 / 失效按过滤后叶统计', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    const counts = wrapper.findAll('.ctr-count').map((n) => n.text());
    // 任务 419（5714 completed + 5715 failed）→ 2 条 · 失败 1
    expect(counts.some((t) => t.includes('2 条') && t.includes('失败 1'))).toBe(true);
    // 任务 384（3792 failed + missing）→ 1 条 · 失败 1 · 失效 1
    expect(counts.some((t) => t.includes('失败 1') && t.includes('失效 1'))).toBe(true);
  });

  it('分支计数随执行状态筛选实时重算（不改层级）', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    await wrapper.findAll('select')[0].setValue('completed');
    const counts = wrapper.findAll('.ctr-count').map((n) => n.text());
    // 只剩 5714（completed）→ 1 条，无失败后缀
    expect(counts).toContain('1 条');
    expect(counts.some((t) => t.includes('· 失败'))).toBe(false);
  });

  it('用例卡一致性：用例继承状态与叶不一致 → info 图标 + Tooltip', async () => {
    const conflictEntries: CompositionEntry[] = [
      {
        ...ENTRIES[0],
        resultId: 5715, sourceCaseId: 'dup-case', sourceCaseName: 'JS178 拒识用例',
        executionStatus: 'completed', statusFromCase: false,
        caseExecutionStatus: 'failed',
      },
      {
        ...ENTRIES[1],
        resultId: 5716, sourceCaseId: 'dup-case', sourceCaseName: 'JS178 拒识用例',
        executionStatus: 'completed', statusFromCase: false,
        caseExecutionStatus: 'failed',
      },
    ];
    const wrapper = mountComposition(conflictEntries, 1);
    await expandAll(wrapper);
    const icon = wrapper.find('.ctr-case-info');
    expect(icon.exists()).toBe(true);
    expect(icon.attributes('title')).toBe('用例状态继承自来源任务；结果状态以叶行为准');
    expect(icon.attributes('aria-label')).toBe('用例状态继承自来源任务；结果状态以叶行为准');
  });

  it('用例卡一致性：降级期叶状态取自用例行 → 不显示 info 图标', async () => {
    const wrapper = mountComposition();
    await expandAll(wrapper);
    expect(wrapper.find('.ctr-case-info').exists()).toBe(false);
  });

  it('降级期提示关闭后在同会话重挂组件仍保持关闭', async () => {
    const first = mountComposition();
    expect(first.find('.cc-hint').exists()).toBe(true);
    await first.find('.cc-hint-close').trigger('click');
    expect(first.find('.cc-hint').exists()).toBe(false);
    first.unmount();

    const second = mountComposition();
    expect(second.find('.cc-hint').exists()).toBe(false);
    second.unmount();
  });

  it('文案纪律：失败条目解释文案无「异常」「不可合并」等误导表述', () => {
    const wrapper = mountComposition();
    const text = wrapper.text();
    expect(text).toContain('仅执行失败 / 部分失败的任务也可被挑选合并，失败条目按原状态呈现');
    expect(text).not.toContain('异常');
    expect(text).not.toContain('不可合并');
  });
});
