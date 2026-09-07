/**
 * TestCaseReportDetail —— 时间轴与音频数据子模块
 * 职责：时间轴数据判定（hasTimelineData）、音频列表归一化（audioListWithTimeline）、
 * 音频存在性判定（hasAudio / hasResultAudioData）
 */
import { computed } from 'vue';
import { normalizeAudioItem } from '../../../utils/audioUtils';
import type { TestCaseReportDetailProps } from './testCaseReportDetail.types';
import { FieldType } from '../../../domain/enums';
import { TIMELINE_PARAM_TYPES } from '../../../domain/constants/paramTypeRules';

/**
 * 时间轴与音频数据编排
 */
export function useTestCaseReportDetailTimeline(props: TestCaseReportDetailProps) {
  const hasAudio = computed(() => !!props.audioPath || props.audioList.length > 0);

  // 是否有结果音频
  const hasResultAudioData = computed(() => {
    return Object.keys(props.resultAudios).length > 0;
  });

  const audioListWithTimeline = computed(() => {
    const list = props.audioList || [];
    if (list.length === 0) return [];

    // 只做字段归一化，不再自行计算时间轴位置
    // 后端已根据 overlap_rate/overlap_time 计算好 timelineStart/timelineEnd
    return list.map(a => normalizeAudioItem(a));
  });

  const hasTimelineData = computed(() => {
    // 优先使用 fieldMapping 判断
    if (props.fieldMapping) {
      const hasResultTimeline = (props.fieldMapping.result || []).some(
        f => TIMELINE_PARAM_TYPES.includes(f.paramType ?? '')
      );
      const hasRefTimeline = (props.fieldMapping.reference || []).some(
        f => TIMELINE_PARAM_TYPES.includes(f.paramType ?? '')
      );
      if (hasResultTimeline || hasRefTimeline) return true;
    }

    // 检查 algorithmResults 数组
    const algoResults = props.algorithmResults;
    if (Array.isArray(algoResults)) {
      if (algoResults.some(item => TIMELINE_PARAM_TYPES.includes(item.paramType ?? ''))) {
        return true;
      }
    }

    // 检查 referenceParams 中的时间轴数据（字典键为参数 code 数据 key，原样保留；条目字段为 camelCase）
    const refParams = props.referenceParams;
    if (refParams && typeof refParams === 'object') {
      const timelineKeyPattern = /rttm|stm/i;
      for (const [key, value] of Object.entries(refParams)) {
        if (timelineKeyPattern.test(key) && value) return true;
        if (value && typeof value === 'object' && (value.type === FieldType.RTTM || value.type === FieldType.STM)) return true;
      }
    }

    return false;
  });

  return {
    hasAudio,
    hasResultAudioData,
    audioListWithTimeline,
    hasTimelineData,
  };
}
