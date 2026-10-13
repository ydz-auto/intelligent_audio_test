/**
 * INT-259 批量导入/导出模态窗确认链回归锁定：
 * footer 按钮只触发表单校验（child.handleSubmit），真正保存由 @submit 回调
 * （handleExportConfirm / handleImportConfirm）emit('save') 承担。
 * 此前 footer 与 @submit 绑定同一函数且互相调用 child.handleSubmit → emit('submit')，
 * 形成 emit 递归死循环（栈溢出），导出/导入永远无法执行。
 * 契约：一次点击恰好产生一条 save 事件（递归回归会直接爆栈使本用例失败）。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const casesState = vi.hoisted(() => ({
  items: [
    { id: 'c1', name: '用例1', groupName: 'g1', type: 'api', config: {} },
    { id: 'c2', name: '用例2', groupName: 'g1', type: 'e2e', config: {} },
  ] as any[],
}));

vi.mock('@/composables/testCase/testcasesPort', () => ({
  testcasesPort: {
    getGroups: vi.fn(async () => ({ items: [{ id: 'g1_id', name: 'g1' }] })),
    getAll: vi.fn(async () => ({
      items: casesState.items,
      total: casesState.items.length,
      page: 1,
      pages: 1,
      perPage: 100,
    })),
    export: vi.fn(async () => new Blob(['{}'], { type: 'application/json' })),
    downloadTemplate: vi.fn(async () => new Blob([''], { type: 'application/octet-stream' })),
    previewImport: vi.fn(async () => ({})),
  },
}));
vi.mock('@/composables/shared/tagsPort', () => ({
  tagsPort: { getTagNames: vi.fn(async () => ({ items: [] })) },
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

function mountModal(mode: 'import' | 'export') {
  return mount(TestCaseModal, {
    props: {
      visible: true,
      mode,
      testType: 'e2e',
      formData: {},
      title: mode === 'export' ? '批量导出测试用例' : '批量导入测试用例',
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

async function clickFooterButton(wrapper: ReturnType<typeof mountModal>, text: string) {
  const btn = wrapper.findAll('button').find(b => b.text().trim() === text);
  expect(btn, `底部「${text}」按钮存在`).toBeTruthy();
  await btn!.trigger('click');
  await flushPromises();
}

function saveEvents(wrapper: ReturnType<typeof mountModal>): any[] {
  return (wrapper.emitted('save') ?? []).map(e => e[0]);
}

describe('INT-259 导入/导出模态窗 · 确认链 emit 递归回归', () => {
  it('导出：选分组后点「导出」恰好产生一条 save 事件，载荷含 format/ids（递归回归会爆栈）', async () => {
    const wrapper = mountModal('export');
    await flushPromises();

    const groupCheckbox = wrapper.find('input#group-g1');
    expect(groupCheckbox.exists(), '分组勾选框存在').toBe(true);
    await groupCheckbox.setValue(true);
    // 模态窗以 e2e 挂载 → 导出类型默认 e2e；切到「所有配置」断言全量 ids
    await wrapper.find('select#export-test-type').setValue('all');
    await flushPromises();

    await clickFooterButton(wrapper, '导出');

    const events = saveEvents(wrapper);
    expect(events.length, '恰好一条 save 事件（不递归）').toBe(1);
    expect(events[0].mode).toBe('export');
    expect(events[0].data.ids).toEqual(['c1', 'c2']);
    expect(events[0].data.format).toBe('json');
  });

  it('导出：未选分组时点「导出」不产生 save 事件', async () => {
    const wrapper = mountModal('export');
    await flushPromises();

    // isSubmitDisabled 依据 groups 长度禁用按钮；直接断言按钮禁用态
    const exportBtn = wrapper.findAll('button').find(b => b.text().trim() === '导出');
    expect(exportBtn?.attributes('disabled')).toBeDefined();
    expect(saveEvents(wrapper)).toHaveLength(0);
  });

  it('导入：选择合法文件后点「导入」恰好产生一条 save 事件并关闭模态窗', async () => {
    const wrapper = mountModal('import');
    await flushPromises();

    const input = wrapper.find('input#import-file');
    expect(input.exists(), '文件输入存在').toBe(true);
    const file = new File(['{"cases":[]}'], 'cases.json', { type: 'application/json' });
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    await flushPromises();

    await clickFooterButton(wrapper, '导入');

    const events = saveEvents(wrapper);
    expect(events.length, '恰好一条 save 事件（不递归）').toBe(1);
    expect(events[0].mode).toBe('import');
    expect(events[0].data.file).toBe(file);
    expect(wrapper.emitted('close'), '模态窗关闭').toBeTruthy();
  });

  it('导入：未选文件时点「导入」不发 save 事件（校验拦截，模态不关闭）', async () => {
    const wrapper = mountModal('import');
    await flushPromises();

    await clickFooterButton(wrapper, '导入');

    expect(saveEvents(wrapper)).toHaveLength(0);
    expect(wrapper.emitted('close')).toBeUndefined();
  });
});
