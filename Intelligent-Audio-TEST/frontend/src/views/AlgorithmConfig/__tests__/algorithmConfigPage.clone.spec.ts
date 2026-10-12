/**
 * 算法复制链路剔除行级 id 回归测试（INT-211）
 *
 * 旧实现 handleClone 将源算法定义原样展开提交，载荷携带源算法各行真实 id；
 * 后端 _update_params/_update_case_params/_update_mappings 的 id 对账分支按全局 id
 * 取行且不校验 algorithm_type 归属，导致副本保存改写源算法参数行、副本自身不产生参数行。
 *
 * 锁定契约：
 * 1. createDefinition 载荷中 deviceParams/apiParams/caseParams/mappings 列表项不含行级 id，
 *    其余字段完整保留，type/name 改写为副本；
 * 2. 源算法定义对象不被就地修改（源行 id 原样保留）；
 * 3. 维度关联保留 dimensionId（对账键语义由 adapter 恒传 dimension_id、剥离关系行 id）；
 * 4. wire 层：载荷经 toAlgorithmDefinitionDto 转换后五类列表项均不含行级 id（端到端断言）；
 * 5. 取消确认弹窗不发起 createDefinition。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { modalOpen, mockGetDefinition, mockCreateDefinition, mockGetDefinitions } = vi.hoisted(() => ({
  modalOpen: vi.fn(),
  mockGetDefinition: vi.fn(),
  mockCreateDefinition: vi.fn(),
  mockGetDefinitions: vi.fn(),
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    getDefinition: mockGetDefinition,
    createDefinition: mockCreateDefinition,
    getDefinitions: mockGetDefinitions,
    getGroups: vi.fn().mockResolvedValue({ data: [] }),
    deleteDefinition: vi.fn(),
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

import { useAlgorithmConfigPage } from '../AlgorithmConfigPage';
import { toAlgorithmDefinitionDto } from '@/infrastructure/adapters/algorithmAdapter';

const sourceDetail = {
  id: 101,
  type: 'voice_llm',
  name: '语音大模型',
  groupId: 3,
  deviceParams: [
    { id: 12, algorithmType: 'voice_llm', paramCode: 'audio_channel', paramName: '声道', paramType: 'number', direction: 'output', required: true, uiOrder: 3, hidden: false },
    { id: 13, algorithmType: 'voice_llm', paramCode: 'sample_rate', paramName: '采样率', paramType: 'text', direction: 'input', required: false, uiOrder: 1, hidden: false },
  ],
  apiParams: [
    { id: 15, algorithmType: 'voice_llm', paramCode: 'api_lang', paramName: '语言', paramType: 'text', direction: 'input', required: false, uiOrder: 0, hidden: false },
  ],
  caseParams: [
    { id: 21, algorithmType: 'voice_llm', paramCode: 'lang', paramName: '语言', paramType: 'text', required: true, uiOrder: 0, hidden: false, scope: 'common' },
  ],
  params: [
    { id: 12, paramCode: 'audio_channel', paramName: '声道' },
  ],
  mappings: {
    device: [
      { id: 31, algorithmType: 'voice_llm', source: 'device', sourceParam: 'asr_text', sourceDirection: 'output', targetParam: 'text', transformType: 'none' },
    ],
    api: [],
    evaluation: [
      { id: 32, algorithmType: 'voice_llm', source: 'case', sourceParam: 'ref', sourceDirection: 'output', dimensionId: 5, targetParam: 'acc', transformType: 'none' },
    ],
  },
  associatedDimensions: [
    { id: 41, dimensionId: 8, name: '准确率', weight: 1.5, isDefault: true },
  ],
  referenceParams: [
    { id: 51, code: 'ref1', name: '参考1', type: 'text' },
  ],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-02T00:00:00Z',
};

const sourceRecord = { id: 101, type: 'voice_llm', name: '语音大模型' } as any;

function setupClone() {
  const view = useAlgorithmConfigPage();
  modalOpen.mockResolvedValue(true);
  mockGetDefinition.mockResolvedValue(sourceDetail);
  mockCreateDefinition.mockResolvedValue({ ...sourceDetail, type: 'voice_llm_copy' });
  mockGetDefinitions.mockResolvedValue({ data: [], total: 0 });
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAlgorithmConfigPage.handleClone 载荷剔除行级 id（INT-211）', () => {
  it('createDefinition 载荷四类参数列表不含行级 id，其余字段与副本命名保留', async () => {
    const view = setupClone();
    await view.handleClone(sourceRecord);

    expect(mockCreateDefinition).toHaveBeenCalledTimes(1);
    const payload = mockCreateDefinition.mock.calls[0][0] as any;

    expect(payload.type).toBe('voice_llm_copy');
    expect(payload.name).toBe('语音大模型 (副本)');
    expect(payload.groupId).toBe(3);

    for (const list of [payload.deviceParams, payload.apiParams, payload.caseParams]) {
      expect(list.length).toBeGreaterThan(0);
      for (const item of list) {
        expect('id' in item).toBe(false);
      }
    }
    expect(payload.deviceParams[0]).toMatchObject({ paramCode: 'audio_channel', paramName: '声道', direction: 'output', required: true, uiOrder: 3, hidden: false });
    expect(payload.apiParams[0]).toMatchObject({ paramCode: 'api_lang', paramName: '语言' });
    expect(payload.caseParams[0]).toMatchObject({ paramCode: 'lang', scope: 'common', required: true });

    for (const list of Object.values(payload.mappings) as any[][]) {
      for (const item of list) {
        expect('id' in item).toBe(false);
      }
    }
    expect(payload.mappings.device[0]).toMatchObject({ sourceParam: 'asr_text', targetParam: 'text', sourceDirection: 'output' });
    expect(payload.mappings.evaluation[0]).toMatchObject({ sourceParam: 'ref', targetParam: 'acc', dimensionId: 5 });
  });

  it('维度关联保留 dimensionId 对账键（关系行 id 的剥离由 adapter 负责）', async () => {
    const view = setupClone();
    await view.handleClone(sourceRecord);

    const payload = mockCreateDefinition.mock.calls[0][0] as any;
    expect(payload.associatedDimensions).toEqual([
      { id: 41, dimensionId: 8, name: '准确率', weight: 1.5, isDefault: true },
    ]);
  });

  it('源算法定义对象不被就地修改（源行 id 原样保留）', async () => {
    const view = setupClone();
    await view.handleClone(sourceRecord);

    expect(sourceDetail.deviceParams[0].id).toBe(12);
    expect(sourceDetail.apiParams[0].id).toBe(15);
    expect(sourceDetail.caseParams[0].id).toBe(21);
    expect(sourceDetail.mappings.device[0].id).toBe(31);
    expect(sourceDetail.type).toBe('voice_llm');
    expect(sourceDetail.name).toBe('语音大模型');
  });

  it('wire 层：载荷经 toAlgorithmDefinitionDto 转换后五类列表项均不含行级 id', async () => {
    const view = setupClone();
    await view.handleClone(sourceRecord);

    const payload = mockCreateDefinition.mock.calls[0][0] as any;
    const body = toAlgorithmDefinitionDto(payload);

    for (const list of [body.device_params, body.api_params, body.case_params]) {
      expect(list.length).toBeGreaterThan(0);
      for (const item of list) {
        expect('id' in item).toBe(false);
      }
    }
    for (const list of Object.values(body.mappings) as any[][]) {
      for (const item of list) {
        expect('id' in item).toBe(false);
      }
    }
    for (const item of body.associated_dimensions) {
      expect('id' in item).toBe(false);
      expect(item.dimension_id).toBeDefined();
    }
  });

  it('取消确认弹窗不发起 createDefinition', async () => {
    const view = setupClone();
    modalOpen.mockResolvedValue(false);
    await view.handleClone(sourceRecord);

    expect(mockGetDefinition).not.toHaveBeenCalled();
    expect(mockCreateDefinition).not.toHaveBeenCalled();
  });
});
