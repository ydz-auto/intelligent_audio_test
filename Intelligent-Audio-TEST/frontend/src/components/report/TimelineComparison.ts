import { ref, computed, watch } from 'vue'

export function useTimelineComparison(props) {
  const selectedResource = ref(null)
  const selectedSpeakers = ref([])
  const scale = ref(1)
  let _wheelTimeout = null
  let _speakerMappingCache = null
  let _speakerMappingCacheKey = null
  const _mockReferenceData = [
    { speaker: 'spk1', start: 0.5, end: 3.2, text: '你好，欢迎光临' },
    { speaker: 'spk1', start: 5.8, end: 8.5, text: '今天天气不错' },
    { speaker: 'spk2', start: 2.8, end: 6.5, text: '请问有什么可以帮您' },
    { speaker: 'spk3', start: 0.0, end: 5.0, text: '我想查询一下订单' },
    { speaker: 'spk3', start: 7.2, end: 9.8, text: '谢谢您的帮助' }
  ]
  const _mockResultData = [
    { speaker: 'spk1', start: 0.6, end: 3.1, text: '你好，欢迎光临' },
    { speaker: 'spk1', start: 5.9, end: 8.4, text: '今天天气不错' },
    { speaker: 'spk2', start: 2.9, end: 6.0, text: '请问有什么可以帮您' },
    { speaker: 'spk3', start: 0.1, end: 4.9, text: '我想查询一下订单' },
    { speaker: 'spk3', start: 7.3, end: 9.7, text: '谢谢您的帮助' },
    { speaker: 'spk4', start: 4.0, end: 5.2, text: '额外检测到的说话' }
  ]

  const isTimelineField = (key) => {
    const timelineKeywords = ['rttm', 'stm', 'segment', 'timeline']
    return timelineKeywords.some(k => key.toLowerCase().includes(k))
  }

  const getTimelineData = (type) => {
    const algoResults = props.algorithmResults || []
    const refParams = props.referenceParams || {}
    const currentSelectedResource = selectedResource.value

    // 从 fieldMapping 获取动态字段名
    const getDynamicKeys = (fieldType) => {
      const fm = props.fieldMapping || {}
      const fields = (fm[fieldType] || []).filter(
        f => ['rttm', 'stm', 'json'].includes(f.param_type)
      )
      return fields.map(f => f.paramCode || f.param_code || f.source_param || f.sourceParam).filter(Boolean);
    }

    const timelineTypes = ['rttm', 'stm', 'json']

    if (type === 'result') {
      // 扁平列表格式：按 device 和 param_type 过滤
      if (!Array.isArray(algoResults)) return []

      let items = algoResults.filter(
        i => timelineTypes.includes(i.param_type)
      )
      if (currentSelectedResource && currentSelectedResource !== 'default') {
        items = items.filter(i => i.device === currentSelectedResource)
      }
      for (const item of items) {
        const parsed = parseTimelineData(item.value)
        if (Array.isArray(parsed) && parsed.length > 0) {
          return [...parsed]
        }
      }
      return []
    }

    if (type === 'reference') {
      // 从 referenceParams 查找
      const dynamicRefKeys = getDynamicKeys('reference')
      const defaultRefKeys = ['stmRef', 'stm_ref', 'rttmRef', 'rttm_ref']
      const refKeys = dynamicRefKeys.length > 0 ? dynamicRefKeys : defaultRefKeys

      for (const key of refKeys) {
        if (refParams[key]) {
          const data = parseTimelineData(refParams[key])
          if (Array.isArray(data) && data.length > 0) {
            return [...data]
          }
        }
      }

      // 如果上面的键都没匹配到，遍历所有 referenceParams 键
      if (dynamicRefKeys.length === 0) {
        for (const [key, value] of Object.entries(refParams)) {
          if (defaultRefKeys.includes(key)) continue
          if (value && typeof value === 'object') {
            const data = parseTimelineData(value)
            if (Array.isArray(data) && data.length > 0) {
              return [...data]
            }
          }
        }
      }
    }

    return []
  }

  const parseTimelineData = (data) => {
    if (!data) return []

    if (Array.isArray(data)) {
      return data
    }

    if (typeof data === 'string') {
      try {
        const parsed = JSON.parse(data)
        if (Array.isArray(parsed)) return parsed
        if (parsed.segments) return parsed.segments
        return parsed
      } catch (e) {
        const rttmResult = parseRttmText(data)
        if (rttmResult.length > 0) return rttmResult
        return parseStmText(data)
      }
    }

    if (typeof data === 'object') {
      if (data.json) {
        if (Array.isArray(data.json)) {
          return data.json
        }
        if (typeof data.json === 'string') {
          try {
            const parsed = JSON.parse(data.json)
            if (Array.isArray(parsed) && parsed.length > 0) return parsed
          } catch (e) {
          }
        }
      }

      if (data.text && typeof data.text === 'string') {
        const rttmResult = parseRttmText(data.text)
        if (rttmResult.length > 0) return rttmResult
        const stmResult = parseStmText(data.text)
        if (stmResult.length > 0) return stmResult
      }

      const stmJson = data.stm_res?.json || data.stmRef?.json || data.stm?.json
      if (stmJson) {
        if (Array.isArray(stmJson)) {
          return stmJson
        }
        if (typeof stmJson === 'string') {
          try {
            const parsed = JSON.parse(stmJson)
            if (Array.isArray(parsed) && parsed.length > 0) return parsed
          } catch (e) {
          }
        }
      }

      // STM text
      const stmText = data.stm_res?.text || data.stmRef?.text || data.stm?.text
      if (stmText && typeof stmText === 'string') {
        const stmResult = parseStmText(stmText)
        if (stmResult.length > 0) {
          return stmResult
        }
      }

      const rttmJson = data.rttm_res?.json || data.rttmRef?.json || data.rttm?.json
      if (rttmJson) {
        if (Array.isArray(rttmJson)) {
          return rttmJson
        }
        if (typeof rttmJson === 'string') {
          try {
            const parsed = JSON.parse(rttmJson)
            if (Array.isArray(parsed) && parsed.length > 0) return parsed
          } catch (e) {
          }
        }
      }

      const rttmText = data.rttm_res?.text || data.rttmRef?.text || data.rttm?.text
      if (rttmText && typeof rttmText === 'string') {
        const rttmResult = parseRttmText(rttmText)
        if (rttmResult.length > 0) {
          return rttmResult
        }
      }

      if (data.json) {
        if (Array.isArray(data.json)) {
          return data.json
        }
        if (typeof data.json === 'string') {
          try {
            const parsed = JSON.parse(data.json)
            if (Array.isArray(parsed) && parsed.length > 0) return parsed
          } catch (e) {
          }
        }
      }

      if (data.text && typeof data.text === 'string') {
        const rttmResult = parseRttmText(data.text)
        if (rttmResult.length > 0) return rttmResult
        return parseStmText(data.text)
      }
    }

    return []
  }

  const parseRttmText = (text) => {
    if (!text || typeof text !== 'string') return []
    const lines = text.split('\n')
    const segments = []

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue

      if (trimmed.startsWith('SPEAKER')) {
        const parts = trimmed.split(/\s+/)
        if (parts.length >= 8) {
          const startTime = parseFloat(parts[3]) || 0
          const duration = parseFloat(parts[4]) || 0
          const segment = {
            speaker: parts[7] || 'spk0',
            start: startTime,
            end: startTime + duration,
            text: ''
          }
          segments.push(segment)
        }
      }
    }

    return segments
  }

  const parseStmText = (text) => {
    if (!text || typeof text !== 'string') return []
    const lines = text.split('\n')
    const segments = []

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue

      if (trimmed.startsWith(';;')) continue

      const parts = trimmed.split(/\s+/)
      if (parts.length >= 6) {
        const startTime = parseFloat(parts[3]) || 0
        const endTime = parseFloat(parts[4]) || 0
        const speaker = parts[2] || 'spk0'

        let textContent = ''
        const angleBracketIdx = parts.findIndex(p => p.startsWith('<'))
        if (angleBracketIdx !== -1 && angleBracketIdx < parts.length - 1) {
          textContent = parts.slice(angleBracketIdx + 1).join(' ').replace(/>\s*$/, '')
        }

        const segment = {
          speaker: speaker,
          start: startTime,
          end: endTime,
          text: textContent
        }
        segments.push(segment)
      }
    }

    return segments
  }

  const computeOverlapTime = (seg1, seg2) => {
    let totalOverlap = 0

    for (const a of seg1) {
      for (const b of seg2) {
        const overlapStart = Math.max(a.start || 0, b.start || 0)
        const overlapEnd = Math.min(a.end || 0, b.end || 0)
        if (overlapEnd > overlapStart) {
          totalOverlap += overlapEnd - overlapStart
        }
      }
    }

    return totalOverlap
  }

  const hungarianAlgorithm = (costMatrix) => {
    const n = costMatrix.length
    if (n === 0) return []

    const m = costMatrix[0].length
    const u = new Array(n + 1).fill(0)
    const v = new Array(m + 1).fill(0)
    const p = new Array(m + 1).fill(0)
    const way = new Array(m + 1).fill(0)

    for (let i = 1; i <= n; i++) {
      p[0] = i
      let j0 = 0
      const minv = new Array(m + 1).fill(Infinity)
      const used = new Array(m + 1).fill(false)

      do {
        used[j0] = true
        const i0 = p[j0]
        let delta = Infinity
        let j1 = 0

        for (let j = 1; j <= m; j++) {
          if (!used[j]) {
            const cur = costMatrix[i0 - 1][j - 1] - u[i0] - v[j]
            if (cur < minv[j]) {
              minv[j] = cur
              way[j] = j0
            }
            if (minv[j] < delta) {
              delta = minv[j]
              j1 = j
            }
          }
        }

        for (let j = 0; j <= m; j++) {
          if (used[j]) {
            u[p[j]] += delta
            v[j] -= delta
          } else {
            minv[j] -= delta
          }
        }

        j0 = j1
      } while (p[j0] !== 0)

      do {
        const j1 = way[j0]
        p[j0] = p[j1]
        j0 = j1
      } while (j0 !== 0)
    }

    const result = new Array(n).fill(-1)
    for (let j = 1; j <= m; j++) {
      if (p[j] !== 0) {
        result[p[j] - 1] = j - 1
      }
    }

    return result
  }

  const computeOptimalSpeakerMapping = (referenceSegments, resultSegments) => {
    const refSpeakers = [...new Set(referenceSegments.map(s => s.speaker || 'spk0'))]
    const resSpeakers = [...new Set(resultSegments.map(s => s.speaker || 'spk0'))]

    if (refSpeakers.length === 0 || resSpeakers.length === 0) {
      return {}
    }

    if (refSpeakers.length === 1 && resSpeakers.length === 1) {
      return { [refSpeakers[0]]: resSpeakers[0] }
    }

    // 预计算每个说话人的片段
    const refSegsMap = {}
    const resSegsMap = {}
    for (const spk of refSpeakers) {
      refSegsMap[spk] = referenceSegments.filter(s => (s.speaker || 'spk0') === spk)
    }
    for (const spk of resSpeakers) {
      resSegsMap[spk] = resultSegments.filter(s => (s.speaker || 'spk0') === spk)
    }

    // 使用贪心算法计算最优匹配
    const overlaps = []
    for (const refSpk of refSpeakers) {
      for (const resSpk of resSpeakers) {
        const overlapTime = computeOverlapTime(refSegsMap[refSpk], resSegsMap[resSpk])
        overlaps.push({ refSpk, resSpk, overlapTime })
      }
    }

    // 按重叠时间降序排序
    overlaps.sort((a, b) => b.overlapTime - a.overlapTime)

    // 贪心选择
    const speakerMapping = {}
    const usedRef = new Set()
    const usedRes = new Set()

    for (const { refSpk, resSpk, overlapTime } of overlaps) {
      if (!usedRef.has(refSpk) && !usedRes.has(resSpk) && overlapTime > 0) {
        speakerMapping[refSpk] = resSpk
        usedRef.add(refSpk)
        usedRes.add(resSpk)
      }
    }

    return speakerMapping
  }

  const cachedReferenceData = computed(() => {
    return getTimelineData('reference')
  })

  const cachedResultData = computed(() => {
    return getTimelineData('result')
  })

  const speakerMapping = computed(() => {
    const refData = cachedReferenceData.value || []
    const resData = cachedResultData.value || []
    const cacheKey = `${refData.length}-${resData.length}-${refData.map(s => s.speaker).join(',')}-${resData.map(s => s.speaker).join(',')}`
    if (_speakerMappingCacheKey === cacheKey && _speakerMappingCache) {
      return _speakerMappingCache
    }
    const mapping = computeOptimalSpeakerMapping(refData, resData)
    _speakerMappingCache = mapping
    _speakerMappingCacheKey = cacheKey
    return mapping
  })

  const maxDuration = computed(() => {
    const refData = getTimelineData('reference')
    const resData = getTimelineData('result')
    const allData = [...refData, ...resData]
    if (allData.length === 0) return 10
    const max = Math.max(...allData.map(s => s.end || 0))
    return Math.ceil(max / 5) * 5 || 10
  })

  const effectiveDuration = computed(() => {
    return maxDuration.value / scale.value
  })

  const timeTicks = computed(() => {
    const duration = effectiveDuration.value
    const ticks = []
    const interval = duration <= 10 ? 2 : (duration <= 30 ? 5 : 10)
    // 不包含起点（i > 0）和终点（i < duration），分别由 .scale-start 和 .scale-end 显示
    for (let i = interval; i < duration; i += interval) {
      ticks.push({
        label: `${i}s`,
        percent: (i / duration) * 100
      })
    }
    return ticks
  })

  const resources = computed(() => {
    // 优先从 results 获取
    const results = props.results || []
    if (results.length > 0) {
      return results.map(r => r.resource)
    }

    // 从 algorithmResults 数组获取唯一设备名
    const algoResults = props.algorithmResults || []
    if (Array.isArray(algoResults) && algoResults.length > 0) {
      const devices = [...new Set(algoResults.map(i => i.device).filter(Boolean))]
      return devices.length > 0 ? devices : ['default']
    }

    return ['default']
  })

  const hasTimelineData = computed(() => {
    const refData = cachedReferenceData.value
    const resData = cachedResultData.value
    return (refData && refData.length > 0) || (resData && resData.length > 0)
  })

  const timelineFields = computed(() => {
    const fields = ['rttm_res', 'stm_res', 'rttm_ref', 'stm_ref', 'rttmRes', 'stmRes', 'rttmRef', 'stmRef']
    const algoType = props.algorithmType?.toLowerCase() || ''
    if (algoType.includes('speaker') || algoType.includes('diarization')) {
      return ['rttm_res', 'stm_res', 'rttmRes', 'stmRes', 'rttm_ref', 'stm_ref', 'rttmRef', 'stmRef']
    }
    return fields
  })

  const speakerList = computed(() => {
    const refData = cachedReferenceData.value
    const resData = cachedResultData.value

    const refSpeakers = []
    const resOnlySpeakers = []

    if (refData && Array.isArray(refData) && refData.length > 0) {
      const uniqueRefSpeakers = [...new Set(refData.map(s => s && s.speaker ? s.speaker : 'spk0'))]
      refSpeakers.push(...uniqueRefSpeakers)
    }

    if (resData && Array.isArray(resData) && resData.length > 0) {
      const uniqueResSpeakers = [...new Set(resData.map(s => s && s.speaker ? s.speaker : 'spk0'))]
      const mappedResSpeakers = new Set(Object.values(speakerMapping.value))
      for (const spk of uniqueResSpeakers) {
        if (!mappedResSpeakers.has(spk)) {
          resOnlySpeakers.push(spk)
        }
      }
    }

    return [...refSpeakers.sort(), ...resOnlySpeakers.sort()]
  })

  const referenceSegmentsBySpeaker = computed(() => {
    const data = cachedReferenceData.value || []
    const grouped = {}
    data.forEach(s => {
      const speaker = s.speaker || 'spk0'
      if (!grouped[speaker]) grouped[speaker] = []
      grouped[speaker].push(s)
    })
    return grouped
  })

  const resultSegmentsBySpeaker = computed(() => {
    const data = cachedResultData.value || []
    const grouped = {}
    data.forEach(s => {
      const speaker = s.speaker || 'spk0'
      if (!grouped[speaker]) grouped[speaker] = []
      grouped[speaker].push(s)
    })
    return grouped
  })

  const getFilteredSpeakerList = () => {
    if (!selectedSpeakers.value || selectedSpeakers.value.length === 0 || selectedSpeakers.value.includes('all')) {
      return speakerList.value
    }
    return speakerList.value.filter(s => selectedSpeakers.value.includes(s))
  }

  const getSegmentStyle = (seg) => {
    const start = seg.start || 0
    const end = seg.end || start + 1
    const duration = end - start
    const maxDur = maxDuration.value / scale.value

    return {
      left: `${(start / maxDur) * 100}%`,
      width: `${Math.max((duration / maxDur) * 100, 3)}%`
    }
  }

  const isMatchSegment = (speaker, seg) => {
    const mappedSpeaker = speakerMapping.value[speaker]
    if (!mappedSpeaker) return false

    const resData = cachedResultData.value || []
    const resSegments = resData.filter(s => (s.speaker || 'spk0') === mappedSpeaker)

    const tolerance = 0.5
    return resSegments.some(resSeg =>
      Math.abs(resSeg.start - seg.start) < tolerance &&
      Math.abs(resSeg.end - seg.end) < tolerance
    )
  }

  const getResultSegmentsForSpeaker = (refSpeaker) => {
    const mappedSpeaker = speakerMapping.value[refSpeaker]
    if (mappedSpeaker) {
      return resultSegmentsBySpeaker.value[mappedSpeaker] || []
    }
    return resultSegmentsBySpeaker.value[refSpeaker] || []
  }

  const handleResourceChange = (event) => {
    selectedResource.value = event.target.value
  }

  const toggleAllSpeakers = (event) => {
    if (event.target.checked) {
      selectedSpeakers.value = []
    }
  }

  const handleWheelZoom = (event) => {
    const factor = event.deltaY > 0 ? (1 / 1.2) : 1.2
    scale.value = Math.max(0.5, Math.min(100, scale.value * factor))
  }

  const zoomIn = () => {
    scale.value = Math.min(100, scale.value * 1.2)
  }

  const zoomOut = () => {
    scale.value = Math.max(0.5, scale.value / 1.2)
  }

  const resetZoom = () => {
    scale.value = 1
  }

  const formatResourceName = (res) => {
    if (!res) return '未知资源'
    if (res.includes('_')) {
      return res.split('_').slice(1).join(' ')
    }
    return res
  }

  // watch
  watch(resources, (newResources) => {
    if (newResources?.length > 0 && !selectedResource.value) {
      selectedResource.value = newResources[0]
    }
  }, { immediate: true })

  return {
    selectedResource,
    selectedSpeakers,
    scale,
    maxDuration,
    effectiveDuration,
    timeTicks,
    resources,
    hasTimelineData,
    timelineFields,
    speakerList,
    cachedReferenceData,
    cachedResultData,
    referenceSegmentsBySpeaker,
    resultSegmentsBySpeaker,
    speakerMapping,
    getFilteredSpeakerList,
    getSegmentStyle,
    isMatchSegment,
    getResultSegmentsForSpeaker,
    handleResourceChange,
    toggleAllSpeakers,
    handleWheelZoom,
    zoomIn,
    zoomOut,
    resetZoom,
    formatResourceName,
    isTimelineField,
    getTimelineData,
    parseTimelineData,
    parseRttmText,
    parseStmText,
    computeOptimalSpeakerMapping,
    computeOverlapTime,
    hungarianAlgorithm
  }
}
