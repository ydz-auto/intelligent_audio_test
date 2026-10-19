/**
 * INT-969：BadgeFilter 对逗号组合值做多值命中回归。
 *
 * 缺陷（INT-909 验收审计）：报告中心点「对比报告」统计徽章后，
 * filters.reportType 被置为 'comparison,secondary_comparison'（后端 IN 多类型过滤），
 * 但 BadgeFilter 原先 modelValue === opt.value 单值比对全部不命中 → 类型筛选行无任何徽章高亮。
 *
 * 锁定契约：
 * 1. 组合值 'comparison,secondary_comparison' 下，comparison / secondary_comparison 两个徽章都呈选中态；
 * 2. 不命中 task / benchmark；「全部」徽章也不高亮；
 * 3. 单值（如 'comparison'）行为不变。
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import BadgeFilter from '../BadgeFilter.vue';

const REPORT_TYPE_OPTIONS = [
  { value: 'comparison', label: '对比报告' },
  { value: 'secondary_comparison', label: '二次对比报告' },
  { value: 'task', label: '任务报告' },
  { value: 'benchmark', label: 'Benchmark 报告' },
];

function badgeTexts(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll('.badge-filter__badge').map(b => b.text());
}

function isBadgeActive(wrapper: ReturnType<typeof mount>, text: string): boolean {
  const badge = wrapper.findAll('.badge-filter__badge').find(b => b.text() === text);
  expect(badge, `徽章「${text}」应存在`).toBeTruthy();
  return badge!.classes().includes('badge-filter__badge--active');
}

describe('INT-969 BadgeFilter 逗号组合值多值命中', () => {
  it('组合值下 comparison / secondary_comparison 两个徽章同时高亮，其余不高亮', () => {
    const wrapper = mount(BadgeFilter, {
      props: {
        options: REPORT_TYPE_OPTIONS,
        modelValue: 'comparison,secondary_comparison',
        allLabel: '全部类型',
      },
    });

    expect(badgeTexts(wrapper)).toEqual(expect.arrayContaining(['全部类型', '对比报告', '二次对比报告', '任务报告', 'Benchmark 报告']));
    expect(isBadgeActive(wrapper, '对比报告')).toBe(true);
    expect(isBadgeActive(wrapper, '二次对比报告')).toBe(true);
    expect(isBadgeActive(wrapper, '任务报告')).toBe(false);
    expect(isBadgeActive(wrapper, 'Benchmark 报告')).toBe(false);
    expect(isBadgeActive(wrapper, '全部类型')).toBe(false);
  });

  it('单值命中行为不变（回归）', () => {
    const wrapper = mount(BadgeFilter, {
      props: {
        options: REPORT_TYPE_OPTIONS,
        modelValue: 'comparison',
        allLabel: '全部类型',
      },
    });

    expect(isBadgeActive(wrapper, '对比报告')).toBe(true);
    expect(isBadgeActive(wrapper, '二次对比报告')).toBe(false);
    expect(isBadgeActive(wrapper, '全部类型')).toBe(false);
  });

  it('all 值仍命中「全部」徽章（回归）', () => {
    const wrapper = mount(BadgeFilter, {
      props: {
        options: REPORT_TYPE_OPTIONS,
        modelValue: 'all',
        allLabel: '全部类型',
      },
    });

    expect(isBadgeActive(wrapper, '全部类型')).toBe(true);
    expect(isBadgeActive(wrapper, '对比报告')).toBe(false);
  });
});
