/**
 * INT-100 审计 P1 回归：前端实时轮询 stop 竞态（僵尸轮询）
 *
 * tick 为 async：await fetchLogs() / logsPort.refresh() 期间关闭监控
 * （开关 toggleRealTimeLog 或卸载清理 cleanupLogView）后，await 恢复
 * 不得再调度新定时器（旧实现会复活轮询，卸载后仍持续发请求）；
 * stop 后立即重启不得产生双循环（旧循环复活会与新循环并发，且一个
 * timer id 被覆盖丢失后永远无法 clearTimeout）。
 *
 * 策略：fake timers + 受控悬挂的 port promise，在 await 窗口内触发 stop，
 * resolve 后推进远超退避上限的时间，断言定时器数与请求数不再增长。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

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

import { useLogView } from '../logView';
import { logsPort } from '@/composables/task/logsPort';
import type { Log, Paginated, LogStatsData, LogRefreshResult } from '@/domain';

const emptyPage = (): Paginated<Log> => ({ items: [], total: 0, page: 1, perPage: 10, pages: 0 });
const emptyStats = (): LogStatsData => ({ total: 0, debug: 0, info: 0, warning: 0, error: 0, critical: 0 });
const emptyRefresh = (): LogRefreshResult => ({ items: [], count: 0, newCount: 0, lastId: 0 });

const mockedGetAll = vi.mocked(logsPort.getAll);
const mockedGetStats = vi.mocked(logsPort.getStats);
const mockedRefresh = vi.mocked(logsPort.refresh);

// 与 logView.ts 同公式推导轮询间隔（env 未配置时默认 5000/30000），
// 避免测试对默认值硬编码
const parsePositiveInt = (raw: unknown, fallback: number): number => {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : fallback;
};
const BASE = parsePositiveInt(import.meta.env.VITE_LOG_POLL_INTERVAL_MS, 5000);
const IDLE_MAX = Math.max(
  BASE,
  parsePositiveInt(import.meta.env.VITE_LOG_POLL_IDLE_MAX_MS, 30000),
);

beforeEach(() => {
  vi.useFakeTimers();
  mockedGetAll.mockReset();
  mockedGetStats.mockReset();
  mockedRefresh.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('INT-100 审计 P1：实时轮询 stop 竞态', () => {
  it('开关关闭：fetchLogs 悬挂期间 stop，resolve 后轮询不复活', async () => {
    const view = useLogView();
    // 任务维度分支：tick 内 await fetchLogs()（logsPort.getAll）
    view.advancedFilters.value.taskId = 'T-1';

    let resolveAll!: (v: Paginated<Log>) => void;
    mockedGetAll.mockImplementation(
      () => new Promise< Paginated<Log> >(resolve => { resolveAll = resolve; }),
    );
    mockedGetStats.mockResolvedValue(emptyStats());

    view.toggleRealTimeLog();
    expect(view.realTimeLogEnabled.value).toBe(true);
    expect(vi.getTimerCount()).toBe(1);

    await vi.advanceTimersByTimeAsync(BASE);
    // tick 已触发且 await 悬挂中：无挂起定时器
    expect(vi.getTimerCount()).toBe(0);

    // 竞态窗口内关闭监控
    view.toggleRealTimeLog();
    expect(view.realTimeLogEnabled.value).toBe(false);

    // await 恢复：不得重新调度定时器（修复前在此复活轮询）
    resolveAll(emptyPage());
    await vi.advanceTimersByTimeAsync(0);
    expect(vi.getTimerCount()).toBe(0);

    // 推进远超空闲退避上限：仍无轮询、无新请求
    await vi.advanceTimersByTimeAsync(IDLE_MAX * 2 + BASE);
    expect(vi.getTimerCount()).toBe(0);
    expect(mockedGetAll).toHaveBeenCalledTimes(1);
  });

  it('组件卸载：refresh 悬挂期间 cleanupLogView，resolve 后轮询不复活', async () => {
    const view = useLogView();
    // 非任务分支：tick 内 await logsPort.refresh(lastId)
    let resolveRefresh!: (v: LogRefreshResult) => void;
    mockedRefresh.mockImplementation(
      () => new Promise< LogRefreshResult >(resolve => { resolveRefresh = resolve; }),
    );

    view.toggleRealTimeLog();
    expect(vi.getTimerCount()).toBe(1);

    await vi.advanceTimersByTimeAsync(BASE);
    expect(vi.getTimerCount()).toBe(0);

    // 卸载清理路径（cleanupLogView → stopRealTimeLog）
    view.cleanupLogView();

    resolveRefresh(emptyRefresh());
    await vi.advanceTimersByTimeAsync(0);
    expect(vi.getTimerCount()).toBe(0);

    await vi.advanceTimersByTimeAsync(IDLE_MAX * 2 + BASE);
    expect(vi.getTimerCount()).toBe(0);
    expect(mockedRefresh).toHaveBeenCalledTimes(1);
    expect(mockedGetAll).not.toHaveBeenCalled();
  });

  it('悬挂期间 stop 后立即重启：旧循环不复活，不产生双循环', async () => {
    const view = useLogView();

    let resolveRefresh!: (v: LogRefreshResult) => void;
    mockedRefresh.mockImplementation(
      () => new Promise< LogRefreshResult >(resolve => { resolveRefresh = resolve; }),
    );
    mockedGetAll.mockResolvedValue(emptyPage());
    mockedGetStats.mockResolvedValue(emptyStats());

    view.toggleRealTimeLog(); // start #1
    await vi.advanceTimersByTimeAsync(BASE);
    expect(vi.getTimerCount()).toBe(0); // refresh 悬挂中

    view.toggleRealTimeLog(); // stop（旧 tick 仍在途）
    resolveRefresh(emptyRefresh());
    await vi.advanceTimersByTimeAsync(0);
    expect(vi.getTimerCount()).toBe(0); // 旧循环未复活

    // 悬挂 tick 尚未执行完时重启（修复前：旧 tick 恢复后 scheduleNext
    // 覆盖新循环 timer id，产生双循环且一个 timer 永远清不掉）
    mockedRefresh.mockResolvedValue(emptyRefresh());
    view.toggleRealTimeLog(); // start #2
    expect(vi.getTimerCount()).toBe(1);

    await vi.advanceTimersByTimeAsync(BASE);
    expect(vi.getTimerCount()).toBe(1); // 恰好一个循环存活

    // 推进多个轮询周期（含空闲退避）：任意时刻只有一个定时器在调度
    await vi.advanceTimersByTimeAsync(IDLE_MAX + BASE);
    expect(vi.getTimerCount()).toBe(1);
  });
});
