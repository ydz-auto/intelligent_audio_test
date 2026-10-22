/**
 * INT-972：用例列表加载失败友好错误降级。
 *
 * 原缺陷：fetchTestCases / fetchTagView 失败仅置 error + 清空数据，容器不消费 error，
 * 页面渲染「没有找到测试用例分组/标签」空态误导用户以为库里无数据。
 *
 * 锁定行为：
 * - 网络/服务端失败（Failed to fetch / 500）→ error 为固定友好文案「用例服务暂不可用，请稍后重试」；
 * - 原始 gRPC 异常 → error 同固定文案，errorDetail 保留原文（供 Toast 折叠区）；
 * - 正常业务错误 → error 原样单行化返回；
 * - 失败后数据清空（不再以空态误导）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useTestCaseStore } from '../testCaseStore';

const testcasesPortMocks = vi.hoisted(() => ({
  getGroups: vi.fn(),
  getAll: vi.fn(),
  getTagView: vi.fn(),
}));

vi.mock('../../composables/testCase/testcasesPort', () => ({
  testcasesPort: testcasesPortMocks,
}));

/** 与后端 api_gateway 透传一致的原始 gRPC 异常文本（算法 50067 拒连） */
const RAW_RPC_MESSAGE =
  '<_InactiveRpcError of RPC that terminated with:\n' +
  '\tstatus = StatusCode.UNAVAILABLE\n' +
  '\tdetails = "failed to connect to all addresses"\n' +
  '>';

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe('INT-972：fetchTestCases 失败降级', () => {
  it('网络失败（端口不可达 Failed to fetch）→ 固定友好文案，不以空态误导', async () => {
    testcasesPortMocks.getGroups.mockRejectedValue(new Error('Failed to fetch'));
    testcasesPortMocks.getAll.mockRejectedValue(new Error('Failed to fetch'));

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.error).toBe('用例服务暂不可用，请稍后重试');
    // 网络失败无原始 RPC 详情 → 折叠区不显示
    expect(store.errorDetail).toBe('');
    // 数据清空（后续错误横幅替代空态渲染）
    expect(store.testCaseGroups).toEqual({});
    expect(store.testCases).toEqual([]);
    expect(store.groupsList).toEqual([]);
  });

  it('原始 gRPC 异常 → error 固定文案 + errorDetail 保留原文供 Toast 折叠区', async () => {
    const err = new Error('用例服务暂不可用') as any;
    err.detail = RAW_RPC_MESSAGE;
    testcasesPortMocks.getGroups.mockRejectedValue(err);
    testcasesPortMocks.getAll.mockRejectedValue(err);

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.error).toBe('用例服务暂不可用，请稍后重试');
    expect(store.errorDetail).toContain('StatusCode.UNAVAILABLE');
  });

  it('正常业务错误 → error 原样单行化返回（不吞业务文案）', async () => {
    testcasesPortMocks.getGroups.mockRejectedValue(new Error('类型已存在'));
    testcasesPortMocks.getAll.mockRejectedValue(new Error('类型已存在'));

    const store = useTestCaseStore();
    await store.fetchTestCases();

    expect(store.error).toBe('类型已存在');
    expect(store.errorDetail).toBe('');
  });
});

describe('INT-1314：fetchTagView 失败降级（独立 tagViewError，容器据此自动降级到分组视图）', () => {
  it('网络失败 → tagViewError 固定友好文案，分组 error 不受污染，标签数据清空', async () => {
    testcasesPortMocks.getTagView.mockRejectedValue(new Error('Failed to fetch'));

    const store = useTestCaseStore();
    await store.fetchTagView({});

    expect(store.tagViewError).toBe('标签视图加载失败，请稍后重试');
    expect(store.error).toBeNull();
    expect(store.errorDetail).toBe('');
    expect(store.tagViewData).toEqual({});
  });

  it('原始 gRPC 异常 → tagViewError 固定文案 + errorDetail 保留原文', async () => {
    const err = new Error('API Request failed') as any;
    err.detail = RAW_RPC_MESSAGE;
    testcasesPortMocks.getTagView.mockRejectedValue(err);

    const store = useTestCaseStore();
    await store.fetchTagView({});

    expect(store.tagViewError).toBe('标签视图加载失败，请稍后重试');
    expect(store.error).toBeNull();
    expect(store.errorDetail).toContain('StatusCode.UNAVAILABLE');
  });
});
