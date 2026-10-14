/**
 * INT-276：Evaluation 页 API 健康检查按钮贯通回归（testApiHealth 命名错位修复）。
 *
 * 缺陷：模板 @test-api="testApiHealth"，而 <script setup> 解构出的名称是 testAPIHealth
 * （composable 导出同名），模板引用未定义名称，点击即 TypeError，功能完全不可用。
 * V9.7.10 基线（Evaluation.vue:122/183）绑定的就是 testAPIHealth。
 *
 * 锁定契约（真实 useEvaluation 组合链 + 端口 mock，端到端贯通）：
 * 1. wire 契约：列表 / 分组两视图下点击「测试API」，testAPIHealth 均被实际调起；
 * 2. 端到端：emit → composable → evaluationPort.healthCheck → GET /evaluation/dimensions/{id}/health，
 *    成功响应打开 DETAIL_VIEW（API健康测试结果）弹窗，载荷含判定结果与端点明细；
 * 3. 失败路径：端口 reject 走错误反馈弹窗，不误报成功；
 * 4. 健康态映射：overall/端点 status 的 'online'/'healthy' 均判定为成功（对齐后端枚举原值）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const ports = vi.hoisted(() => ({
  getAll: vi.fn(),
  getCategories: vi.fn(),
  healthCheck: vi.fn(),
  update: vi.fn(),
}));
const algorithmApi = vi.hoisted(() => ({
  getOptions: vi.fn(),
}));
const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('@/composables/evaluation/evaluationPort', () => ({
  evaluationPort: ports,
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: algorithmApi,
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({
    open: modal.open,
    close: vi.fn(),
    closeAll: vi.fn(),
    getActiveModals: vi.fn(() => []),
    updateModalProps: vi.fn(),
    registerModal: vi.fn(),
  }),
  MODAL_TYPES: {
    BASIC_CONFIRM: 'basicConfirm',
    DELETE_CONFIRM: 'deleteConfirm',
    DETAIL_VIEW: 'detailView',
  },
}));

vi.mock('@/composables/modal/useNotification', () => ({
  provideNotification: vi.fn(),
  useNotification: () => ({ show: vi.fn() }),
}));

// 子组件浅替身：页面级 wire 契约测试不渲染其内部（端口已 mock，无需网络隔离）
vi.mock('../../components/common/BadgeFilter.vue', () => ({
  default: { template: '<div class="badge-filter-stub" />', props: ['options', 'modelValue', 'allLabel', 'title'] },
}));
vi.mock('../../components/algorithm/AlgorithmFilter.vue', () => ({
  default: { template: '<div class="algorithm-filter-stub" />', props: ['options', 'modelValue', 'title'] },
}));
// EvaluationDimensionTable 保持真实组件（emit 契约是被测对象本身）
import EvaluationDimensionTable from '@/components/EvaluationDimensionTable.vue';

import Evaluation from '../Evaluation.vue';

/** 单维度空列表页（分页形状） */
const EMPTY_PAGE = { items: [], total: 0, page: 1, per_page: 10, pages: 0 };
const EMPTY_CATEGORIES = { items: [], total: 0, page: 1, per_page: 1000, pages: 1 };
const EMPTY_ALGOS = { algorithms: [] };

/** 维度列表响应：主维度 + 子维度（分组视图同源） */
const DIMENSIONS_PAGE = {
  items: [
    { id: 11, name: '准确率', weight: 5, dimensionType: 'main', resultType: 'api', status: true },
    { id: 12, name: '拒识率', weight: 3, dimensionType: 'main', resultType: 'api', status: true },
  ],
  total: 2, page: 1, per_page: 10, pages: 1,
};

/** 后端健康探测响应（camelCase Domain，经 toDimensionHealthCheck 之前的端口层形状） */
const HEALTH_OK = {
  results: [{ url: 'http://asr.local/ping', status: 'online', statusCode: 200, responseTime: '12.00ms' }],
  overallStatus: 'online',
};

const lastModalCall = () => modal.open.mock.calls[modal.open.mock.calls.length - 1];

/** 挂载页面并等待首屏拉取完成 */
async function mountEvaluation() {
  const wrapper = mount(Evaluation);
  await flushPromises();
  return wrapper;
}

/** 定位第一个 EvaluationDimensionTable 中指定行文本行的「测试API」按钮并点击 */
function clickTestApi(wrapper: any, rowName: string) {
  const tables = wrapper.findAllComponents(EvaluationDimensionTable);
  expect(tables.length).toBeGreaterThan(0);
  const table = tables[0];
  const row = table.findAll('tbody tr').find((r: any) => r.text().includes(rowName));
  expect(row, `维度行 ${rowName} 应存在`).toBeTruthy();
  const btn = row!.findAll('button').find((b: any) => b.text().includes('测试API'));
  expect(btn, '「测试API」按钮应存在').toBeTruthy();
  btn!.trigger('click');
}

beforeEach(() => {
  vi.clearAllMocks();
  ports.getAll.mockResolvedValue(DIMENSIONS_PAGE);
  ports.getCategories.mockResolvedValue(EMPTY_CATEGORIES);
  algorithmApi.getOptions.mockResolvedValue(EMPTY_ALGOS);
});

describe('wire 契约：@test-api 绑定到 testAPIHealth（INT-276 回归）', () => {
  it('列表视图：点击「测试API」实际调起 testAPIHealth（端口收到 healthCheck）', async () => {
    const wrapper = await mountEvaluation();
    // 切列表视图
    await wrapper.find('button.btn-toggle[title="列表视图"]').trigger('click');
    await flushPromises();

    ports.healthCheck.mockResolvedValue(HEALTH_OK);
    clickTestApi(wrapper, '准确率');
    await flushPromises();

    expect(ports.healthCheck).toHaveBeenCalledTimes(1);
    expect(ports.healthCheck).toHaveBeenCalledWith(11);
  });

  it('分组视图（默认视图）：同样贯通（此前命名错位在该视图同样断链）', async () => {
    const wrapper = await mountEvaluation();

    ports.healthCheck.mockResolvedValue(HEALTH_OK);
    clickTestApi(wrapper, '拒识率');
    await flushPromises();

    expect(ports.healthCheck).toHaveBeenCalledTimes(1);
    expect(ports.healthCheck).toHaveBeenCalledWith(12);
  });
});

describe('端到端：healthCheck → GET /evaluation/dimensions/{id}/health → 结果弹窗', () => {
  it('成功：发起健康探测并打开 DETAIL_VIEW「API健康测试结果」弹窗，载荷含成功态与端点明细', async () => {
    const wrapper = await mountEvaluation();

    ports.healthCheck.mockResolvedValue(HEALTH_OK);
    clickTestApi(wrapper, '准确率');
    await flushPromises();

    const [type, options] = lastModalCall();
    expect(type).toBe('detailView');
    expect(options.title).toBe('API健康测试结果');
    expect(options.data.results.success).toBe(true);
    expect(options.data.results.endpoints).toHaveLength(1);
    expect(options.data.results.endpoints[0]).toMatchObject({
      url: 'http://asr.local/ping',
      success: true,
      latency: 12,
    });
    expect(options.data.dimension).toMatchObject({ id: 11, name: '准确率' });
  });

  it('失败：端口 reject 走错误反馈弹窗，不打开结果弹窗', async () => {
    const wrapper = await mountEvaluation();

    ports.healthCheck.mockRejectedValue(new Error('net down'));
    clickTestApi(wrapper, '准确率');
    await flushPromises();

    const [type, options] = lastModalCall();
    expect(type).toBe('basicConfirm');
    expect(options.title).toBe('错误');
    expect(String(options.content)).toContain('API测试失败');
    expect(String(options.content)).toContain('net down');
  });

  it('健康态映射：overall/端点 status 为 healthy 也判定成功（后端健康检查原值兼容）', async () => {
    const wrapper = await mountEvaluation();

    ports.healthCheck.mockResolvedValue({
      results: [{ url: 'http://asr.local/ping', status: 'healthy', responseTime: '8.5ms' }],
      overallStatus: 'healthy',
    });
    clickTestApi(wrapper, '准确率');
    await flushPromises();

    const [, options] = lastModalCall();
    expect(options.data.results.success).toBe(true);
    expect(options.data.results.endpoints[0].success).toBe(true);
  });

  it('探测失败态：status=offline 判定失败，载荷携带错误信息', async () => {
    const wrapper = await mountEvaluation();

    ports.healthCheck.mockResolvedValue({
      results: [{ url: 'http://asr.local/ping', status: 'offline', error: 'timeout' }],
      overallStatus: 'offline',
    });
    clickTestApi(wrapper, '准确率');
    await flushPromises();

    const [, options] = lastModalCall();
    expect(options.data.results.success).toBe(false);
    expect(options.data.results.endpoints[0].success).toBe(false);
    expect(options.data.results.endpoints[0].error).toBe('timeout');
  });
});
