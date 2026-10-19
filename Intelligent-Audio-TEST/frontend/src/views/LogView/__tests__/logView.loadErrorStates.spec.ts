/**
 * INT-974：日志页加载 / 错误 / 空三态驱动状态回归
 *
 * 缺陷（INT-911 验收实测）：fetchLogs/fetchStats 静默 catch（仅 console），
 * isLoading 存在但未渲染到模板；接口失败页面静默空白，用户无法区分
 * 「加载中 / 无数据 / 出错」。
 *
 * 锁定契约：
 * 1. 列表请求失败 → loadError 置为友好文案（原始 RPC 异常降级为固定文案，
 *    不直出原文；正常业务错误原样保留失败原因）；
 *    后续成功加载 → loadError 清空；
 * 2. 首个 fetchLogs 结束前 isInitialLoading=true（驱动 loading 指示），
 *    结束后 false（实时轮询/后台刷新不再触发 loading 闪现）；
 * 3. 列表成功但统计失败 → loadError 不受影响，仅 Toast 提示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/LogView' }),
}));

vi.mock('@/composables/task/logsPort', () => ({
  logsPort: {
    getAll: vi.fn(),
    getStats: vi.fn(),
    refresh: vi.fn(),
    mark: vi.fn(),
    clear: vi.fn(),
    export: vi.fn(),
  },
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    getOptions: vi.fn().mockResolvedValue([]),
  },
}));

// 拦截全局通知：记录 Toast 调用（与 logView.ts 相对路径 import 解析为同一模块）
const notifyMocks = vi.hoisted(() => ({
  error: vi.fn(),
}));

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ error: notifyMocks.error }),
}));

import { useLogView } from '../logView';
import { logsPort } from '@/composables/task/logsPort';
import type { Log, Paginated, LogStatsData } from '@/domain';

const emptyPage = (): Paginated<Log> => ({ items: [], total: 0, page: 1, perPage: 10, pages: 0 });
const emptyStats = (): LogStatsData => ({ total: 0, debug: 0, info: 0, warning: 0, error: 0, critical: 0 });

const mockedGetAll = vi.mocked(logsPort.getAll);
const mockedGetStats = vi.mocked(logsPort.getStats);

beforeEach(() => {
  mockedGetAll.mockReset();
  mockedGetStats.mockReset();
  notifyMocks.error.mockReset();
});

describe('INT-974：日志页三态驱动状态', () => {
  it('列表请求失败 → loadError 为友好文案；后续成功 → 清空', async () => {
    const view = useLogView();
    // 原始 gRPC 异常文本（网关透传内部异常）→ 固定友好文案，不直出原文
    mockedGetAll.mockRejectedValue(
      new Error('<_InactiveRpcError of RPC that terminated with: status=StatusCode.UNAVAILABLE>'),
    );

    await view.fetchLogs();
    expect(view.loadError.value).toBe('日志加载失败，请稍后重试');

    // 第二次成功加载：错误清空、数据就位
    mockedGetAll.mockResolvedValue(emptyPage());
    mockedGetStats.mockResolvedValue(emptyStats());
    await view.fetchLogs();
    expect(view.loadError.value).toBe('');
    expect(view.loadErrorDetail.value).toBe('');
    expect(view.isInitialLoading.value).toBe(false);
  });

  it('业务错误文案原样进入 loadError（不吞没失败原因）', async () => {
    const view = useLogView();
    mockedGetAll.mockRejectedValue(new Error('无权限查看他人日志'));

    await view.fetchLogs();
    expect(view.loadError.value).toBe('无权限查看他人日志');
  });

  it('浏览器级网络失败（Failed to fetch）→ 降级为友好文案', async () => {
    const view = useLogView();
    mockedGetAll.mockRejectedValue(new TypeError('Failed to fetch'));

    await view.fetchLogs();
    expect(view.loadError.value).toBe('日志加载失败，请稍后重试');
  });

  it('首个 fetchLogs 挂起期间 isInitialLoading=true，结束后 false', async () => {
    const view = useLogView();
    let resolveAll!: (v: Paginated<Log>) => void;
    mockedGetAll.mockImplementation(
      () => new Promise<Paginated<Log>>(resolve => { resolveAll = resolve; }),
    );
    mockedGetStats.mockResolvedValue(emptyStats());

    const pending = view.fetchLogs();
    expect(view.isLoading.value).toBe(true);
    expect(view.isInitialLoading.value).toBe(true);

    resolveAll(emptyPage());
    await pending;
    expect(view.isLoading.value).toBe(false);
    expect(view.isInitialLoading.value).toBe(false);
  });

  it('列表成功但统计失败 → loadError 不受影响，仅 Toast 提示', async () => {
    const view = useLogView();
    mockedGetAll.mockResolvedValue(emptyPage());
    mockedGetStats.mockRejectedValue(new Error('统计接口暂时不可用'));

    await view.fetchLogs();
    expect(view.loadError.value).toBe('');
    // fetchStats 为 fire-and-forget，等待其 promise 落地后断言 Toast 调用
    await vi.waitFor(() => expect(notifyMocks.error).toHaveBeenCalledTimes(1));
    expect(notifyMocks.error).toHaveBeenCalledWith('统计接口暂时不可用', '');
  });
});
