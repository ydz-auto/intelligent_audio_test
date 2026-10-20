/**
 * INT-288：LogView 加载 / 错误 / 空态回归。
 *
 * 缺陷：isLoading 存在（logView.ts:98）但模板零消费；无日志时表格空白无
 * 「暂无日志」；fetchLogs 失败仅 console.error。验收（issue 原文）：加载态
 * （spinner）、错误态（错误条 + 重试）、错误与空态视觉区分、失败保留旧数据。
 * 锁定契约：
 * 1. fetchLogs 失败 → error 暴露文案，旧数据保留不清空；
 * 2. 视图：拉取失败 → .load-error-state + 重试，重试重新拉取，恢复表格；
 * 3. 视图：0 条无错误 → .lv-empty-state「暂无日志」；
 * 4. 视图：拉取期间 → .lv-loading-state spinner。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/LogView' }),
}));

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  getStats: vi.fn(),
  refresh: vi.fn(),
  mark: vi.fn(),
  clear: vi.fn(),
  export: vi.fn(),
}));

vi.mock('@/composables/task/logsPort', () => ({ logsPort: ports }));
vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: vi.fn().mockResolvedValue([]) },
}));

import { useLogView } from '../logView';
import LogView from '../LogView.vue';
import type { Log } from '@/domain';

const LOG_PAGE = {
  items: [
    { id: 1, level: 'info', module: 'api', source: 'test', content: 'hello', time: '2026-10-17T00:00:00Z', category: 'test' } as unknown as Log,
  ],
  total: 1, page: 1, perPage: 10, pages: 1,
};
const EMPTY_PAGE = { items: [], total: 0, page: 1, perPage: 10, pages: 0 };
const STATS = { total: 0, debug: 0, info: 0, warning: 0, error: 0, critical: 0 };

beforeEach(() => {
  vi.clearAllMocks();
  ports.getStats.mockResolvedValue(STATS);
  ports.getAll.mockResolvedValue(LOG_PAGE);
});

function mountLogView() {
  return mount(LogView, {
    global: {
      stubs: {
        LogFilterPanel: true,
        LogArchivePanel: true,
        PaginationComponent: true,
      },
    },
  });
}

describe('useLogView 错误态（INT-288）', () => {
  it('fetchLogs 失败：error 置文案、旧数据保留不清空', async () => {
    const view = useLogView();
    await view.fetchLogs();
    expect(view.logs.value).toHaveLength(1);

    ports.getAll.mockRejectedValueOnce(new Error('net down'));
    await view.fetchLogs();

    expect(view.error.value).toBe('加载日志失败，请稍后重试');
    expect(view.logs.value, '失败保留旧数据（不再空白表格）').toHaveLength(1);
    expect(view.isLoading.value).toBe(false);
  });
});

describe('LogView 视图三态（INT-288）', () => {
  it('错误态：拉取失败 → 错误条 + 重试，而非空态「暂无日志」', async () => {
    ports.getAll.mockRejectedValue(new Error('net down'));
    const wrapper = mountLogView();
    await flushPromises();

    const err = wrapper.find('.load-error-state');
    expect(err.exists(), '失败后应渲染错误条（不再仅 console.error）').toBe(true);
    expect(err.text()).toContain('加载日志失败');
    expect(wrapper.find('.lv-empty-state').exists(), '错误不得呈现为空态').toBe(false);

    ports.getAll.mockResolvedValueOnce(LOG_PAGE);
    await err.find('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('.load-error-state').exists(), '重试成功后错误条消失').toBe(false);
    expect(wrapper.find('table').exists(), '重试成功后恢复日志表格').toBe(true);
  });

  it('空态：0 条无错误 → 「暂无日志」', async () => {
    ports.getAll.mockResolvedValue(EMPTY_PAGE);
    const wrapper = mountLogView();
    await flushPromises();
    expect(wrapper.find('.lv-empty-state').exists(), '0 条时应渲染空态容器').toBe(true);
    expect(wrapper.text()).toContain('暂无日志');
  });

  it('加载态：拉取期间显示 spinner（isLoading 被模板消费）', async () => {
    ports.getAll.mockReturnValue(new Promise(() => {}));
    const wrapper = mountLogView();
    await wrapper.vm.$nextTick();
    expect(wrapper.find('.lv-loading-state').exists(), '拉取期间应渲染加载态容器').toBe(true);
    expect(wrapper.find('.lv-loading-spinner').exists()).toBe(true);
  });
});
