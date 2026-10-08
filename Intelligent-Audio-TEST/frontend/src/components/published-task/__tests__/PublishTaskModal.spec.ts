/**
 * PublishTaskModal Benchmark 选项组件测试
 * 覆盖：开关默认关闭、勾选后携带 benchmark/benchmarkSuite/benchmarkCategory、
 * 未填写的可选分组字段不随提交透传。
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import PublishTaskModal from '../PublishTaskModal.vue';

const tasks: any[] = [
  { id: 1, name: '任务一', status: 'completed', caseCount: 3 },
  { id: 2, name: '任务二', status: 'running', caseCount: 5 },
];

function mountModal() {
  return mount(PublishTaskModal, {
    props: { tasks, presetSourceTaskId: 1 },
    global: { stubs: { teleport: true } },
  });
}

describe('PublishTaskModal Benchmark 选项', () => {
  it('默认不勾选，确认时 benchmark=false 且不携带分组字段', async () => {
    const wrapper = mountModal();
    await wrapper.find('input.form-input[placeholder*="正式回归"]').setValue('回归任务');
    await wrapper.findAll('button.btn-primary').filter((b) => b.text().includes('发布'))[0].trigger('click');
    const payload = wrapper.emitted('confirm')![0][0] as any;
    expect(payload.benchmark).toBe(false);
    expect(payload.benchmarkSuite).toBeUndefined();
    expect(payload.benchmarkCategory).toBeUndefined();
  });

  it('勾选后展示测试集/类别输入，确认时携带 benchmark 布尔与分组字段', async () => {
    const wrapper = mountModal();
    expect(wrapper.find('input[placeholder*="librispeech"]').exists()).toBe(false);

    await wrapper.find('input[type="checkbox"]').setValue(true);
    expect(wrapper.find('input[placeholder*="librispeech"]').exists()).toBe(true);

    await wrapper.find('input.form-input[placeholder*="正式回归"]').setValue('回归任务');
    await wrapper.find('input[placeholder*="librispeech"]').setValue('librispeech-test-clean');
    await wrapper.find('select').setValue('asr');
    await wrapper.findAll('button.btn-primary').filter((b) => b.text().includes('发布'))[0].trigger('click');

    const payload = wrapper.emitted('confirm')![0][0] as any;
    expect(payload.benchmark).toBe(true);
    expect(payload.benchmarkSuite).toBe('librispeech-test-clean');
    expect(payload.benchmarkCategory).toBe('asr');
  });

  it('勾选但留空分组字段时仅携带 benchmark=true', async () => {
    const wrapper = mountModal();
    await wrapper.find('input.form-input[placeholder*="正式回归"]').setValue('回归任务');
    await wrapper.find('input[type="checkbox"]').setValue(true);
    await wrapper.findAll('button.btn-primary').filter((b) => b.text().includes('发布'))[0].trigger('click');
    const payload = wrapper.emitted('confirm')![0][0] as any;
    expect(payload.benchmark).toBe(true);
    expect(payload.benchmarkSuite).toBeUndefined();
    expect(payload.benchmarkCategory).toBeUndefined();
  });
});
