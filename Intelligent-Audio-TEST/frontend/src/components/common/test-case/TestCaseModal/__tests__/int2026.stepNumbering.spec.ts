/**
 * INT-2026 横向步骤导航编号连续回归锁定：
 * 「参考参数」原先取 base.length + 2，而「评估维度」刚以 base.length + 1 入栈，
 * 于是参考参数恒比正确编号多 1（API 缺 4、端到端缺 5）。
 * 编号必须按顺序生成，两种用例类型都是 1..N 连续。
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';

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
  AlgoParamsStep: true,
  AudioListStep: true,
  NoiseInterferenceStep: true,
  RoundEvaluationEditor: true,
  ReferencePathStep: true,
};

function mountEditor(testType: 'api' | 'e2e') {
  return mount(RoundConfigEditor, {
    props: {
      modelValue: [{ roundNumber: 1, audios: [] }],
      testType,
      caseAlgorithmParams: [],
      algorithmType: 'asr',
      algorithmFormSchema: null,
      algorithmParams: [],
    },
    global: { stubs: childStubs },
  });
}

function tocItems(wrapper: any): Array<{ num: string; label: string }> {
  return wrapper.findAll('.rce-toc-item').map((item: any) => ({
    num: item.find('.rce-toc-num').text(),
    label: item.find('.rce-toc-label').text(),
  }));
}

describe('INT-2026 RoundConfigEditor · 步骤导航编号', () => {
  it('API 用例四步编号为 1..4（参考参数 = 4，不跳号）', () => {
    const wrapper = mountEditor('api');
    expect(tocItems(wrapper)).toEqual([
      { num: '1', label: '算法参数' },
      { num: '2', label: '音频列表' },
      { num: '3', label: '评估维度' },
      { num: '4', label: '参考参数' },
    ]);
  });

  it('端到端用例五步编号为 1..5（参考参数 = 5，不跳号）', () => {
    const wrapper = mountEditor('e2e');
    expect(tocItems(wrapper)).toEqual([
      { num: '1', label: '算法参数' },
      { num: '2', label: '音频列表' },
      { num: '3', label: '噪声 & 干扰' },
      { num: '4', label: '评估维度' },
      { num: '5', label: '参考参数' },
    ]);
  });

  it('切换用例类型后编号随之重排（不回退到旧编号）', async () => {
    const wrapper = mountEditor('api');
    await wrapper.setProps({ testType: 'e2e' });
    expect(tocItems(wrapper).map((s) => s.num)).toEqual(['1', '2', '3', '4', '5']);
    await wrapper.setProps({ testType: 'api' });
    expect(tocItems(wrapper).map((s) => s.num)).toEqual(['1', '2', '3', '4']);
  });
});
