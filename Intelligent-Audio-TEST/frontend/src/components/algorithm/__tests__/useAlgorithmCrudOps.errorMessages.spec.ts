/**
 * AlgorithmConfigModal 保存/编辑/启停/删除失败路径错误消息安全化回归锁定（INT-1019）
 *
 * INT-899（04fa3fb84）只覆盖了 AlgorithmConfigPage.ts 页面级路径，
 * 遗漏了模态窗 saveAlgorithm 的 catch 分支——算法 gRPC 未起时 Toast 直出
 * 原始 `<_InactiveRpcError...>` 异常文本（含 ipv4 地址/端口/Python 栈）。
 *
 * 锁定契约：
 * 1. saveAlgorithm 失败（原始 RPC 文本）→ 降级固定文案「算法服务暂不可用，请稍后重试」，不直出原文；
 * 2. saveAlgorithm 失败（正常业务错误）→ 保留业务文案（单行化）；
 * 3. saveAlgorithm 失败（非 Error 抛出）→ 未知错误兜底（INT-291 契约）；
 * 4. 同源路径 handleEdit / handleToggleStatus / executeDelete 失败同样降级固定文案（不再静默）；
 * 5. saveAlgorithm 成功路径照常 emit success / update:visible false / 刷新列表。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref, reactive } from 'vue';

const {
  modalOpen,
  mockGetDefinition,
  mockCreateDefinition,
  mockUpdateDefinition,
  mockGetDefinitions,
  mockGetGroups,
  mockDeleteDefinition,
  mockCreateGroup,
} = vi.hoisted(() => ({
  modalOpen: vi.fn(),
  mockGetDefinition: vi.fn(),
  mockCreateDefinition: vi.fn(),
  mockUpdateDefinition: vi.fn(),
  mockGetDefinitions: vi.fn(),
  mockGetGroups: vi.fn(),
  mockDeleteDefinition: vi.fn(),
  mockCreateGroup: vi.fn(),
}));

const { notifyError, notifyWarning, notifySuccess } = vi.hoisted(() => ({
  notifyError: vi.fn(),
  notifyWarning: vi.fn(),
  notifySuccess: vi.fn(),
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    getDefinitions: mockGetDefinitions,
    getGroups: mockGetGroups,
    createDefinition: mockCreateDefinition,
    updateDefinition: mockUpdateDefinition,
    deleteDefinition: mockDeleteDefinition,
    getDefinition: mockGetDefinition,
    createGroup: mockCreateGroup,
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

vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({ error: notifyError, warning: notifyWarning, success: notifySuccess }),
}));

import { useAlgorithmCrudOps } from '../useAlgorithmCrudOps';

/** 与 verify_int920_error_state.py / stub_grpc_down.py 透传文本同构的原始 RPC 异常 */
const RAW_RPC =
  '<_InactiveRpcError of RPC that terminated with:\n' +
  '\tstatus = StatusCode.UNAVAILABLE\n' +
  '\tdetails = "failed to connect to all addresses; last error: UNAVAILABLE: ipv4:127.0.0.1:51067"\n' +
  '>';

function setup(mode = 'create') {
  const props = { mode };
  const emit = vi.fn();
  const formState = reactive({
    type: 'voice_llm',
    name: '语音大模型',
    groupId: null,
    description: '',
    status: '',
    statusSwitch: true,
    icon: '',
    displayOrder: 0,
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
    referenceParams: [],
  });
  const effectiveMode = ref(mode);
  const internalMode = ref(mode);
  const algorithms = ref([]);
  const groups = ref([]);
  const availableDimensions = ref([]);
  const creatingNewGroup = ref(false);
  const newGroupName = ref('');
  const activeTab = ref('basic');
  const paramConfigType = ref('device');

  const ops = useAlgorithmCrudOps(
    props,
    emit,
    formState,
    effectiveMode,
    internalMode,
    algorithms,
    groups,
    availableDimensions,
    vi.fn(async () => []),
    vi.fn(),
    vi.fn(async () => {}),
    creatingNewGroup,
    newGroupName,
    activeTab,
    paramConfigType
  );

  return { ops, emit, formState };
}

describe('useAlgorithmCrudOps 失败路径错误消息安全化（INT-1019）', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDefinitions.mockResolvedValue({ data: [], total: 0 });
    mockGetGroups.mockResolvedValue({ data: [] });
    mockCreateDefinition.mockResolvedValue({ id: 1 });
    mockUpdateDefinition.mockResolvedValue({});
    mockGetDefinition.mockResolvedValue(null);
    mockDeleteDefinition.mockResolvedValue({});
  });

  it('saveAlgorithm 失败（原始 gRPC 异常文本）：降级固定文案，不直出原文', async () => {
    mockCreateDefinition.mockRejectedValue(new Error(RAW_RPC));
    const { ops } = setup('create');

    await ops.saveAlgorithm();

    expect(notifyError).toHaveBeenCalledTimes(1);
    expect(notifyError).toHaveBeenCalledWith('保存算法失败: 算法服务暂不可用，请稍后重试');
  });

  it('saveAlgorithm 失败（正常业务错误）：保留业务文案', async () => {
    mockCreateDefinition.mockRejectedValue(new Error('类型已存在'));
    const { ops } = setup('create');

    await ops.saveAlgorithm();

    expect(notifyError).toHaveBeenCalledWith('保存算法失败: 类型已存在');
  });

  it('saveAlgorithm 失败（非 Error 抛出）：未知错误兜底（INT-291 契约）', async () => {
    mockCreateDefinition.mockRejectedValue('boom');
    const { ops } = setup('create');

    await ops.saveAlgorithm();

    expect(notifyError).toHaveBeenCalledWith('保存算法失败: 未知错误');
  });

  it('saveAlgorithm 成功：无错误通知，emit success / update:visible false 并刷新列表', async () => {
    const { ops, emit } = setup('create');

    await ops.saveAlgorithm();

    expect(notifyError).not.toHaveBeenCalled();
    expect(emit).toHaveBeenCalledWith('success');
    expect(emit).toHaveBeenCalledWith('update:visible', false);
    expect(mockGetDefinitions).toHaveBeenCalled();
  });

  it('handleEdit 失败（原始 gRPC 异常文本）：加载算法详情失败固定文案，不再静默', async () => {
    mockGetDefinition.mockRejectedValue(new Error(RAW_RPC));
    const { ops } = setup('edit');

    await ops.handleEdit({ type: 'voice_llm', name: '语音大模型', status: 'online' } as any);

    expect(notifyError).toHaveBeenCalledWith('加载算法详情失败: 算法服务暂不可用，请稍后重试');
  });

  it('handleToggleStatus 失败（原始 gRPC 异常文本）：启用失败固定文案，不再静默', async () => {
    mockUpdateDefinition.mockRejectedValue(new Error(RAW_RPC));
    const { ops } = setup('list');

    await ops.handleToggleStatus({ type: 'voice_llm', name: '语音大模型', status: 'offline' } as any);

    expect(notifyError).toHaveBeenCalledWith('启用失败: 算法服务暂不可用，请稍后重试');
  });

  it('executeDelete 失败（原始 gRPC 异常文本）：删除算法失败固定文案，不再静默', async () => {
    mockDeleteDefinition.mockRejectedValue(new Error(RAW_RPC));
    const { ops } = setup('list');

    await ops.executeDelete({ type: 'voice_llm', name: '语音大模型' } as any);

    expect(notifyError).toHaveBeenCalledWith('删除算法失败: 算法服务暂不可用，请稍后重试');
  });
});
