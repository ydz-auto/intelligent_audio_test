import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { useAudioImport } from './audioImport';

vi.mock('../../utils/api', () => ({
  audiosApi: {
    getAllTags: vi.fn().mockResolvedValue({ success: true, data: { items: [] } }),
    getAll: vi.fn().mockResolvedValue({ success: true, data: { items: [], total: 0 } }),
    getDirections: vi.fn().mockResolvedValue({ items: [] }),
  },
  devicesApi: {
    getPlaybackDevices: vi.fn().mockResolvedValue({ success: true, data: { items: [] } }),
  },
}));

vi.mock('../../utils/modalManager', () => ({
  getModalManager: () => ({
    open: vi.fn(),
    closeAll: vi.fn(),
  }),
}));

vi.mock('../../store/modalStore', () => ({
  useModalStore: () => ({}),
}));

function flushMacrotask() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

describe('useAudioImport - restore progress', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('sets uploadProgress > 0 when there is a failed local task', async () => {
    localStorage.setItem(
      'audioUploadTasks',
      JSON.stringify([
        {
          id: 'task-1',
          status: 'failed',
          totalFiles: 2,
          completedFiles: 0,
          failedFiles: 2,
          totalSize: 0,
          files: [
            { name: 'a.wav', status: 'failed', size: 10, uploadedSize: 0, progress: 0 },
            { name: 'b.wav', status: 'failed', size: 10, uploadedSize: 0, progress: 0 },
          ],
        },
      ]),
    );

    const Comp = defineComponent({
      setup() {
        return useAudioImport();
      },
      template: '<div />',
    });

    const wrapper = mount(Comp);

    await nextTick();
    await flushMacrotask();
    await nextTick();

    const vm = wrapper.vm as any;
    expect(vm.currentTask).toBeTruthy();
    expect(vm.currentTask.failedFiles).toBeGreaterThan(0);
    expect(vm.uploadProgress).toBeGreaterThan(0);
  });
});

