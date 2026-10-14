/**
 * 算法配置列表页失败路径可观测性回归测试（INT-291）
 *
 * 旧实现失败路径仅 console.error，界面无任何提示：
 * 列表加载失败落「暂无数据」与空态不可区分；复制/删除失败无感知。
 *
 * 锁定契约：
 * 1. loadAlgorithms / loadGroups 失败走 useNotification.error（站内已有范式）；
 * 2. loadAlgorithmDetail 失败提示（编辑弹窗以列表行浅数据打开，避免误以为主数据完整）；
 * 3. handleClone 失败提示，且不触发 loadAlgorithms（列表现状不被误清）；
 * 4. confirmDelete→executeDelete 失败提示，不触发 loadAlgorithms、不切回列表页签；
 * 5. 成功路径照常刷新列表（通知不改变原成功行为）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const { modalOpen, mockGetDefinition, mockCreateDefinition, mockGetDefinitions, mockGetGroups, mockDeleteDefinition } = vi.hoisted(() => ({
  modalOpen: vi.fn(),
  mockGetDefinition: vi.fn(),
  mockCreateDefinition: vi.fn(),
  mockGetDefinitions: vi.fn(),
  mockGetGroups: vi.fn(),
  mockDeleteDefinition: vi.fn(),
}));

const show = vi.fn();

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    getDefinition: mockGetDefinition,
    createDefinition: mockCreateDefinition,
    getDefinitions: mockGetDefinitions,
    getGroups: mockGetGroups,
    deleteDefinition: mockDeleteDefinition,
  },
}));

vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({
    open: modalOpen,
    close: vi.fn(),
    closeAll: vi.fn(),
    getActiveModals: vi.fn(() => []),
    updateModalProps: vi.fn(),
    registerModal: vi.fn(),
  }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM' },
}));

import { provideNotification } from '@/composables/modal/useNotification';
import { useAlgorithmConfigPage } from '../AlgorithmConfigPage';
import AlgorithmConfigPage from '../AlgorithmConfigPage.vue';

const record = { id: 101, type: 'voice_llm', name: '语音大模型' } as any;

function setup() {
  provideNotification({ show });
  return useAlgorithmConfigPage();
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetDefinitions.mockResolvedValue({ data: [], total: 0 });
  mockGetGroups.mockResolvedValue({ data: [] });
});

describe('useAlgorithmConfigPage 失败路径通知（INT-291）', () => {
  it('loadAlgorithms 失败：notification.error 提示，loading 复位为 false', async () => {
    mockGetDefinitions.mockRejectedValue(new Error('网络断开'));
    const view = setup();

    await view.loadAlgorithms();

    expect(show).toHaveBeenCalledTimes(1);
    expect(show).toHaveBeenCalledWith('加载算法列表失败: 网络断开', 'error', '');
    expect(view.loading.value).toBe(false);
  });

  it('loadAlgorithms 失败（非 Error 抛出）：提示未知错误兜底文案', async () => {
    mockGetDefinitions.mockRejectedValue('boom');
    const view = setup();

    await view.loadAlgorithms();

    expect(show).toHaveBeenCalledWith('加载算法列表失败: 未知错误', 'error', '');
  });

  it('loadGroups 失败：notification.error 提示（经页面挂载触发 onMounted 链路）', async () => {
    mockGetGroups.mockRejectedValue(new Error('服务不可用'));

    mount(AlgorithmConfigPage);
    await flushPromises();

    // onMounted 链路里 loadGroups 独立 try/catch，失败不影响 loadAlgorithms
    expect(show).toHaveBeenCalledWith('加载分组列表失败: 服务不可用', 'error', '');
  });

  it('loadAlgorithmDetail 失败：notification.error 提示（handleEdit 链路，弹窗仍打开）', async () => {
    mockGetDefinition.mockRejectedValue(new Error('详情接口 500'));
    const view = setup();

    view.handleEdit(record);
    await flushPromises();

    expect(show).toHaveBeenCalledWith('加载算法详情失败: 详情接口 500', 'error', '');
    expect(view.modalVisible.value).toBe(true);
  });

  it('handleClone 失败：notification.error 提示，且不刷新列表（列表现状不误清）', async () => {
    modalOpen.mockResolvedValue(true);
    mockGetDefinition.mockResolvedValue({ type: 'voice_llm', name: '语音大模型' });
    mockCreateDefinition.mockRejectedValue(new Error('类型已存在'));
    const view = setup();

    await view.handleClone(record);

    expect(show).toHaveBeenCalledWith('复制算法失败: 类型已存在', 'error', '');
    expect(mockGetDefinitions).not.toHaveBeenCalled();
  });

  it('confirmDelete→executeDelete 失败：notification.error 提示，不刷新列表、不切页签', async () => {
    modalOpen.mockResolvedValue(true);
    mockDeleteDefinition.mockRejectedValue(new Error('外键约束'));
    const view = setup();
    view.activeTab.value = 'detail';

    await view.confirmDelete(record);

    expect(show).toHaveBeenCalledWith('删除算法失败: 外键约束', 'error', '');
    expect(mockGetDefinitions).not.toHaveBeenCalled();
    expect(view.activeTab.value).toBe('detail');
  });

  it('删除成功路径：无通知，照常刷新列表并切回列表页签', async () => {
    modalOpen.mockResolvedValue(true);
    mockDeleteDefinition.mockResolvedValue(undefined);
    const view = setup();
    view.activeTab.value = 'detail';

    await view.confirmDelete(record);

    expect(show).not.toHaveBeenCalled();
    expect(mockGetDefinitions).toHaveBeenCalled();
    expect(view.activeTab.value).toBe('list');
  });
});
