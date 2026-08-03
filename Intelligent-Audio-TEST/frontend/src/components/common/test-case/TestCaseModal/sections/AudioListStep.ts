import { computed, inject } from 'vue'
import type { RoundConfigItem, AudioConfig } from '../types'
import type { PlaybackDevice } from '../../../../../shared/types'

export function useAudioListStep(
  props: { round: RoundConfigItem },
  emit: (event: string, ...args: any[]) => void
) {
  // 注入 audioConfig（由 index.vue provide）
  const audioConfig = inject<any>('audioConfig', {})

  const playbackDevices = computed<PlaybackDevice[]>(() => audioConfig?.playbackDevices?.value || [])

  function getAudioDuration(audioId: string | number): number {
    return audioConfig?.getAudioDuration?.(audioId) || 0
  }

  function formatDuration(seconds: number): string {
    return audioConfig?.formatDuration?.(seconds) || '0s'
  }

  const totalDuration = computed(() => {
    let total = 0
    audios.value.forEach(config => {
      if (config.audioId) {
        total += getAudioDuration(config.audioId)
      }
    })
    return total
  })

  // ---- 本地音频列表 ----
  const audios = computed<AudioConfig[]>(() => props.round.audios || [])

  function emitRound(newAudios: AudioConfig[]) {
    emit('update:round', { ...props.round, audios: newAudios })
  }

  // ---- 基础操作 ----
  function addAudio() {
    const list = [...audios.value]
    list.push({ audioId: '', playbackDeviceId: '', spl: 65, playOrder: list.length })
    emitRound(list)
  }

  function removeAudio(index: number) {
    const list = audios.value
      .filter((_, i) => i !== index)
      .map((a, i) => ({ ...a, playOrder: i }))
    emitRound(list)
  }

  function copyAudio(index: number) {
    const source = audios.value[index]
    const list = [...audios.value]
    list.splice(index + 1, 0, { ...source, playOrder: index + 1 })
    list.forEach((a, i) => { a.playOrder = i })
    emitRound(list)
  }

  function updateAudio(index: number, key: keyof AudioConfig, value: unknown) {
    const list = [...audios.value]
    list[index] = { ...list[index], [key]: value }
    emitRound(list)
  }

  function clearAllAudioConfigs() {
    if (audios.value.length > 0 && confirm('确定要清空所有音频配置吗？')) {
      emitRound([])
    }
  }

  // ---- 音频选择 ----
  function openRoundAudioModal(index: number) {
    emit('openAudioSelect', 'dry', (selectedAudios: { id: string; name?: string }[]) => {
      if (selectedAudios.length === 0) return
      const list = [...audios.value]
      // 第一个音频填充当前槽位
      list[index] = { ...list[index], audioId: selectedAudios[0].id }
      // 剩余音频追加为新条目
      for (let i = 1; i < selectedAudios.length; i++) {
        list.push({ audioId: selectedAudios[i].id, playbackDeviceId: '', spl: 65, playOrder: list.length })
      }
      // 重新编号 playOrder
      list.forEach((a, i) => { a.playOrder = i })
      emitRound(list)
    })
  }

  // ---- 试听 ----
  function previewAudio(audioId: string) {
    emit('previewAudio', audioId)
  }

  // ---- 拖拽排序 ----
  const draggedAudioIndex = computed(() => audioConfig?.draggedAudioIndex?.value ?? null)
  const dragOverAudioIndex = computed(() => audioConfig?.dragOverAudioIndex?.value ?? null)

  function handleAudioDragStart(index: number, event: DragEvent) {
    audioConfig?.handleAudioDragStart?.(index, event)
  }

  function handleAudioDragEnd() {
    audioConfig?.handleAudioDragEnd?.()
  }

  function handleAudioDragOver(index: number, event: DragEvent) {
    audioConfig?.handleAudioDragOver?.(index, event)
  }

  function handleAudioDrop(index: number, _event: DragEvent) {
    if (draggedAudioIndex.value === null || draggedAudioIndex.value === index) return
    if (audios.value.length <= 1) return

    const list = [...audios.value]
    const draggedItem = list[draggedAudioIndex.value]
    list.splice(draggedAudioIndex.value, 1)
    list.splice(index, 0, draggedItem)
    list.forEach((a, i) => { a.playOrder = i })
    emitRound(list)

    audioConfig?.handleAudioDragEnd?.()
  }

  // ---- 排序 ----
  function sortByFileName(order: 'asc' | 'desc') {
    if (audios.value.length <= 1) return
    const audioNames: Record<string, string> = {}
    audios.value.forEach(config => {
      if (config.audioId) {
        audioNames[config.audioId] = audioConfig?.getAudioName?.(config.audioId) || ''
      }
    })
    const list = [...audios.value]
    list.sort((a, b) => {
      const nameA = audioNames[a.audioId] || ''
      const nameB = audioNames[b.audioId] || ''
      return order === 'asc' ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA)
    })
    list.forEach((a, i) => { a.playOrder = i })
    emitRound(list)
  }

  function shuffleAudioConfigs() {
    if (audios.value.length <= 1) return
    const list = [...audios.value]
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[list[i], list[j]] = [list[j], list[i]]
    }
    list.forEach((a, i) => { a.playOrder = i })
    emitRound(list)
  }

  // ---- 标签交错 ----
  const showTagSelector = computed(() => audioConfig?.showTagSelector?.value ?? false)
  const selectedTagsForInterleave = computed(() => audioConfig?.selectedTagsForInterleave?.value ?? [])

  function getAudioName(audioId: string | number): string {
    return audioConfig?.getAudioName?.(audioId) || '未知音频'
  }

  function getAudioTags(audioId: string | number): string {
    return audioConfig?.getAudioTags?.(audioId) || ''
  }

  function getNormalizedTags(tagsStr: string): string[] {
    return audioConfig?.getNormalizedTags?.(tagsStr) || []
  }

  const uniqueTags = computed(() => {
    if (!audios.value.length) return []
    const tagSet = new Set<string>()
    audios.value.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId))
        tags.forEach(tag => tagSet.add(tag))
      }
    })
    return Array.from(tagSet)
  })

  function toggleTagSelector() {
    audioConfig?.toggleTagSelector?.()
  }

  function toggleTagSelection(tag: string) {
    audioConfig?.toggleTagSelection?.(tag)
  }

  function interleaveByTags() {
    if (audios.value.length <= 1) return
    const selectedTags = [...selectedTagsForInterleave.value]
    if (selectedTags.length < 2) return

    const matchedConfigs: AudioConfig[] = []
    const unmatchedConfigs: AudioConfig[] = []

    audios.value.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId))
        const hasAnySelectedTag = selectedTags.some(tag => tags.includes(tag))
        if (hasAnySelectedTag) {
          matchedConfigs.push({ ...config })
        } else {
          unmatchedConfigs.push({ ...config })
        }
      } else {
        unmatchedConfigs.push({ ...config })
      }
    })

    if (matchedConfigs.length < 2) return

    const groupedByTag: Record<string, AudioConfig[]> = {}
    selectedTags.forEach(tag => {
      groupedByTag[tag] = matchedConfigs.filter(config => {
        const tags = getNormalizedTags(getAudioTags(config.audioId))
        return tags.includes(tag)
      })
    })

    const maxGroupSize = Math.max(...Object.values(groupedByTag).map(g => g.length))
    const interleaved: AudioConfig[] = []
    const usedIndices = new Set<number>()

    for (let i = 0; i < maxGroupSize; i++) {
      for (const tag of selectedTags) {
        if (i < groupedByTag[tag].length) {
          const config = groupedByTag[tag][i]
          const originalIdx = matchedConfigs.indexOf(config)
          if (!usedIndices.has(originalIdx)) {
            usedIndices.add(originalIdx)
            interleaved.push(config)
          }
        }
      }
    }

    const remainingMatched = matchedConfigs.filter((_, idx) => !usedIndices.has(idx))
    interleaved.push(...remainingMatched)
    interleaved.push(...unmatchedConfigs)

    interleaved.forEach((a, i) => { a.playOrder = i })
    emitRound(interleaved)

    audioConfig?.toggleTagSelector?.()
  }

  // ---- 标签-设备映射 ----
  const showTagDeviceSelector = computed(() => audioConfig?.showTagDeviceSelector?.value ?? false)
  const hasValidTagDeviceMapping = computed(() => audioConfig?.hasValidTagDeviceMapping?.value ?? false)

  function toggleTagDeviceSelector() {
    audioConfig?.toggleTagDeviceSelector?.()
  }

  function getDeviceForTag(tag: string): string {
    return audioConfig?.getDeviceForTag?.(tag) || ''
  }

  function updateTagDeviceMapping(tag: string, deviceId: string) {
    audioConfig?.updateTagDeviceMapping?.(tag, deviceId)
  }

  function getTagAudioCount(tag: string): number {
    if (!audios.value) return 0
    let count = 0
    audios.value.forEach(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId))
        if (tags.includes(tag)) count++
      }
    })
    return count
  }

  function assignDeviceByTags() {
    if (!hasValidTagDeviceMapping.value || !audios.value.length) return

    const list = audios.value.map(config => {
      if (config.audioId) {
        const tags = getNormalizedTags(getAudioTags(config.audioId))
        const matchedTag = tags.find(tag => audioConfig?.getDeviceForTag?.(tag))
        if (matchedTag) {
          const deviceId = audioConfig?.getDeviceForTag?.(matchedTag)
          if (deviceId) {
            return { ...config, playbackDeviceId: deviceId }
          }
        }
      }
      return { ...config }
    })
    emitRound(list)
    audioConfig?.toggleTagDeviceSelector?.()
  }

  return {
    audios,
    formatDuration,
    totalDuration,
    sortByFileName,
    shuffleAudioConfigs,
    toggleTagSelector,
    toggleTagDeviceSelector,
    showTagSelector,
    uniqueTags,
    selectedTagsForInterleave,
    toggleTagSelection,
    interleaveByTags,
    showTagDeviceSelector,
    getDeviceForTag,
    updateTagDeviceMapping,
    playbackDevices,
    getTagAudioCount,
    hasValidTagDeviceMapping,
    assignDeviceByTags,
    addAudio,
    draggedAudioIndex,
    dragOverAudioIndex,
    handleAudioDragStart,
    handleAudioDragEnd,
    handleAudioDragOver,
    handleAudioDrop,
    getAudioName,
    getAudioDuration,
    getAudioTags,
    getNormalizedTags,
    copyAudio,
    removeAudio,
    openRoundAudioModal,
    previewAudio,
    updateAudio,
    clearAllAudioConfigs
  }
}
