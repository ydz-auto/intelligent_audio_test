import { reactive, ref, type Ref } from 'vue';
import { audiosPort } from './audiosPort';
import { getModalManager } from '../../utils/modalManager';
import { downloadBlob } from '../../utils/utils';
import { MODAL_TYPES } from '../modal/constants';
import type { AudioInfo, APIResponse } from '../../domain';
import { canEditResource } from '../visibility/useVisibility';
import { toUserErrorMessage } from '../../utils/errorMessage';

/** 删除请求超时上限（毫秒）。后端 OSS 删除偶发阻塞超过网关 60s gRPC 截止
 *  （INT-1332），前端在确认后给出加载态，并在该时限内反馈超时/错误，
 *  避免 UI 无反馈挂起约 60s。 */
export const DELETE_REQUEST_TIMEOUT_MS = 20000;

/** 是否删除超时（本地计时 / fetch 中止 / 后端 DEADLINE_EXCEEDED 透传） */
function isDeleteTimeoutError(e: any): boolean {
  if (!e) return false;
  return (
    e?.isTimeout === true ||
    e?.name === 'AbortError' ||
    /DEADLINE_EXCEEDED|timed?\s?out/i.test(String(e?.message || ''))
  );
}

/** 给请求加本地超时：到期本地 reject（浏览器 fetch 由 signal 中止连接；
 *  Electron IPC 通道不支持 signal，计时兜底）。非 Promise 输入（测试桩）
 *  直接透传，避免悬挂计时器。 */
function withRequestTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  if (!promise || typeof promise.then !== 'function') {
    return Promise.resolve(promise as T);
  }
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      const err: any = new Error(`请求超时（${Math.round(ms / 1000)} 秒未响应）`);
      err.isTimeout = true;
      reject(err);
    }, ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); }
    );
  });
}

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

  // ========== 删除加载态（INT-1332） ==========
  // 行内单删进行中的音频 id（行删除按钮显示加载态并禁用，防重复并发删除同一行）
  const deletingIds = ref<(string | number)[]>([]);
  // 批量删除进行中（页头「批量删除」按钮显示加载态并禁用）
  const batchDeleting = ref(false);

  function isDeleting(id: string | number): boolean {
    return deletingIds.value.includes(id);
  }

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

  async function batchDelete(options: { skipConfirm?: boolean } = {}) {
    if (selectedAudios.value.length === 0) return;
    // 批量删除进行中忽略重复点击（配合页头按钮加载态禁用）
    if (batchDeleting.value) return;

    if (!options.skipConfirm) {
      const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '批量删除',
        content: `确定要删除选中的 ${selectedAudios.value.length} 个音频吗？此操作不可撤销。`,
        danger: true
      });
      if (!confirmed) return;
    }

    batchDeleting.value = true;
    try {
      // 单次调用内循环重试（INT-1332 返工）：批量删除加载态在整个重试窗口保持，
      // 直到成功 / 取消后才由外层 finally 统一清除一次——重试期间按钮保持加载态禁用、
      // 并发点击被 batchDeleting 守卫拦截（不再用递归重入，避免外层 finally 提前清态）。
      while (true) {
        const controller = new AbortController();
        const abortTimer = setTimeout(() => controller.abort(), DELETE_REQUEST_TIMEOUT_MS);
        try {
          const response = await withRequestTimeout(
            audiosPort.batchAction('delete', selectedAudios.value, {}, { unwrapResponse: false, signal: controller.signal }) as Promise<APIResponse<any>>,
            DELETE_REQUEST_TIMEOUT_MS
          );
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
              content: toUserErrorMessage(response, '部分文件删除失败'),
              danger: true
            });
          }
          return;
        } catch (e: any) {
          const isTimeout = isDeleteTimeoutError(e);
          // 主动超时中止是可预期流程（已弹窗提示），按 warn 记录避免误报 SEVERE；
          // 其余失败保留 error 日志便于排查（INT-1003/1052 错误路径口径）
          if (isTimeout) {
            console.warn('Batch delete timed out:', e);
          } else {
            console.error('Batch delete failed:', e);
          }
          // 超时/后端截止后刷新列表核对服务端实际状态（后端可能已删除但响应迟到）
          if (isTimeout) onRefresh();
          const retry = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: isTimeout ? '批量删除超时' : '删除失败',
            content: isTimeout
              ? `删除请求超过 ${Math.round(DELETE_REQUEST_TIMEOUT_MS / 1000)} 秒未响应（存储服务繁忙或已超时）。已刷新列表核对状态，若音频仍存在可点击「重试」再次删除。`
              : toUserErrorMessage(e, '批量删除失败，请重试'),
            danger: true,
            confirmText: isTimeout ? '重试' : '确定',
            cancelText: '取消'
          });
          if (retry && isTimeout) {
            continue; // 重试：batchDeleting 保持 true，重新发起请求
          }
          return; // 取消 / 非超时失败：退出，由外层 finally 统一清除加载态
        } finally {
          clearTimeout(abortTimer);
        }
      }
    } finally {
      batchDeleting.value = false;
    }
  }

  async function batchExport() {
    if (selectedAudios.value.length === 0) return;
    try {
      const response = await audiosPort.batchAction('export', selectedAudios.value, {}, { responseType: 'blob' }) as any;
      downloadBlob(new Blob([response]), `audios_export_${new Date().getTime()}.zip`);
    } catch (e) {
      console.error('Batch export failed:', e);
    }
  }

  // ========== 单文件操作 ==========

  async function deleteAudio(id: string | number, options: { skipConfirm?: boolean } = {}) {
    // INT-536：私有音频非 owner（admin 豁免见 canEditResource）前端守卫——
    // 列表入口已按 canEditResource 隐藏，此处兜底拦截绕过 UI 直达的删除调用
    const audio = audioList.value.find(a => a.id === id);
    if (audio && !canEditResource(audio)) {
      await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '无权限',
        content: '该音频为私有资源，仅创建者和管理员可删除',
        danger: true
      });
      return;
    }

    // 同一行删除进行中忽略重复点击（配合行内加载态禁用按钮）
    if (isDeleting(id)) return;

    if (!options.skipConfirm) {
      const confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '删除音频',
        content: '确定要删除这个音频吗？',
        danger: true
      });
      if (!confirmed) return;
    }

    deletingIds.value = [...deletingIds.value, id];
    try {
      // 单次调用内循环重试（INT-1332 返工）：行内加载态在整个重试窗口保持，
      // 直到成功 / 取消后才由外层 finally 统一清除一次——重试期间按钮保持「删除中」禁用、
      // 并发点击被 isDeleting 守卫拦截（不再用递归重入，避免外层 finally 提前清态）。
      while (true) {
        // 超时中止底层请求：浏览器 fetch 走 signal；Electron IPC 通道由 withRequestTimeout 计时兜底
        const controller = new AbortController();
        const abortTimer = setTimeout(() => controller.abort(), DELETE_REQUEST_TIMEOUT_MS);
        try {
          const response = await withRequestTimeout(
            audiosPort.delete(id, { unwrapResponse: false, signal: controller.signal }) as Promise<APIResponse>,
            DELETE_REQUEST_TIMEOUT_MS
          );
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
              content: toUserErrorMessage(response, '音频删除失败，请稍后重试'),
              danger: true
            });
          }
          return;
        } catch (e: any) {
          const isTimeout = isDeleteTimeoutError(e);
          // 主动超时中止是可预期流程（已弹窗提示），按 warn 记录避免误报 SEVERE；
          // 其余失败保留 error 日志便于排查（INT-1003/1052 错误路径口径）
          if (isTimeout) {
            console.warn('Delete audio timed out:', e);
          } else {
            console.error('Delete audio failed:', e);
          }
          // 超时/后端截止后刷新列表核对服务端实际状态（后端可能已删除但响应迟到）
          if (isTimeout) onRefresh();
          const retry = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: isTimeout ? '删除超时' : '删除失败',
            content: isTimeout
              ? `删除请求超过 ${Math.round(DELETE_REQUEST_TIMEOUT_MS / 1000)} 秒未响应（存储服务繁忙或已超时）。已刷新列表核对状态，若该音频仍存在可点击「重试」再次删除。`
              : toUserErrorMessage(e, '音频删除失败，请稍后重试'),
            danger: true,
            confirmText: isTimeout ? '重试' : '确定',
            cancelText: '取消'
          });
          if (retry && isTimeout) {
            continue; // 重试：deletingIds 保持 [id]，重新发起请求
          }
          return; // 取消 / 非超时失败：退出，由外层 finally 统一清除加载态
        } finally {
          clearTimeout(abortTimer);
        }
      }
    } finally {
      deletingIds.value = deletingIds.value.filter(x => x !== id);
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
      // 后端 stream 返回 JSON 预签名 URL（或网关回退路径），下载需二次取字节流；
      // 按 blob 消费 stream 响应会下载到 .json 文件（INT-146 缺陷1）
      const blob = await audiosPort.download(id);
      downloadBlob(blob, name);
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
      // AudioInfo Domain 类型为 camelCase，统一读 audioType（type 为兜底别名）
      audioTitle.value = audio.name;
      currentPreviewAudioId.value = audio.id;
      const t = audio.audioType || audio.type || 'dry';
      currentPreviewAudioType.value = (['dry', 'noise', 'prompt', 'mixed'].includes(t) ? t : 'dry') as 'dry' | 'noise' | 'prompt' | 'mixed';
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
        // 后端 UpdateMetadataRequest/handle_update_metadata 只读 name（PUT /audios/{id}/metadata），
        // 不能用 fileName 作为「文件名」上行 key（INT-1330）
        name: audio.name || '',
        // filepath 为 Domain 契约字段（camelCase 改造后统一为小写 filepath）
        category: audio.filepath || '',
        audioType: audio.audioType || audio.type || 'dry',
        asrText: audio.asrText || '',
        tags: tagsArray.join(','),
        format: audio.format || '',
        duration: audio.duration || 0,
        sourceLanguage: audio.sourceLanguage || '',
        size: audio.size || 0,
        translations: audio.translations || [],
        annotations: audio.annotations || []
      };

      modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
        title: '编辑元数据',
        width: '1200px',
        data: metadata,
        fields: [
          { key: 'name', label: '文件名' },
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
            const response = await audiosPort.updateMetadata(editedData.id, editedData, { unwrapResponse: false }) as any;
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
      convertAudioInfo.originalSampleRate = (audio.sampleRate || '').toString();
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
    // 删除加载态（INT-1332）
    deletingIds,
    batchDeleting,
    isDeleting,
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
