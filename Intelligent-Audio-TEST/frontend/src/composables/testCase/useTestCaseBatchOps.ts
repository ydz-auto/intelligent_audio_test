import { testcasesApi } from '../../utils/api'
import { useNotification } from '../modal/useNotification'
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

  const batchUpdateAlgorithmParams = async (ids: (string | number)[], algorithmParams: Record<string, any>) => {
    try {
      error.value = null
      await testcasesApi.batchAction('update_algorithm_params', ids, { algorithmParams })

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

  const batchUpdatePlaybackDevices = async (ids: (string | number)[], playbackDevices: Record<string, any>) => {
    try {
      error.value = null
      await testcasesApi.batchAction('update_playback_devices', ids, { playbackDevices })

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          // Rounds-based format
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              audios: Array.isArray(round.audios)
                ? round.audios.map((audio: any) => ({
                    ...audio,
                    playbackDeviceId: playbackDevices.deviceId
                  }))
                : round.audios
            }))
          }
          // Legacy flat format fallback
          else if (config.audios) {
            ;(config as any).audios = (config as any).audios.map((audio: any) => {
              const audioType = (audio.testType || audio.test_type || '').toLowerCase()
              if (audioType === 'e2e') {
                return { ...audio, testType: 'e2e', playbackDeviceId: playbackDevices.deviceId }
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

  const batchUpdateSPL = async (ids: (string | number)[], spl: Record<string, any>) => {
    try {
      error.value = null
      await testcasesApi.batchAction('update_spl', ids, { spl })

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              audios: Array.isArray(round.audios)
                ? round.audios.map((audio: any) => ({ ...audio, spl: spl.value }))
                : round.audios
            }))
          } else if (config.audios) {
            ;(config as any).audios = (config as any).audios.map((audio: any) => {
              const audioType = (audio.testType || audio.test_type || '').toLowerCase()
              if (audioType === 'e2e') {
                return { ...audio, testType: 'e2e', spl: spl.value }
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
          tc.groupId = groupId
          tc.groupName = groupName
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

  const batchUpdateDimensions = async (ids: (string | number)[], dimensions: any[], testType: string) => {
    try {
      error.value = null
      await testcasesApi.batchAction('update_dimensions', ids, { dimensions, test_type: testType })

      ids.forEach(id => {
        const tc = testCases.value.find(t => t.id === id)
        if (tc && tc.config) {
          const config = { ...tc.config }
          // Both rounds and legacy formats store dimensions at top level
          config.dimensions = dimensions
          // For rounds format, also update evaluation within each round
          if (config.rounds && Array.isArray(config.rounds)) {
            config.rounds = config.rounds.map((round: any) => ({
              ...round,
              evaluation: round.evaluation
                ? { ...round.evaluation, dimensions: dimensions }
                : { dimensions: dimensions }
            }))
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

  const batchUpdateNoise = async (ids: (string | number)[], audioId: string, spl: number, deviceIds: string[]) => {
    try {
      error.value = null
      await testcasesApi.batchAction('update_noise', ids, { noise_audio_id: audioId, noise_spl: spl, noise_device_ids: deviceIds })

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

          if (status.status === 'completed' || status.status === 'failed') {
            resolve({
              success: status.status === 'completed',
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
    pollRefreshTaskStatus
  }
}
