/**
 * INT-195 用例编辑模态窗改分组回归锁定：
 * 提交边界（handleCaseSave）必须把 groupId 收敛到当前所选分组名——
 * 后端 group_id 优先级最高，编辑回填/初始深拷贝残留的旧 groupId 一旦随载荷提交，
 * 就会压住用户新选分组（改分组静默失效）。new-group 流程不得携带旧 groupId。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const groupsState = vi.hoisted(() => ({
  items: [
    { id: 'g1_id', name: 'g1' },
    { id: 'g2_id', name: 'g2' },
  ] as any[],
}));

vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({ items: groupsState.items })),
  },
}));
vi.mock('@/composables/shared/tagsPort', () => ({
  tagsPort: { getTagNames: vi.fn(async () => ({ items: [] })) },
}));
vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getFormSchema: vi.fn(async () => ({})) },
}));
vi.mock('@/composables/algorithm/useAlgorithmConfig', () => ({
  useAlgorithmConfig: () => ({
    getAlgorithmOptions: vi.fn(async () => []),
    getCaseAlgorithmParams: vi.fn(async () => []),
  }),
}));
vi.mock('@/composables/algorithm/useAlgorithmLabels', () => ({
  useAlgorithmLabels: () => ({
    algorithmOptions: { value: [] },
    loadAlgorithms: vi.fn(async () => {}),
  }),
}));
vi.mock('@/composables/device/playbackPort', () => ({
  playbackPort: { getAll: vi.fn(async () => []) },
}));
vi.mock('@/composables/audio/audiosPort', () => ({
  audiosPort: {
    getAll: vi.fn(async () => ({ items: [] })),
    getByIds: vi.fn(async () => []),
  },
}));
vi.mock('../useAudioConfig', () => ({
  useAudioConfig: () => {
    const r = (v: any) => ({ value: v });
    return {
      playbackDevices: r([]),
      loadResources: vi.fn(async () => {}),
      showAudioModal: r(false),
      showDeviceModal: r(false),
      showNoiseDeviceModal: r(false),
      showBatchDeviceModal: r(false),
      showCrossDeviceModal: r(false),
      showBatchSplModal: r(false),
      showAudioPreviewModal: r(false),
      currentAudioType: r('dry'),
      currentAudioIndex: r(null),
      currentDeviceAudioIndex: r(null),
      initialSelectedDevices: r([]),
      noiseInitialSelectedDevices: r([]),
      batchInitialSelectedDevices: r([]),
      crossDeviceInitialSelectedDevices: r([]),
      batchSplValue: r(65),
      currentPreviewAudioId: r(null),
      currentPreviewAudioType: r('dry'),
      currentPreviewDeviceId: r(null),
      currentPreviewSpl: r(65),
      currentPreviewOffset: r(0),
      noiseAudios: r([]),
      dryAudios: r([]),
      handleAudioSelect: vi.fn(),
      handleMultipleAudioSelect: vi.fn(),
      handleDeviceSelect: vi.fn(),
      handleBatchDeviceSelect: vi.fn(),
      handleCrossDeviceSelect: vi.fn(),
    };
  },
}));
vi.mock('../useDimensionConfig', () => ({
  useDimensionConfig: () => ({
    availableDimensions: { value: [] },
    loadDimensions: vi.fn(async () => {}),
  }),
}));

import TestCaseModal from '../index.vue';

function editFormData(overrides: Record<string, any> = {}) {
  return {
    id: 'case-1',
    name: '用例A',
    group: 'g1',
    groupId: 'g1_id',
    description: '',
    tags: [],
    testType: 'e2e',
    algorithmType: '',
    algorithmParams: [],
    config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    ...overrides,
  };
}

function mountModal(formData: Record<string, any>) {
  return mount(TestCaseModal, {
    props: {
      visible: true,
      mode: 'case',
      testType: 'e2e',
      formData,
      title: '编辑测试用例',
    },
    global: {
      stubs: {
        teleport: true,
        AlgorithmSelector: true,
        RoundConfigEditor: true,
        OverallEvaluationEditor: true,
        GlobalNoiseEditor: true,
        AudioSelectModal: true,
        AudioPreviewModal: true,
        GlobalPlaybackDeviceModal: true,
        BatchSplModal: true,
      },
    },
  });
}

async function clickSave(wrapper: ReturnType<typeof mountModal>) {
  const saveBtn = wrapper.findAll('button').find(b => b.text() === '保存');
  expect(saveBtn, '保存按钮存在').toBeTruthy();
  await saveBtn!.trigger('click');
  await flushPromises();
}

function firstSavePayload(wrapper: ReturnType<typeof mountModal>): any {
  const events = wrapper.emitted('save');
  expect(events, 'save 事件已发出').toBeTruthy();
  return events![0][0];
}

describe('INT-195 编辑模态窗改分组 · 提交边界 groupId 收敛', () => {
  it('改选分组后保存：groupId 收敛为新选分组的 ID', async () => {
    const wrapper = mountModal(editFormData());
    await flushPromises();

    const select = wrapper.find('#caseGroup');
    expect((select.element as HTMLSelectElement).value).toBe('g1');
    await select.setValue('g2');
    await flushPromises();

    await clickSave(wrapper);
    const payload = firstSavePayload(wrapper);
    expect(payload.mode).toBe('case');
    expect(payload.data.group).toBe('g2');
    expect(payload.data.groupId).toBe('g2_id');
  });

  it('未改动直接保存（残留旧 groupId 的深拷贝场景）：groupId 仍收敛为回填分组名对应 ID，不透传残留值', async () => {
    // 模拟初始深拷贝携带与所选分组名不一致的旧 groupId（历史回归陷阱）
    const wrapper = mountModal(editFormData({ groupId: 'stale_old_id' }));
    await flushPromises();

    await clickSave(wrapper);
    const payload = firstSavePayload(wrapper);
    expect(payload.data.group).toBe('g1');
    expect(payload.data.groupId).toBe('g1_id');
    expect(payload.data.groupId).not.toBe('stale_old_id');
  });

  it('新建分组流程：不携带旧 groupId，载荷按新名提交并标记 createNewGroup', async () => {
    const wrapper = mountModal(editFormData({ groupId: 'g1_id' }));
    await flushPromises();

    await wrapper.find('#caseGroup').setValue('new-group');
    const newNameInput = wrapper.find('input[placeholder="输入新分组名称"]');
    expect(newNameInput.exists()).toBe(true);
    await newNameInput.setValue('INT195新组');
    await flushPromises();

    await clickSave(wrapper);
    const payload = firstSavePayload(wrapper);
    expect(payload.data.group).toBe('INT195新组');
    expect(payload.data.createNewGroup).toBe(true);
    expect(payload.data.groupId).toBeUndefined();
  });

  it('所选分组不在分组列表（列表加载失败/竞态）：保存被拦截，不发静默请求', async () => {
    groupsState.items = [];
    try {
      const wrapper = mountModal(editFormData());
      await flushPromises();

      await clickSave(wrapper);
      expect(wrapper.emitted('save'), '载荷被拦截，save 未发出').toBeUndefined();
    } finally {
      groupsState.items = [
        { id: 'g1_id', name: 'g1' },
        { id: 'g2_id', name: 'g2' },
      ];
    }
  });
});
