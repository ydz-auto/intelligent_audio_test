/**
 * INT-301：任务级执行/评估双状态徽章单测。
 *
 * 锁定口径：
 * - 执行徽章优先取后端派生 executionStatus（评估推进不落此字段）；缺失回退 status
 * - 评估徽章仅在 evaluationStatus 存在时渲染（pending/evaluating/completed/failed/skipped）
 * - 双徽章文案独立映射（评估侧「待评估/评估中/已完成/评估失败/评估跳过」）
 * - 回收站条目维持「已删除」单徽章，不渲染双徽章
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';

// 真实 useTaskCard（不 mock），锁定 TaskCard.ts 的徽章映射逻辑
import TaskCard from '../TaskCard.vue';

vi.mock('../../../composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({ loadAlgorithms: vi.fn(), getAlgorithmLabel: (v: string) => v }),
}));

const mountTask = (task: Record<string, unknown>) =>
  mount(TaskCard, {
    props: { task, isSelected: false, showCheckbox: false, showConfig: false, actions: [] },
  });

describe('TaskCard 双状态徽章（INT-301）', () => {
  it('执行徽章取派生 executionStatus：完成 + 评估完成 → 双徽章（已完成/已完成）', () => {
    const wrapper = mountTask({
      id: 1, name: 'A', status: 'completed',
      executionStatus: 'completed', evaluationStatus: 'completed',
    });
    const badges = wrapper.findAll('.task-status');
    const texts = badges.map(b => b.text());
    expect(texts).toContain('已完成');
    // 执行徽章 + 评估徽章均渲染
    expect(wrapper.find('.exec-status-badge').classes()).toContain('completed');
    const evalBadge = wrapper.find('.eval-status-badge');
    expect(evalBadge.exists()).toBe(true);
    expect(evalBadge.classes()).toContain('completed');
    expect(evalBadge.text()).toContain('已完成');
  });

  it('重评进行中：执行徽章保持 completed，评估徽章 evaluating（评估推进不动执行侧）', () => {
    const wrapper = mountTask({
      id: 2, name: 'B', status: 'reevaluating',
      executionStatus: 'completed', evaluationStatus: 'evaluating',
    });
    expect(wrapper.find('.exec-status-badge').classes()).toContain('completed');
    const evalBadge = wrapper.find('.eval-status-badge');
    expect(evalBadge.classes()).toContain('evaluating');
    expect(evalBadge.text()).toContain('评估中');
  });

  it('评估徽章缺失时不渲染（旧数据兼容，单徽章回退）', () => {
    const wrapper = mountTask({
      id: 3, name: 'C', status: 'running',
    });
    expect(wrapper.find('.exec-status-badge').exists()).toBe(true);
    expect(wrapper.find('.eval-status-badge').exists()).toBe(false);
  });

  it('executionStatus 缺失时执行徽章回退原始 status', () => {
    const wrapper = mountTask({
      id: 4, name: 'D', status: 'running', evaluationStatus: 'pending',
    });
    expect(wrapper.find('.exec-status-badge').classes()).toContain('running');
  });

  it('评估失败文案独立于执行失败（评估失败 / 执行已完成并存）', () => {
    const wrapper = mountTask({
      id: 5, name: 'E', status: 'completed',
      executionStatus: 'completed', evaluationStatus: 'failed',
    });
    expect(wrapper.find('.exec-status-badge').text()).toContain('已完成');
    expect(wrapper.find('.eval-status-badge').text()).toContain('评估失败');
  });

  it('skipped（停止中断评估）文案与配色独立', () => {
    const wrapper = mountTask({
      id: 6, name: 'F', status: 'stopped',
      executionStatus: 'stopped', evaluationStatus: 'skipped',
    });
    expect(wrapper.find('.exec-status-badge').text()).toContain('已停止');
    const evalBadge = wrapper.find('.eval-status-badge');
    expect(evalBadge.classes()).toContain('skipped');
    expect(evalBadge.text()).toContain('评估跳过');
  });

  it('回收站条目维持「已删除」单徽章，不渲染双徽章', () => {
    const wrapper = mountTask({
      id: 7, name: 'G', status: 'completed', deleted: true,
      executionStatus: 'completed', evaluationStatus: 'completed',
    });
    expect(wrapper.find('.deleted-badge').exists()).toBe(true);
    expect(wrapper.find('.exec-status-badge').exists()).toBe(false);
    expect(wrapper.find('.eval-status-badge').exists()).toBe(false);
  });

  it('待评估徽章（evaluationStatus=pending）文案为「待评估」', () => {
    const wrapper = mountTask({
      id: 8, name: 'H', status: 'running',
      executionStatus: 'running', evaluationStatus: 'pending',
    });
    expect(wrapper.find('.eval-status-badge').text()).toContain('待评估');
  });

  it('F2：执行徽章渲染 exec-status-badge 类并带状态取值类（tokens 配色锚点）', () => {
    // UX 审计 F2：执行徽章 9 值全 tokens 配色——组件锁定「徽章携带取值类」，
    // 配色由 .exec-status-badge.<status> scoped CSS 承载（filled，同评估徽章视觉语言）
    const wrapper = mountTask({
      id: 9, name: 'I', status: 'running',
      executionStatus: 'running', evaluationStatus: 'completed',
    });
    const exec = wrapper.find('.exec-status-badge');
    expect(exec.classes()).toContain('exec-status-badge');
    expect(exec.classes()).toContain('running');
    expect(wrapper.find('.eval-status-badge').classes()).toContain('completed');
  });

  it('F3：双徽章图标映射来自共享模块（TaskCard 与详情头同源）', async () => {
    // 图标映射单一定义源 utils/taskStatusBadge.ts——TaskCard.ts 与
    // TestExecutionComponent.vue 均从该模块引用（F3 打回修复锁定）
    const badge = await import('../../../utils/taskStatusBadge');
    expect(badge.getExecutionBadgeIcon('running')).toContain('fa-spin');
    expect(badge.getEvaluationBadgeIcon('evaluating')).toContain('fa-sync-alt');
    expect(badge.getExecutionBadgeStatus({ status: 'completed' })).toBe('completed');
    expect(badge.getExecutionBadgeStatus({ status: 'reevaluating', executionStatus: 'completed' })).toBe('completed');
  });
});
