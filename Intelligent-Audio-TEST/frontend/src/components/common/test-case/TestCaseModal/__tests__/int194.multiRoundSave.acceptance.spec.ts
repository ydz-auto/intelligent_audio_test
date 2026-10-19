/**
 * INT-194 验收测试：用例编辑模态窗保存保留第 2+ 轮算法参数
 *
 * 原缺陷：handleCaseSave 用 CaseForm 暴露的单轮扁平 algorithmParams 对象覆写
 * saveData.algorithmParams（按轮分组独立列），后端整体替换语义下第 2+ 轮被清空。
 * 修复（7db1517a）：移除覆写，grouped 独立列以 caseFormData 为唯一权威整体透传。
 *
 * 覆盖点（对应开发提测报告的 5 个测试点）：
 * A1 两轮用例编辑模态窗直接点保存不丢轮（复现原缺陷场景）
 * A2 第 1 轮参数改动生效且第 2 轮不丢（经 RoundConfigEditor→CaseForm 同步链路）
 * A3 锁定模式（testType 锁定为 api）下编辑保存不丢轮
 * A4 删除轮次后独立列同步移除并重编号（RoundConfigEditor 既有逻辑回归）
 * A5 新增用例（无 id）带算法参数保存，参数进入提交载荷
 */
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent } from 'vue';

vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({
      items: [
        { id: 'g1_id', name: 'g1' },
        { id: 'g2_id', name: 'g2' },
      ],
    })),
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
// RoundConfigEditor 的删除确认弹窗：mock 为立即确认（真实弹窗流程不在本卡范围）
vi.mock('../../../../../composables/modal/useModal', async () => {
  const actual = await vi.importActual<any>('../../../../../composables/modal/useModal');
  return {
    ...actual,
    useModalControl: () => ({
      open: vi.fn(async () => ({})),
      close: vi.fn(),
      closeAll: vi.fn(),
    }),
  };
});

import TestCaseModal from '../index.vue';
import RoundConfigEditor from '../RoundConfigEditor.vue';
import { convertTestCaseFormData } from '@/utils/testCaseConfig';
// INT-972：snake_case 转换已收敛到 adapter（toTestCaseUpsertDto），表单归一化输出 camelCase 草稿
import { toTestCaseUpsertDto } from '@/infrastructure/adapters/testCaseAdapter';

function twoRoundEditFormData() {
  return {
    id: 'case-1',
    name: '两轮用例',
    group: 'g1',
    groupId: 'g1_id',
    description: '',
    tags: [],
    testType: 'api',
    algorithmType: 'qwen_ast',
    algorithmParams: [
      { roundNumber: 1, params: [{ fieldCode: 'threshold', fieldValue: 0.5 }] },
      { roundNumber: 2, params: [{ fieldCode: 'threshold', fieldValue: 0.8 }] },
    ],
    config: {
      rounds: [
        {
          roundNumber: 1,
          audios: [{ audioId: 'a1', playbackDeviceId: 'd1', spl: 65, playOrder: 0 }],
          evaluation: { enabled: false, dimensions: [] },
        },
        {
          roundNumber: 2,
          audios: [{ audioId: 'a2', playbackDeviceId: 'd2', spl: 70, playOrder: 0 }],
          evaluation: { enabled: false, dimensions: [] },
        },
      ],
      dimensions: [],
    },
  };
}

function round1ModifiedGrouped() {
  return [
    { roundNumber: 1, params: [{ fieldCode: 'threshold', fieldValue: 0.9 }] },
    { roundNumber: 2, params: [{ fieldCode: 'threshold', fieldValue: 0.8 }] },
  ];
}

// RoundConfigEditor 桩：提供按钮触发 update:algorithmParams（模拟 AlgoParamsStep 按轮编辑回传）
const RoundConfigEditorEmitStub = defineComponent({
  name: 'RoundConfigEditor',
  props: ['modelValue', 'algorithmParams'],
  emits: ['update:algorithmParams', 'update:modelValue'],
  template: `<button class="rc-edit-round1" @click="$emit('update:algorithmParams', editedGrouped)">edit</button>`,
  computed: {
    editedGrouped() {
      return round1ModifiedGrouped();
    },
  },
});

function mountEditModal(testType: 'api' | 'e2e' = 'api') {
  return mount(TestCaseModal, {
    props: {
      visible: true,
      mode: 'case',
      testType,
      formData: twoRoundEditFormData(),
      title: '编辑测试用例',
    },
    global: {
      stubs: {
        teleport: true,
        CaseForm: false,
        AlgorithmSelector: true,
        RoundConfigEditor: RoundConfigEditorEmitStub,
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

async function clickSave(wrapper: ReturnType<typeof mountEditModal>) {
  const saveBtn = wrapper.findAll('button').find(b => b.text() === '保存');
  expect(saveBtn, '保存按钮存在').toBeTruthy();
  await saveBtn!.trigger('click');
  await flushPromises();
  const events = wrapper.emitted('save');
  expect(events, 'save 事件已发出').toBeTruthy();
  return (events![0][0] as any);
}

describe('INT-194 验收 · 模态窗保存路径（原缺陷场景）', () => {
  it('A1 两轮用例直接点保存：第 2 轮算法参数与结构均保留', async () => {
    const wrapper = mountEditModal();
    await flushPromises();

    const payload = await clickSave(wrapper);
    expect(payload.isEdit).toBe(true);

    // 模态窗 emit 的 data：grouped 独立列整体透传，两轮都在
    const col = payload.data.algorithmParams;
    expect(Array.isArray(col)).toBe(true);
    expect(col).toHaveLength(2);
    expect(col[0].roundNumber).toBe(1);
    expect(col[1].roundNumber).toBe(2);
    expect(col[1].params).toEqual([{ fieldCode: 'threshold', fieldValue: 0.8 }]);
    expect(payload.data.config.rounds).toHaveLength(2);

    // 落库前的真实 wire 格式（store.updateTestCase → testcasesApi.update 走 toTestCaseUpsertDto）
    const wire: any = toTestCaseUpsertDto(convertTestCaseFormData(payload.data));
    expect(wire.algorithm_params).toHaveLength(2);
    expect(wire.algorithm_params[0]).toEqual({
      round_number: 1,
      params: [{ field_code: 'threshold', field_value: 0.5 }],
    });
    expect(wire.algorithm_params[1]).toEqual({
      round_number: 2,
      params: [{ field_code: 'threshold', field_value: 0.8 }],
    });
    expect(wire.config.rounds).toHaveLength(2);
    expect(wire.config.rounds[1].round_number).toBe(2);
  });

  it('A2 第 1 轮参数改动生效且第 2 轮不丢（RoundConfigEditor→CaseForm 同步链路）', async () => {
    const wrapper = mountEditModal();
    await flushPromises();

    // 桩按钮触发 RoundConfigEditor 的 update:algorithmParams（第 1 轮 0.5→0.9，第 2 轮不动）
    const rcStub = wrapper.findComponent({ name: 'RoundConfigEditor' });
    expect(rcStub.exists()).toBe(true);
    await rcStub.find('button.rc-edit-round1').trigger('click');
    await flushPromises();

    const payload = await clickSave(wrapper);
    const col = payload.data.algorithmParams;
    expect(col).toHaveLength(2);
    expect(col[0].params).toEqual([{ fieldCode: 'threshold', fieldValue: 0.9 }]);
    expect(col[1].params).toEqual([{ fieldCode: 'threshold', fieldValue: 0.8 }]);

    const wire: any = toTestCaseUpsertDto(convertTestCaseFormData(payload.data));
    expect(wire.algorithm_params[0].params[0].field_value).toBe(0.9);
    expect(wire.algorithm_params[1].params[0].field_value).toBe(0.8);
  });

  it('A3 锁定模式（testType 锁定）下直接保存不丢第 2 轮', async () => {
    const wrapper = mountEditModal('api');
    await flushPromises();

    const payload = await clickSave(wrapper);
    const col = payload.data.algorithmParams;
    expect(col).toHaveLength(2);
    expect(col[1].roundNumber).toBe(2);
    const wire: any = toTestCaseUpsertDto(convertTestCaseFormData(payload.data));
    expect(wire.algorithm_params).toHaveLength(2);
  });

  it('A5 新增用例（无 id）带算法参数保存：载荷无 id 且参数进入提交形态', async () => {
    const formData = twoRoundEditFormData();
    delete (formData as any).id;
    formData.name = '新增用例';
    formData.algorithmParams = [{ roundNumber: 1, params: [{ fieldCode: 'threshold', fieldValue: 0.6 }] }];

    const wrapper = mount(TestCaseModal, {
      props: {
        visible: true,
        mode: 'case',
        testType: 'api',
        formData,
        title: '新增测试用例',
      },
      global: {
        stubs: {
          teleport: true,
          CaseForm: false,
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
    await flushPromises();

    const payload = await clickSave(wrapper);
    expect(payload.isEdit).toBe(false);
    expect(payload.data.id).toBeUndefined();

    const wire: any = toTestCaseUpsertDto(convertTestCaseFormData(payload.data));
    // 第 1 轮参数进入提交形态；normalizeTestCaseConfig 会为无参数的轮次补空 entries
    //（testCaseConfig.ts:102-106 + 兼容合并 219-234，既有归一化行为，不丢数据）
    const round1 = (wire.algorithm_params as any[]).find(e => e.round_number === 1);
    expect(round1.params).toEqual([{ field_code: 'threshold', field_value: 0.6 }]);
    for (const e of wire.algorithm_params as any[]) {
      if (e.round_number !== 1) {
        expect(e.params).toEqual([]);
      }
    }
  });
});

// RoundConfigEditor 单元级：按轮编辑合并 / 删轮重编号（既有逻辑回归）
const editorStubs = {
  RoundNav: true,
  StepToc: true,
  RoundEvaluationEditor: true,
  ReferencePathStep: true,
  AudioListStep: true,
  NoiseInterferenceStep: true,
  AlgoParamsStep: defineComponent({
    name: 'AlgoParamsStep',
    props: { roundAlgorithmParams: { type: Array, default: () => [] } },
    emits: ['update:round-algo-params', 'update:round', 'open-audio-select'],
    template: `<button class="edit-algo" @click="$emit('update:round-algo-params', roundAlgorithmParams.map(p => p.fieldCode === 'threshold' ? { ...p, fieldValue: 0.9 } : p))">edit</button>`,
  }),
  RoundHead: defineComponent({
    name: 'RoundHead',
    props: ['round', 'activeIndex', 'totalRounds'],
    emits: ['delete', 'copy', 'update:active-index'],
    template: `<button class="delete-round" @click="$emit('delete')">delete</button>`,
  }),
};

describe('INT-194 验收 · RoundConfigEditor 按轮独立列', () => {
  function mountEditor() {
    return mount(RoundConfigEditor, {
      props: {
        modelValue: twoRoundEditFormData().config.rounds,
        testType: 'api',
        algorithmType: 'qwen_ast',
        algorithmParams: twoRoundEditFormData().algorithmParams,
      },
      global: { stubs: editorStubs },
    });
  }

  it('A4-1 编辑第 1 轮参数：独立列按 roundNumber 合并，第 2 轮不动', async () => {
    const wrapper = mountEditor();
    await flushPromises();

    await wrapper.find('button.edit-algo').trigger('click');
    await flushPromises();

    const events = wrapper.emitted('update:algorithmParams');
    expect(events, 'update:algorithmParams 已发出').toBeTruthy();
    const grouped = events![events!.length - 1][0] as any[];
    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toEqual({ roundNumber: 1, params: [{ fieldCode: 'threshold', fieldValue: 0.9 }] });
    expect(grouped[1]).toEqual({ roundNumber: 2, params: [{ fieldCode: 'threshold', fieldValue: 0.8 }] });
  });

  it('A4-2 删除第 1 轮：rounds 与独立列同步移除并重编号', async () => {
    const wrapper = mountEditor();
    await flushPromises();

    await wrapper.find('button.delete-round').trigger('click');
    await flushPromises();

    // 独立列：被删轮次的参数移除，剩余轮次重编号
    const algoEvents = wrapper.emitted('update:algorithmParams');
    expect(algoEvents, '独立列更新已发出').toBeTruthy();
    const grouped = algoEvents![algoEvents!.length - 1][0] as any[];
    expect(grouped).toHaveLength(1);
    expect(grouped[0].roundNumber).toBe(1);
    expect(grouped[0].params).toEqual([{ fieldCode: 'threshold', fieldValue: 0.8 }]);

    // rounds 重编号
    const roundEvents = wrapper.emitted('update:modelValue');
    expect(roundEvents, 'rounds 更新已发出').toBeTruthy();
    const rounds = roundEvents![roundEvents!.length - 1][0] as any[];
    expect(rounds).toHaveLength(1);
    expect(rounds[0].roundNumber).toBe(1);
    expect(rounds[0].audios[0].audioId).toBe('a2');
  });
});
