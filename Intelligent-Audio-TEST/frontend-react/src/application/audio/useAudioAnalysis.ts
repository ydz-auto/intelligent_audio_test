/**
 * 音频特征分析 / 质量评估 / 处理操作 query+mutation hooks（application 层；16_设备域.md §6.23）。
 * queryKey 前缀 ['audio-features', id] / ['audio-quality', id]；处理成功后
 * invalidate 音频列表（§5.3）与本次音频的分析结果（overwrite 会改写原文件，值需重算）。
 *
 * retry: false —— 端点失败（如特征分析 400 / 音频不存在 404）须尽快落到错误态 + 重试钮，
 * 不能靠 React Query 默认 3 次退避拖延（§6.23 三态口径：加载中 / 失败 / 正常值）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getAudioFeatures,
  getAudioQuality,
  processAudio,
} from '@/infrastructure/api/audios-api'
import type { AudioProcessRequest, AudioProcessResult } from '@/domain/models/audio'

/** 特征分析（GET /audios/{id}/features）；enabled=false 时不发请求（弹窗关闭） */
export function useAudioFeatures(audioId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['audio-features', audioId],
    queryFn: () => getAudioFeatures(audioId as number),
    enabled: enabled && audioId != null,
    retry: false,
    staleTime: 60_000,
  })
}

/** 质量评估（GET /audios/{id}/quality） */
export function useAudioQuality(audioId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['audio-quality', audioId],
    queryFn: () => getAudioQuality(audioId as number),
    enabled: enabled && audioId != null,
    retry: false,
    staleTime: 60_000,
  })
}

/** 处理操作（POST /audios/{id}/process；成功即列表与分析结果失效重取） */
export function useAudioProcess() {
  const queryClient = useQueryClient()

  return useMutation<AudioProcessResult, Error, { id: number; payload: AudioProcessRequest }>({
    mutationFn: ({ id, payload }) => processAudio(id, payload),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['audios'] })
      void queryClient.invalidateQueries({ queryKey: ['audio-features', variables.id] })
      void queryClient.invalidateQueries({ queryKey: ['audio-quality', variables.id] })
    },
  })
}
