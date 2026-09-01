import { testcasesApi } from '../../utils/api'
import { useNotification } from '../modal/useNotification'
import { TestType, TaskStatus } from '@/shared/types/enums'
import type { TestCase } from '../../shared/types'

/**
 * 测试用例批量操作 composable。
 *
 * 该 composable 接收 testCaseStore 实例作为参数，通过解构获取所需的状态引用与
 * 本地辅助方法（organizeTestCasesByGroup / extractTags / fetchTestCases /
 * handleError），用于在批量操作后同步更新本地状态。所有方法名与返回值
 * 与原 testCaseStore 中的实现保持一致，确保对外接口完全兼容。
 */
export function useTestCaseBatchOps(store: {
  testCases: import('vue').Ref<TestCase[]>
  error: import('vue').Ref<string | null>
  fullGroupsMap: import('vue').Ref<Record<string, import('../shared/types').TestCaseGroup>>
  organizeTestCasesByGroup: () => void
  extractTags: () => void
  fetchTestCases: (params?: Record<string, any>) => Promise<void>
  handleError: (err: any, errorMessage: string) => boolean
}) {
  const notification = useNotification()

  const {
    testCases,
    error,
    fullGroupsMap,
    organizeTestCasesByGroup,
    extractTags,
    fetchTestCases,
    handleError
  } = store

  const batchUpdateAlgorithmParams = async (
    ids: (string | number)[],
    algorithmParams: Record<string, any>,
    options?: { roundMode?: string; roundNumbers?: number[] }
  ) => {
    try {
      error.value = null
      const payload: Record<string, any> = { algorithmParams }
      if (options?.roundMode) payload.round_mode = options.roundMode
      if (options?.roundNumbers) payload.round_numbers = options.roundNumbers
      await testcasesApi.batchAction('update_algorithm_params', ids, payload)

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc) {
          tc.algorithm_params = algorithmParams as any
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量更新用例专属参数失败')
    }
  }

  const batchUpdatePlaybackDevices = async (
    ids: (string | number)[],
    playbackDevices: Record<string, any>,
    options?: { targets?: string[]; roundMode?: string; roundNumbers?: number[] }
  ) => {
    try {
      error.value = null
      const payload: Record<string, any> = { playbackDevices }
      if (options?.targets) payload.targets = options.targets
      if (options?.roundMode) payload.round_mode = options.roundMode
      if (options?.roundNumbers) payload.round_numbers = options.roundNumbers
      await testcasesApi.batchAction('update_playback_devices', ids, payload)

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          const targets = options?.targets || ['audio']
          const deviceId = playbackDevices.deviceId
          // Rounds-based format
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              audios: Array.isArray(round.audios)
                ? round.audios.map((audio: any) => ({
                    ...audio,
                    ...(targets.includes('audio') && deviceId ? { playbackDeviceId: deviceId } : {})
                  }))
                : round.audios
            }))
          }
          // Legacy flat format fallback
          else if (config.audios) {
            ;(config as any).audios = (config as any).audios.map((audio: any) => {
              const audioType = (audio.test_type || '').toLowerCase()
              if (audioType === TestType.E2E) {
                return { ...audio, testType: TestType.E2E, playbackDeviceId: playbackDevices.deviceId }
              }
              return audio
            })
          }
          tc.config = config
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量更新播放设备失败')
    }
  }

  const batchUpdateSPL = async (
    ids: (string | number)[],
    spl: Record<string, any>,
    options?: { targets?: string[]; roundMode?: string; roundNumbers?: number[] }
  ) => {
    try {
      error.value = null
      const payload: Record<string, any> = { spl }
      if (options?.targets) payload.targets = options.targets
      if (options?.roundMode) payload.round_mode = options.roundMode
      if (options?.roundNumbers) payload.round_numbers = options.roundNumbers
      await testcasesApi.batchAction('update_spl', ids, payload)

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          const targets = options?.targets || ['audio']
          const roundMode = options?.roundMode || 'all'
          const roundNumbers = options?.roundNumbers || []
          const splValue = typeof spl === 'object' ? spl.value : spl
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => {
              const rn = round.roundNumber || round.round_number
              if (roundMode === 'specific' && rn && !roundNumbers.includes(rn)) return round
              const newRound = { ...round }
              if (Array.isArray(newRound.audios)) {
                newRound.audios = newRound.audios.map((audio: any) => {
                  const a = { ...audio }
                  if (targets.includes('audio') && splValue !== undefined) {
                    a.spl = splValue
                  }
                  return a
                })
              }
              return newRound
            })
          } else if (config.audios) {
            ;(config as any).audios = (config as any).audios.map((audio: any) => {
              const audioType = (audio.test_type || '').toLowerCase()
              if (audioType === TestType.E2E) {
                return { ...audio, testType: TestType.E2E, spl: spl.value }
              }
              return audio
            })
          }
          tc.config = config
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量更新声压失败')
    }
  }

  const batchMoveCases = async (ids: (string | number)[], groupId: string) => {
    try {
      error.value = null
      await testcasesApi.batchAction('move_to_group', ids, { target_group_id: groupId })

      const group = fullGroupsMap.value[groupId]
      const groupName = group?.name || '未知分组'

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc) {
          tc.group_id = groupId
          tc.group_name = groupName
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量移动用例失败')
    }
  }

  const batchCopyCases = async (ids: (string | number)[], groupId: string) => {
    try {
      error.value = null
      await testcasesApi.batchAction('copy_to_group', ids, { target_group_id: groupId })
      await fetchTestCases()
      return true
    } catch (err: any) {
      return handleError(err, '批量复制用例失败')
    }
  }

  const batchUpdateDimensions = async (
    ids: (string | number)[],
    dimensions: any[],
    testType: string,
    options?: { roundMode?: string; roundNumbers?: number[]; targets?: string[]; roundDimensions?: Record<number, any[]>; multiDimensions?: any[] }
  ) => {
    try {
      error.value = null
      const payload: Record<string, any> = { dimensions, test_type: testType }
      if (options?.roundMode) payload.round_mode = options.roundMode
      if (options?.roundNumbers) payload.round_numbers = options.roundNumbers
      if (options?.targets) payload.targets = options.targets
      if (options?.roundDimensions) payload.round_dimensions = options.roundDimensions
      if (options?.multiDimensions) payload.multi_dimensions = options.multiDimensions
      await testcasesApi.batchAction('update_dimensions', ids, payload)

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          const hasMulti = !!(options?.multiDimensions && options.multiDimensions.length > 0)

          if (options?.roundMode === 'per_round' && options.roundDimensions) {
            // 逐轮设置模式：每个轮次独立设置维度
            if (config.rounds && Array.isArray(config.rounds)) {
              const lastRn = config.rounds.length
              config.rounds = config.rounds.map((round: any) => {
                const rn = round.roundNumber || round.round_number
                // 先查精确轮次，-1 代表最后一轮，按实际轮次数解析
                let roundDims = options.roundDimensions![rn] || []
                if (rn === lastRn && options.roundDimensions![-1]) {
                  // 最后一轮的维度叠加到该轮
                  const lastDims = options.roundDimensions![-1] || []
                  // 合并去重：以 last_round 的配置为准补充
                  const existingIds = new Set(roundDims.map((d: any) => d.id))
                  for (const d of lastDims) {
                    if (!existingIds.has(d.id)) roundDims = [...roundDims, d]
                  }
                }
                return {
                  ...round,
                  evaluation: round.evaluation
                    ? { ...round.evaluation, dimensions: roundDims }
                    : { dimensions: roundDims }
                }
              })
            }
          } else if (dimensions && dimensions.length > 0) {
            // 统一模式
            if (config.rounds && Array.isArray(config.rounds)) {
              const lastRn = config.rounds.length
              config.rounds = config.rounds.map((round: any) => {
                const rn = round.roundNumber || round.round_number
                // 指定轮次模式下只更新选中的轮次（含 -1 = 最后一轮）
                if (options?.roundMode === 'specific' && options.roundNumbers) {
                  const isSelected = options.roundNumbers.includes(rn) ||
                    (rn === lastRn && options.roundNumbers.includes(-1))
                  if (!isSelected) return round
                }
                return {
                  ...round,
                  evaluation: round.evaluation
                    ? { ...round.evaluation, dimensions: dimensions }
                    : { dimensions: dimensions }
                }
              })
            }
          }

          // 多轮整体评估维度：有 multiDimensions 字段就写入（空数组=清空）
          if (options?.multiDimensions !== undefined) {
            config.dimensions = options.multiDimensions
          }

          tc.config = config
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量更新评价维度失败')
    }
  }

  const batchUpdateNoise = async (
    ids: (string | number)[],
    audioId: string,
    spl: number,
    deviceIds: string[],
    options?: { targets?: string[]; roundMode?: string; roundNumbers?: number[] }
  ) => {
    try {
      error.value = null
      const payload: Record<string, any> = {
        noise_audio_id: audioId,
        noise_spl: spl,
        noise_device_ids: deviceIds
      }
      if (options?.targets) payload.targets = options.targets
      if (options?.roundMode) payload.round_mode = options.roundMode
      if (options?.roundNumbers) payload.round_numbers = options.roundNumbers
      await testcasesApi.batchAction('update_noise', ids, payload)

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc) {
          const config = tc.config ? { ...tc.config } : {}
          const noiseConfig = {
            audioId: audioId,
            spl: spl,
            deviceIds: deviceIds,
            loop: false,
          }
          // Rounds-based format: update backgroundNoise in each round
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              backgroundNoise: noiseConfig
            }))
          } else {
            // Legacy flat format
            config.backgroundNoise = { audioId: audioId, spl: spl, deviceIds: deviceIds }
          }
          tc.config = config
        }
      })
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量更新噪声配置失败')
    }
  }

  const batchAutoGenerateName = async (ids: (string | number)[]) => {
    try {
      error.value = null
      await testcasesApi.batchAction('auto_generate_name', ids, {})
      await fetchTestCases()
      return true
    } catch (err: any) {
      return handleError(err, '批量自动生成用例名失败')
    }
  }

  const batchAddTags = async (ids: (string | number)[], newTags: string[]) => {
    try {
      error.value = null
      await testcasesApi.batchAction('add_tags', ids, { tags: newTags })

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc) {
          const existingTagNames = new Set(tc.tags?.map(t => typeof t === 'string' ? t : t.name) || [])
          newTags.forEach(tagName => {
            if (!existingTagNames.has(tagName)) {
              if (!tc.tags) tc.tags = []
              tc.tags.push(tagName as any)
            }
          })
        }
      })
      extractTags()
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量添加标签失败')
    }
  }

  const batchRemoveTags = async (ids: (string | number)[], tagsToRemove: string[]) => {
    try {
      error.value = null
      await testcasesApi.batchAction('remove_tags', ids, { tags: tagsToRemove })

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.tags) {
          tc.tags = tc.tags.filter((tag): tag is string | { id: number; name: string } => {
            const tagName = typeof tag === 'string' ? tag : tag.name
            return !tagsToRemove.includes(tagName)
          }) as typeof tc.tags
        }
      })
      extractTags()
      organizeTestCasesByGroup()
      return true
    } catch (err: any) {
      return handleError(err, '批量移除标签失败')
    }
  }

  const batchRenameTag = async (oldTagName: string, newTagName: string) => {
    try {
      error.value = null
      await testcasesApi.batchAction('rename_tag', [], { old_tag_name: oldTagName, new_tag_name: newTagName })

      testCases.value.forEach(tc => {
        if (tc.tags) {
          tc.tags = tc.tags.map(tag => {
            const tagName = typeof tag === 'string' ? tag : tag.name
            if (tagName === oldTagName) {
              return newTagName as any
            }
            return tag
          })
        }
      })
      extractTags()
      return true
    } catch (err: any) {
      return handleError(err, '重命名标签失败')
    }
  }

  const batchRefreshReference = async (ids: (string | number)[]) => {
    try {
      error.value = null
      const result: any = await testcasesApi.batchAction('refresh_reference', ids, {})
      if (result?.task_id) {
        return { taskId: result.task_id }
      }
      await fetchTestCases()
      return true
    } catch (err: any) {
      return handleError(err, '刷新用例参考失败')
    }
  }

  const pollRefreshTaskStatus = async (taskId: string, onProgress?: (progress: number) => void): Promise<{ success: boolean; updated: number; failed: number }> => {
    return new Promise((resolve) => {
      const poll = async () => {
        try {
          const status: any = await testcasesApi.getRefreshTaskStatus(taskId)

          if (status.status === 'not_found') {
            resolve({ success: false, updated: 0, failed: 0 })
            return
          }

          if (onProgress && typeof status.progress === 'number') {
            onProgress(status.progress)
          }

          if (status.status === TaskStatus.COMPLETED || status.status === TaskStatus.FAILED) {
            resolve({
              success: status.status === TaskStatus.COMPLETED,
              updated: status.updated || 0,
              failed: status.failed || 0
            })
            return
          }

          setTimeout(poll, 1000)
        } catch (err) {
          console.error('[pollRefreshTaskStatus] 查询任务状态失败:', err)
          resolve({ success: false, updated: 0, failed: 0 })
        }
      }

      poll()
    })
  }

  // notification 在原实现中被 batchRefreshReference 等间接路径保留以维持行为一致，
  // 但当前批量操作本身不直接调用 notification，因此这里保留引用以避免被 tree-shake 误删。
  void notification

  const fetchCaseIdsByFilter = async (filters: {
    group?: string
    testType?: string
    search?: string
    tag?: string
    algorithmType?: string
  }): Promise<(string | number)[]> => {
    try {
      const result: any = await testcasesApi.getIdsByFilter(filters)
      return (result as any)?.ids || []
    } catch (err: any) {
      console.error('[fetchCaseIdsByFilter] 获取用例ID失败:', err)
      return []
    }
  }

  return {
    batchUpdateAlgorithmParams,
    batchUpdatePlaybackDevices,
    batchUpdateSPL,
    batchMoveCases,
    batchCopyCases,
    batchUpdateDimensions,
    batchUpdateNoise,
    batchAutoGenerateName,
    batchAddTags,
    batchRemoveTags,
    batchRenameTag,
    batchRefreshReference,
    pollRefreshTaskStatus,
    fetchCaseIdsByFilter
  }
}
