import { reactive, ref, type Ref } from 'vue';
import { audiosApi } from '../../utils/api';
import { getModalManager } from '../../utils/modalManager';
import { MODAL_TYPES } from '../../shared/types';
import type { AudioInfo, APIResponse } from '../../shared/types';

/**
 * 音频批量操作和单文件操作组合式函数
 *
 * 职责：
 * - 批量删除/导出
 * - 单文件删除/下载/分享
 * - 编辑元数据
 * - 音频预览
 * - 转换音频格式
 */

export function useAudioBatchOps(
  audioList: Ref<AudioInfo[]>,
  selectedAudios: Ref<(string | number)[]>,
  onRefresh: () => void
) {
  const modalManager = getModalManager();

  const showConvertModal = ref(false);
  const showAudioPlayerModal = ref(false);
  const audioTitle = ref('');
  const currentPreviewAudioId = ref<string | number | null>(null);
  const currentPreviewAudioType = ref<'dry' | 'noise' | 'prompt' | 'mixed'>('dry');

  const urlImportData = reactive({
    url: '',
    type: 'dry' as 'dry' | 'noise' | 'prompt' | 'mixed',
    tags: [] as string[]
  });

  const convertAudioInfo = reactive({
    id: '' as string | number,
    name: '',
    originalFileName: '',
    originalFormat: '',
    originalSampleRate: '',
    originalChannels: '',
    originalBitDepth: '',
    targetFormat: 'wav',
    targetSampleRate: '44100',
    targetChannels: '1',
    targetBitDepth: '16'
  });

  // ========== 批量操作 ==========

  async function batchDelete() {
    if (selectedAudios.value.length === 0) return;

    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '批量删除',
      content: `确定要删除选中的 ${selectedAudios.value.length} 个音频吗？此操作不可撤销。`,
      danger: true
    });

    if (confirmed) {
      try {
        const response = await audiosApi.batchAction('delete', selectedAudios.value, {}, { unwrapResponse: false }) as APIResponse<any>;
        const hasError = response.message && (response.message.includes('失败') || response.message.includes('没有可删除') || response.message.includes('被其他资源引用') || response.message.includes('禁止删除'));
        if (response.success && !hasError) {
          selectedAudios.value = [];
          onRefresh();
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除成功',
            content: response.message || `成功删除音频`,
            danger: false
          });
        } else {
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除失败',
            content: response.message || '部分文件删除失败',
            danger: true
          });
        }
      } catch (e: any) {
        console.error('Batch delete failed:', e);
        await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '删除失败',
          content: e.message || '批量删除失败，请重试',
          danger: true
        });
      }
    }
  }

  async function batchExport() {
    if (selectedAudios.value.length === 0) return;
    try {
      const response = await audiosApi.batchAction('export', selectedAudios.value, {}, { responseType: 'blob' }) as any;
      const url = window.URL.createObjectURL(new Blob([response]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `audios_export_${new Date().getTime()}.zip`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Batch export failed:', e);
    }
  }

  // ========== 单文件操作 ==========

  async function deleteAudio(id: string | number) {
    const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除音频',
      content: '确定要删除这个音频吗？',
      danger: true
    });

    if (confirmed) {
      try {
        const response = await audiosApi.delete(id, { unwrapResponse: false }) as APIResponse;
        const hasError = response.message && (response.message.includes('失败') || response.message.includes('没有可删除') || response.message.includes('被其他资源引用') || response.message.includes('禁止删除'));
        if (response.success && !hasError) {
          onRefresh();
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除成功',
            content: '音频删除成功',
            danger: false
          });
        } else {
          await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '删除失败',
            content: response.message || '音频删除失败',
            danger: true
          });
        }
      } catch (e: any) {
        console.error('Delete audio failed:', e);
        await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '删除失败',
          content: e.message || '音频删除失败，请重试',
          danger: true
        });
      }
    }
  }

  async function downloadAudio(audioOrId: AudioInfo | string | number) {
    let id: string | number;
    let name: string;

    if (typeof audioOrId === 'object') {
      id = audioOrId.id;
      name = audioOrId.name;
    } else {
      id = audioOrId;
      const audio = audioList.value.find(a => a.id === id);
      name = audio ? audio.name : `audio_${id}.wav`;
    }

    try {
      const response = await audiosApi.stream(id, { responseType: 'blob' }) as any;
      const url = window.URL.createObjectURL(new Blob([response]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', name);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Download audio failed:', e);
    }
  }

  function shareAudio(audioOrId: AudioInfo | string | number) {
    let id: string | number;
    if (typeof audioOrId === 'object') {
      id = audioOrId.id;
    } else {
      id = audioOrId;
    }
    console.log('Share audio:', id);
  }

  // ========== 预览 ==========

  function previewAudio(audioOrId: AudioInfo | string | number) {
    let audio: AudioInfo | undefined;
    if (typeof audioOrId === 'object') {
      audio = audioOrId;
    } else {
      audio = audioList.value.find(a => a.id === audioOrId);
    }

    if (audio) {
      audioTitle.value = audio.name;
      currentPreviewAudioId.value = audio.id;
      currentPreviewAudioType.value = audio.audio_type || audio.type || 'dry';
      showAudioPlayerModal.value = true;
    }
  }

  // ========== 元数据编辑 ==========

  function editMetadata(audioOrId: AudioInfo | string | number) {
    let audio: AudioInfo | undefined;
    if (typeof audioOrId === 'object') {
      audio = audioOrId;
    } else {
      audio = audioList.value.find(a => a.id === audioOrId);
    }

    if (audio) {
      let tagsArray: string[] = [];
      if (Array.isArray(audio.tags)) {
        tagsArray = audio.tags;
      } else if (audio.tags) {
        const tagsString = String(audio.tags);
        if (tagsString) {
          tagsArray = tagsString.split(',').map((tag: string) => tag.trim());
        }
      }

      const metadata = {
        id: audio.id,
        fileName: audio.name || '',
        category: audio.filepath || audio.filePath || audio.file_path || '',
        audioType: audio.audio_type || audio.type || 'dry',
        asrText: audio.asr_text || '',
        tags: tagsArray.join(','),
        format: audio.format || '',
        duration: audio.duration || 0,
        sourceLanguage: audio.source_language || '',
        size: audio.size || 0,
        translations: audio.translations || [],
        annotations: audio.annotations || []
      };

      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: '编辑元数据',
        width: '1200px',
        data: metadata,
        fields: [
          { key: 'fileName', label: '文件名' },
          { key: 'audioType', label: '音频类型' },
          { key: 'tags', label: '标签' },
          { key: 'format', label: '音频格式' },
          { key: 'duration', label: '时长(秒)' },
          { key: 'size', label: '文件大小' },
          { key: 'sourceLanguage', label: '源语言' },
          { key: 'asrText', label: 'ASR文本' },
          { key: 'translations', label: '翻译语向' },
          { key: 'annotations', label: '标注' }
        ]
      }).then(async (payload: any) => {
        if (payload && payload.action === 'save') {
          const editedData = payload.data;
          try {
            const response = await audiosApi.updateMetadata(editedData.id, editedData, { unwrapResponse: false }) as any;
            if (response.success) {
              onRefresh();
              await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
                title: '保存成功',
                content: '元数据保存成功',
                danger: false
              });
            } else {
              await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
                title: '保存失败',
                content: response.message || '保存失败',
                danger: true
              });
            }
          } catch (err: any) {
            await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
              title: '保存失败',
              content: err.message || String(err),
              danger: true
            });
          }
        }
      });
    }
  }

  // ========== 转换音频 ==========

  function convertAudio(audioOrEvent?: AudioInfo | any) {
    if (audioOrEvent && (audioOrEvent as AudioInfo).id) {
      const audio = audioOrEvent as AudioInfo;
      convertAudioInfo.id = audio.id;
      convertAudioInfo.name = audio.name;
      convertAudioInfo.originalFileName = audio.filename || '';
      convertAudioInfo.originalFormat = audio.format || '';
      convertAudioInfo.originalSampleRate = (audio.sample_rate || '').toString();
      convertAudioInfo.originalChannels = (audio.channels || '').toString();
      convertAudioInfo.originalBitDepth = '';

      showConvertModal.value = true;
    } else {
      showConvertModal.value = false;
    }
  }

  // ========== 模态框管理 ==========

  function closeModal(modalId?: string) {
    if (modalId === 'convertAudioModal') {
      showConvertModal.value = false;
    } else {
      modalManager.closeAll();
    }
  }

  function closeActiveModal() {
    showConvertModal.value = false;
    showAudioPlayerModal.value = false;
    modalManager.closeAll?.();
  }

  function initModalWatchers() {
    // 兼容占位
  }

  return {
    // 状态
    showConvertModal,
    showAudioPlayerModal,
    audioTitle,
    currentPreviewAudioId,
    currentPreviewAudioType,
    urlImportData,
    convertAudioInfo,
    // 方法
    batchDelete,
    batchExport,
    deleteAudio,
    downloadAudio,
    shareAudio,
    previewAudio,
    editMetadata,
    convertAudio,
    closeModal,
    closeActiveModal,
    initModalWatchers,
  };
}
