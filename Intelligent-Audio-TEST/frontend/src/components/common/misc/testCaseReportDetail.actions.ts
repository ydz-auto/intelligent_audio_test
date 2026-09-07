/**
 * TestCaseReportDetail —— 交互状态与面板控制子模块
 * 职责：维度 tab 状态与越界重置 watch、可展开文本折叠状态、JSON 判定/格式化辅助、
 * 音频播放器（路径音频打开）状态，以及执行结果区的汇总判定（hasExecutionResults）
 */
import { ref, computed, watch, type ComputedRef } from 'vue';
import type {
  PlayingAudio,
  ReferenceTextField,
  ResultFieldGroup,
  ResultTextField,
} from './testCaseReportDetail.types';

/** 跨模块依赖上下文（由组合根注入） */
export interface ReportActionsContext {
  /** 结果文本按维度分组（来自 fields 子模块，用于 tab 越界重置） */
  dimResultGroups: ComputedRef<ResultFieldGroup[]>
  /** 动态参考文本字段（来自 fields 子模块） */
  referenceTextFields: ComputedRef<ReferenceTextField[]>
  /** 动态结果文本字段（来自 fields 子模块） */
  resultTextFields: ComputedRef<ResultTextField[]>
  /** 时间轴数据判定（来自 timeline 子模块） */
  hasTimelineData: ComputedRef<boolean>
  /** 音频存在性判定（来自 timeline 子模块） */
  hasAudio: ComputedRef<boolean>
  /** 结果音频存在性判定（来自 timeline 子模块） */
  hasResultAudioData: ComputedRef<boolean>
}

/**
 * 交互状态与面板控制编排
 */
export function useTestCaseReportDetailActions(ctx: ReportActionsContext) {
  // 维度 tab 状态
  const activeDimTab = ref(0);

  watch(ctx.dimResultGroups, (newGroups) => {
    if (activeDimTab.value >= newGroups.length) {
      activeDimTab.value = 0;
    }
  }, { flush: 'post' });

  // 可展开文本折叠状态
  const expandedTexts = ref<Record<string, boolean>>({});

  const toggleText = (key: string) => {
    expandedTexts.value[key] = !expandedTexts.value[key];
  };

  const isJsonString = (val: unknown) => {
    if (val === null || val === undefined) return false;
    if (typeof val === 'object') return true;
    if (typeof val !== 'string') return false;
    const str = val.trim();
    if (!str || (!str.startsWith('{') && !str.startsWith('['))) return false;
    try {
      JSON.parse(str);
      return true;
    } catch (_e) {
      return false;
    }
  };

  const formatJson = (val: unknown) => {
    if (val === null || val === undefined) return '';
    if (typeof val === 'object') return JSON.stringify(val, null, 2);
    if (typeof val !== 'string') return String(val);
    try {
      return JSON.stringify(JSON.parse(val), null, 2);
    } catch (_e) {
      return String(val);
    }
  };

  // 音频播放器（路径音频打开）
  const showAudioModal = ref(false);
  const currentPlayingAudio = ref<PlayingAudio | null>(null);

  const openPathAudio = (path: string) => {
    if (!path) return;
    currentPlayingAudio.value = {
      path,
      label: path.split(/[\\/]/).pop() || '音频',
    };
    showAudioModal.value = true;
  };

  const closeAudioModal = () => {
    showAudioModal.value = false;
    currentPlayingAudio.value = null;
  };

  // 是否有任何执行结果数据（文本、时间轴、音频、结果音频）
  const hasExecutionResults = computed(() => {
    // 动态文本字段（来自 fieldMapping 或 algorithmResults/referenceParams）
    if (ctx.referenceTextFields.value.length > 0 || ctx.resultTextFields.value.length > 0) return true;
    // 时间轴数据
    if (ctx.hasTimelineData.value) return true;
    // 音频数据
    if (ctx.hasAudio.value) return true;
    // 结果音频
    if (ctx.hasResultAudioData.value) return true;
    return false;
  });

  return {
    // 执行结果面板
    hasExecutionResults,
    // 维度 tab
    activeDimTab,
    // JSON 辅助
    isJsonString,
    formatJson,
    // 文本折叠
    expandedTexts,
    toggleText,
    // 音频播放器
    showAudioModal,
    currentPlayingAudio,
    openPathAudio,
    closeAudioModal,
  };
}
