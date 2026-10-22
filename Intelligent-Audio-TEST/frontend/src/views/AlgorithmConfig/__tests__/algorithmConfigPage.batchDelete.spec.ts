/**
 * 算法配置列表批量删除 + 参数总数回归测试（INT-1380）
 *
 * 缺陷1：列表「参数数」列只统计设备参数（`record.params?.length`），漏 API/用例参数。
 *        锁定契约：paramCount = deviceParams + apiParams + caseParams 全量求和（对齐 React）。
 * 缺陷2：无批量删除 UI。锁定契约：勾选（type 去重）→ 浮条计数 → 确认弹窗 →
 *        POST /algorithm/bulk-delete（deleted_types 对账成功/失败数）→ 成功通知 + 清勾选 + 刷新列表。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { modalOpen, mockGetDefinitions, mockGetGroups, mockBulkDelete } = vi.hoisted(() => ({
  modalOpen: vi.fn(),
  mockGetDefinitions: vi.fn(),
  mockGetGroups: vi.fn(),
  mockBulkDelete: vi.fn(),
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    getDefinition: vi.fn(),
    createDefinition: vi.fn(),
    getDefinitions: mockGetDefinitions,
    getGroups: mockGetGroups,
    deleteDefinition: vi.fn(),
    bulkDelete: mockBulkDelete,
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
import { paramCount, useAlgorithmConfigPage } from '../AlgorithmConfigPage';

const list = [
  { id: 1, type: 'voice_llm', name: '语音大模型', deviceParams: [1, 2, 3], apiParams: [4, 5], caseParams: [] },
  { id: 2, type: 'speech_enhance', name: '语音增强', deviceParams: [], apiParams: [], caseParams: [1] },
  { id: 3, type: 'no_params', name: '无参数', deviceParams: [], apiParams: [], caseParams: [] },
] as any[];

function setup() {
  const show = vi.fn();
  provideNotification({ show });
  const view = useAlgorithmConfigPage();
  return { show, view };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetDefinitions.mockResolvedValue({ data: list, total: list.length });
  mockGetGroups.mockResolvedValue({ data: [] });
});

describe('paramCount 参数总数（INT-1380 缺陷1）', () => {
  it('设备 + API + 用例 全量求和（voice_llm：3+2+0=5）', () => {
    expect(paramCount(list[0])).toBe(5);
  });

  it('仅有用例参数也计入（speech_enhance：0+0+1=1）', () => {
    expect(paramCount(list[1])).toBe(1);
  });

  it('缺省字段按 0 计（旧列表 `params` 别名不再单独参与，避免漏 API/用例）', () => {
    expect(paramCount(list[2])).toBe(0);
    expect(paramCount({})).toBe(0);
  });
});

describe('批量删除勾选状态（INT-1380 缺陷2）', () => {
  it('toggleSelect 按 type 切换勾选，selectedCount 随动', async () => {
    const { view } = setup();
    await view.loadAlgorithms();

    view.toggleSelect(list[0]);
    expect(view.selectedCount.value).toBe(1);
    expect(view.selectedTypes.value.has('voice_llm')).toBe(true);

    view.toggleSelect(list[0]);
    expect(view.selectedCount.value).toBe(0);
  });

  it('toggleSelectAll 全选当前页（paginatedAlgorithms），再点取消全选', async () => {
    const { view } = setup();
    await view.loadAlgorithms();

    view.toggleSelectAll();
    expect(view.selectedCount.value).toBe(view.paginatedAlgorithms.value.length);
    expect(view.isAllSelected.value).toBe(true);

    view.toggleSelectAll();
    expect(view.selectedCount.value).toBe(0);
    expect(view.isAllSelected.value).toBe(false);
  });

  it('clearSelection 清空勾选', async () => {
    const { view } = setup();
    await view.loadAlgorithms();
    view.toggleSelectAll();

    view.clearSelection();
    expect(view.selectedCount.value).toBe(0);
  });
});

describe('handleBulkDelete（INT-1380 缺陷2）', () => {
  it('确认后 POST bulk-delete，deleted_types 对账成功数，成功通知 + 清勾选 + 刷新列表', async () => {
    modalOpen.mockResolvedValue(true);
    mockBulkDelete.mockResolvedValue({ deletedTypes: ['voice_llm'] });
    const { show, view } = setup();
    await view.loadAlgorithms();

    view.toggleSelect(list[0]);
    view.toggleSelect(list[1]);

    await view.handleBulkDelete();

    expect(mockBulkDelete).toHaveBeenCalledWith(['voice_llm', 'speech_enhance']);
    expect(show).toHaveBeenCalledWith('成功删除 1 个算法，失败 1 个', 'success', '');
    expect(view.selectedCount.value).toBe(0);
    expect(mockGetDefinitions).toHaveBeenCalled();
  });

  it('全部成功时不带失败数', async () => {
    modalOpen.mockResolvedValue(true);
    mockBulkDelete.mockResolvedValue({ deletedTypes: ['voice_llm', 'speech_enhance'] });
    const { show, view } = setup();
    await view.loadAlgorithms();

    view.toggleSelect(list[0]);
    view.toggleSelect(list[1]);
    await view.handleBulkDelete();

    expect(show).toHaveBeenCalledWith('成功删除 2 个算法', 'success', '');
  });

  it('取消确认弹窗不发起 bulk-delete', async () => {
    modalOpen.mockResolvedValue(false);
    const { show, view } = setup();
    await view.loadAlgorithms();
    view.toggleSelect(list[0]);

    await view.handleBulkDelete();

    expect(mockBulkDelete).not.toHaveBeenCalled();
    expect(show).not.toHaveBeenCalled();
    expect(view.selectedCount.value).toBe(1); // 勾选保留
  });

  it('失败路径：错误通知，勾选保留，不刷新列表（列表现状不误清）', async () => {
    modalOpen.mockResolvedValue(true);
    mockBulkDelete.mockRejectedValue(new Error('算法服务暂不可用'));
    const { show, view } = setup();
    await view.loadAlgorithms();
    view.toggleSelect(list[0]);

    await view.handleBulkDelete();

    expect(show).toHaveBeenCalledWith('批量删除失败: 算法服务暂不可用', 'error', '');
    expect(view.selectedCount.value).toBe(1);
    expect(mockGetDefinitions).toHaveBeenCalledTimes(1); // 仅初始 loadAlgorithms
  });
});
