/**
 * INT-259 轮次复制/删除与算法参数独立列同步回归锁定：
 * 1) 删除轮次：独立列按「旧轮号→新轮号」映射重编号——原实现按数组下标重编号，
 *    在 push 追加序（先编辑后轮再编辑前轮）下会把不同轮的参数互相串写；
 * 2) 复制轮次：源轮的算法参数条目必须同步复制到新轮号（否则复制轮参数为空）。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../../../../composables/modal/useModal', () => ({
  useModalControl: () => ({
    open: vi.fn(async () => true),
    close: vi.fn(),
    closeAll: vi.fn(),
    getActiveModals: vi.fn(() => []),
    updateModalProps: vi.fn(),
    registerModal: vi.fn(),
  }),
  MODAL_TYPES: { DELETE_CONFIRM: 'deleteConfirm' },
}));

import RoundConfigEditor from '../RoundConfigEditor.vue';

const childStubs = {
  RoundNav: true,
  RoundHead: true,
  StepToc: true,
  AlgoParamsStep: true,
  AudioListStep: true,
  NoiseInterferenceStep: true,
  RoundEvaluationEditor: true,
  ReferencePathStep: true,
};

function mountEditor(rounds: any[], algorithmParams: any[]) {
  return mount(RoundConfigEditor, {
    props: {
      modelValue: rounds,
      testType: 'e2e' as const,
      caseAlgorithmParams: [],
      algorithmType: 'asr',
      algorithmFormSchema: null,
      algorithmParams,
      testCaseId: 'case-1',
    },
    global: { stubs: childStubs },
  });
}

function algoParamEvents(wrapper: any): any[][] {
  return wrapper.emitted('update:algorithmParams') ?? [];
}

describe('INT-259 RoundConfigEditor · 算法参数独立列轮次同步', () => {
  it('删除中间轮：剩余轮参数按旧轮号顺序重编号，乱序数组不串写', async () => {
    // 参数条目为 push 追加序（round2 先于 round1 编辑过）
    const wrapper = mountEditor(
      [
        { roundNumber: 1, audios: [{ audioId: 'a1' }] },
        { roundNumber: 2, audios: [] },
        { roundNumber: 3, audios: [] },
      ],
      [
        { roundNumber: 2, params: [{ fieldCode: 'k2', fieldValue: 'v2' }] },
        { roundNumber: 1, params: [{ fieldCode: 'k1', fieldValue: 'v1' }] },
      ],
    );
    await flushPromises();

    // 定位到第 3 轮（index 2）后删除
    (wrapper.vm as any).activeRoundIndex = 2;
    await (wrapper.vm as any).removeCurrentRound();
    await flushPromises();

    const events = algoParamEvents(wrapper);
    expect(events.length, '发出独立列更新').toBeGreaterThan(0);
    const grouped = events[events.length - 1][0];
    // 按轮号断言取值正确（消费方均按 roundNumber 查找，数组顺序不承载语义）
    const byRn = Object.fromEntries(grouped.map((e: any) => [e.roundNumber, e.params]));
    expect(grouped).toHaveLength(2);
    expect(byRn[1]).toEqual([{ fieldCode: 'k1', fieldValue: 'v1' }]);
    expect(byRn[2]).toEqual([{ fieldCode: 'k2', fieldValue: 'v2' }]);
  });

  it('删除首轮：旧 round2/3 的参数顺移为新 round1/2，被删轮条目清除', async () => {
    const wrapper = mountEditor(
      [
        { roundNumber: 1, audios: [] },
        { roundNumber: 2, audios: [] },
        { roundNumber: 3, audios: [] },
      ],
      [
        { roundNumber: 1, params: [{ fieldCode: 'k1', fieldValue: 'v1' }] },
        { roundNumber: 2, params: [{ fieldCode: 'k2', fieldValue: 'v2' }] },
        { roundNumber: 3, params: [{ fieldCode: 'k3', fieldValue: 'v3' }] },
      ],
    );
    await flushPromises();

    (wrapper.vm as any).activeRoundIndex = 0;
    await (wrapper.vm as any).removeCurrentRound();
    await flushPromises();

    const grouped = algoParamEvents(wrapper).slice(-1)[0][0];
    expect(grouped).toEqual([
      { roundNumber: 1, params: [{ fieldCode: 'k2', fieldValue: 'v2' }] },
      { roundNumber: 2, params: [{ fieldCode: 'k3', fieldValue: 'v3' }] },
    ]);
  });

  it('复制轮次：源轮参数条目深拷贝到新轮号', async () => {
    const wrapper = mountEditor(
      [{ roundNumber: 1, audios: [{ audioId: 'a1' }] }],
      [{ roundNumber: 1, params: [{ fieldCode: 'voiceprint', fieldValue: { audioId: 'a1' } }] }],
    );
    await flushPromises();

    await (wrapper.vm as any).copyCurrentRound();
    await flushPromises();

    const grouped = algoParamEvents(wrapper).slice(-1)[0][0];
    expect(grouped).toHaveLength(2);
    expect(grouped[1]).toEqual({
      roundNumber: 2,
      params: [{ fieldCode: 'voiceprint', fieldValue: { audioId: 'a1' } }],
    });
    // 深拷贝：修改副本不影响源条目对象
    expect(grouped[1].params).not.toBe(grouped[0].params);
  });
});
