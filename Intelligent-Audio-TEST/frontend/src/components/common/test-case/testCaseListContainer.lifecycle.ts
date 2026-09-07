/**
 * TestCaseListContainer —— 数据加载与生命周期模块
 *
 * 职责：算法/维度/播放设备选项加载、全局键盘快捷键（Escape 关闭弹窗）、挂载/卸载钩子。
 */
import { onMounted, onUnmounted, onBeforeUnmount } from 'vue';
import { playbackPort } from '../../../composables/device/playbackPort';
import { algorithmPort } from '../../../composables/algorithm/algorithmPort';
import { evaluationPort } from '../../../composables/evaluation/evaluationPort';
import type { Ref } from 'vue';
import type { ContainerState } from './testCaseListContainer.state';

/** 生命周期模块依赖（来自展开/音频预览/选择模块） */
interface LifecycleModuleDeps {
  /** 滚动哨兵观察器 */
  setupLoadMoreObserver: () => void;
  /** 清理滚动哨兵观察器 */
  cleanupObserver: () => void;
  /** 关闭全部批量菜单 */
  closeAllBatchMenus: () => void;
  /** 音频预览 composable 中供快捷键处理引用的状态/方法 */
  audioPreview: {
    showAudioTypeModal: Ref<boolean>;
    handleCloseAudioTypeModal: () => void;
    showAudioPreviewModal: Ref<boolean>;
    handleAudioPreviewModalClose: () => void;
    showPlaybackDeviceModal: Ref<boolean>;
    showAudioPlayer: Ref<boolean>;
    handleAudioPlayerClose: () => void;
  };
}

/** 创建数据加载与生命周期模块 */
export function createLifecycleModule(props: any, emit: any, state: ContainerState, deps: LifecycleModuleDeps) {
  const { playbackDevices, algorithmOptions, dimensionOptions } = state;
  const {
    setupLoadMoreObserver,
    cleanupObserver,
    closeAllBatchMenus,
    audioPreview
  } = deps;

  // ===== 数据加载 =====
  async function loadAlgorithmOptions() {
    try {
      const data = await algorithmPort.getOptions();
      algorithmOptions.value = [
        { value: 'all', label: '所有算法' },
        ...(data?.algorithms || []).map((algo: any) => ({
          value: algo.value,
          label: algo.name || algo.value
        }))
      ];
    } catch (error) {
      console.error('加载算法选项失败:', error);
      algorithmOptions.value = [
        { value: 'all', label: '所有算法' },
        { value: 'translation', label: '翻译' },
        { value: 'asr', label: 'ASR识别' },
        { value: 'speaker_recognition', label: '说话人识别' },
        { value: 'tts', label: '语音合成' }
      ];
    }
  }

  async function loadDimensionOptions() {
    try {
      const data = await evaluationPort.getOptions();
      dimensionOptions.value = (data?.dimensions || [])
        .filter((d: any) => d.type !== 'sub')
        .map((d: any) => ({ id: d.id, name: d.name }));
    } catch (error) {
      console.error('加载评估维度选项失败:', error);
      dimensionOptions.value = [];
    }
  }

  const loadPlaybackDevices = async () => {
    try {
      // playbackPort.getAll 已展平为 Domain 数组
      playbackDevices.value = await playbackPort.getAll();
    } catch (error) {
      console.error('加载播放设备列表失败:', error);
      playbackDevices.value = [];
    }
  };

  // ===== 键盘快捷键 =====
  const handleGlobalKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      if (audioPreview.showAudioTypeModal.value) {
        audioPreview.handleCloseAudioTypeModal();
      }
      if (audioPreview.showAudioPreviewModal.value) {
        audioPreview.handleAudioPreviewModalClose();
      }
      if (audioPreview.showPlaybackDeviceModal.value) {
        audioPreview.showPlaybackDeviceModal.value = false;
      }
      if (audioPreview.showAudioPlayer.value) {
        audioPreview.handleAudioPlayerClose();
      }
    }
  };

  // ===== 生命周期 =====
  onMounted(() => {
    document.addEventListener('click', closeAllBatchMenus);
    window.addEventListener('keydown', handleGlobalKeyDown);
    setupLoadMoreObserver();
    Promise.all([
      loadPlaybackDevices(),
      loadAlgorithmOptions(),
      loadDimensionOptions()
    ]);
  });

  onUnmounted(() => {
    document.removeEventListener('click', closeAllBatchMenus);
  });

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handleGlobalKeyDown);
    cleanupObserver();
  });

  return {
    loadAlgorithmOptions,
    loadDimensionOptions,
    loadPlaybackDevices,
    handleGlobalKeyDown
  };
}

/** 数据加载与生命周期模块类型（由工厂推断） */
export type LifecycleModule = ReturnType<typeof createLifecycleModule>;