import { ref, computed, watch, onUnmounted } from 'vue'
import { reportsApi } from '../../utils/api'
import { API_CONFIG } from '../../utils/config'
import { useNotification } from '../../composables/modal/useNotification'

export function useSpecificCaseComparison(props: any) {
  // Audio player state
  const showAudioModal = ref(false)
  const currentAudioId = ref<any>(null)
  const currentAudioTitle = ref('')
  const currentAudioTypeLabel = ref('')
  const currentAudioType = ref('api')
  const currentAudioSpl = ref<any>(null)
  const currentAudioPlayOrder = ref<any>(null)
  const currentAudioNoiseSpl = ref<any>(null)
  const currentAudioDeviceName = ref<any>(null)

  const playAudio = (audio: any, typeLabel: string = '', type: string = 'api') => {
    if (!audio || (!audio.id && !audio.url)) return
    currentAudioId.value = audio.id
    currentAudioTitle.value = audio.filename || audio.label || '未知音频'
    currentAudioTypeLabel.value = typeLabel || audio.label || '测试音频'
    currentAudioType.value = type
    currentAudioSpl.value = audio.spl || null
    currentAudioPlayOrder.value = audio.play_order || null
    currentAudioNoiseSpl.value = audio.noise_spl || null
    currentAudioDeviceName.value = audio.device_name || null
    showAudioModal.value = true
  }

  // Collapse state
  const isCollapsed = ref(false)

  // Collapse toggle method
  const toggleCollapse = () => {
    isCollapsed.value = !isCollapsed.value
  }

  const resourceHeaders = computed(() => {
    const data = props.reportData || {}
    return (
      data.resourceHeaders ||
      data.resource_headers ||
      data.summary?.resourceHeaders ||
      data.summary?.resource_headers ||
      []
    )
  })

  const resourceHeaderMap = computed(() => {
    const data = props.reportData || {}
    const headers =
      data.resourceHeaders ||
      data.resource_headers ||
      data.summary?.resourceHeaders ||
      data.summary?.resource_headers ||
      []

    const map: Record<string, string> = {}
    if (Array.isArray(headers)) {
      headers.forEach((h: any) => {
        if (!h) return
        const key = h.key || h.resource
        const label = h.label || h.name || key
        if (key) map[String(key)] = String(label || key)
      })
    }
    return map
  })

  const getResourceLabel = (resourceKey: any) => {
    const key = String(resourceKey ?? '')
    const mapped = resourceHeaderMap.value?.[key]
    if (mapped) return mapped
    return resourceKey
  }

  // Data
  const searchKeyword = ref('')
  const selectedCategories = ref<any[]>([])
  const categorySearchQuery = ref('')
  const categoryPage = ref(1)
  const categoryPageSize = ref(50)

  // 处理标签：如果是对象数组，提取name属性
  const processTags = (tags: any) => {
    if (!tags) return []
    if (!Array.isArray(tags)) return []
    return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
  }

  // 处理类别：如果是对象数组，提取name属性
  const processCategories = (categories: any) => {
    if (!categories) return []
    if (!Array.isArray(categories)) return []
    return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
  }

  const filteredCategoriesForSelection = computed(() => {
    if (!categorySearchQuery.value.trim()) {
      return categories.value
    }
    const query = categorySearchQuery.value.toLowerCase()
    return categories.value.filter((cat: string) => cat.toLowerCase().includes(query))
  })

  const totalCategoryPages = computed(() => Math.ceil(filteredCategoriesForSelection.value.length / categoryPageSize.value) || 1)

  const paginatedCategories = computed(() => {
    const start = (categoryPage.value - 1) * categoryPageSize.value
    const end = start + categoryPageSize.value
    return filteredCategoriesForSelection.value.slice(start, end)
  })

  const selectedTags = ref<any[]>([])
  const selectedMetrics = ref<any[]>([])
  const sortDimension = ref('name')
  const selectedSortMetric = ref('')
  const secondSortMetric = ref('')  // 第二个排序维度（用于多维度排序）
  const sortOrder = ref('asc')
  const expandedCases = ref<any[]>([])
  const pinnedCases = ref<any[]>([])
  const currentCaseDetail = ref<any>(null)
  const casesLoading = ref(false)
  const casesLoadError = ref('')
  const isDownloadingLog = ref(false)
  const downloadingCaseName = ref('')
  const downloadProgress = ref(0)
  const downloadSpeed = ref('')
  const downloadSize = ref('')
  const downloadTotal = ref('')

  // 从reportData中获取数据，优先使用reportData直接提供的数据，然后再使用summary中的数据
  // 注意：二次对比报告中用例分组存储在caseCategories字段中，而不是categories字段中
  const categories = ref<any[]>(processCategories(props.reportData.categories || props.reportData.summary?.categories || props.reportData.summary?.caseCategories))
  const allTags = ref<any[]>(processTags(props.reportData.allTags || props.reportData.summary?.allTags || props.reportData.summary?.allCaseTags))

  // 所有评测维度，确保至少有一个默认维度
  const allMetrics = ref<any[]>(props.reportData.allMetrics || props.reportData.summary?.allMetrics || [])

  // 获取用例数据
  const cases = ref<any[]>([])

  // 计算实际使用的评测维度
  const actualAllMetrics = computed(() => {
    // 优先使用props提供的维度
    let metrics = allMetrics.value || [];

    console.log('actualAllMetrics - allMetrics.value:', allMetrics.value)
    console.log('actualAllMetrics - cases.value:', cases.value)

    // 如果没有提供维度，从cases数据中提取所有维度
    if (metrics.length === 0 && cases.value.length > 0) {
      const dimensionSet = new Set();
      cases.value.forEach((caseItem: any) => {
        console.log('actualAllMetrics - caseItem.metrics:', caseItem.metrics)
        // 支持新的数组格式和旧的对象格式
        const metricsData = caseItem.metrics
        if (Array.isArray(metricsData)) {
          metricsData.forEach((m: any) => {
            if (m && m.metric) {
              dimensionSet.add(m.metric);
            }
          });
        } else if (metricsData && typeof metricsData === 'object') {
          Object.keys(metricsData).forEach(dimName => {
            dimensionSet.add(dimName);
          });
        }
      });

      console.log('actualAllMetrics - dimensionSet:', dimensionSet)

      // 将提取的维度转换为所需格式
      metrics = Array.from(dimensionSet).map(dimName => ({
        name: dimName,
        unit: '%' // 默认单位
      }));
    }

    // 如果仍然没有维度，添加默认维度
    if (metrics.length === 0) {
      metrics = [{ name: 'WER', unit: '%' }];
    }

    const usedMetricNames = new Set()
    const allCases = cases.value || []
    if (allCases.length > 0) {
      allCases.forEach((caseItem: any) => {
        const metricsData = caseItem.metrics
        if (Array.isArray(metricsData)) {
          metricsData.forEach((m: any) => {
            if (m && m.metric && typeof m.value === 'number') {
              usedMetricNames.add(m.metric)
            }
          })
        } else if (metricsData && typeof metricsData === 'object') {
          Object.entries(metricsData).forEach(([metricName, metricValue]) => {
            const n = typeof metricValue === 'number' ? metricValue : Number(metricValue)
            if (Number.isFinite(n)) usedMetricNames.add(metricName)
          })
        }
      })
    }

    if (usedMetricNames.size > 0) {
      metrics = metrics.filter((m: any) => m?.name && usedMetricNames.has(m.name))
      if (metrics.length === 0) {
        metrics = [{ name: 'WER', unit: '%' }]
      }
    }

    console.log('actualAllMetrics - final metrics:', metrics)
    return metrics;
  })

  // 设备/API列表
  // 使用??替代||，并检查数组长度，确保空数组不会被当作有效值
  const getValidResources = (data: any) => {
    const resources = [
      data.resources,
      data.devices,
      data.apis,
      data.summary?.resources,
      data.summary?.apis,
      data.summary?.devices
    ];

    for (const resource of resources) {
      if (Array.isArray(resource) && resource.length > 0) {
        return resource;
      }
    }
    return [];
  };

  const devices = ref<any[]>(getValidResources(props.reportData));

  const normalizeAudioFields = (caseItem: any, taskType: string) => {
    if (!caseItem || typeof caseItem !== 'object') return caseItem
    const normalized = { ...caseItem }

    if (normalized.audios && Array.isArray(normalized.audios) && normalized.audios.length > 0) {
      normalized.audioList = normalized.audios.map((audio: any, idx: number) => {
        let typeLabel = '测试音频'
        const audioType = audio.testType ?? audio.audioType ?? audio.test_type ?? audio.audio_type ?? 'api'
        if (audioType === 'api') {
          typeLabel = 'API测试音频'
        } else if (audioType === 'e2e') {
          typeLabel = 'E2E测试音频'
        } else if (audioType === 'noise') {
          typeLabel = '噪声'
        } else if (audioType === 'dry') {
          typeLabel = '干声'
        }

        return {
          id: audio.id,
          path: audio.url ?? audio.path,
          label: audio.label ?? audio.filename ?? `${typeLabel} ${idx + 1}`,
          type: audioType,
          filename: audio.filename,
          duration: audio.duration,
          spl: audio.spl,
          playOrder: audio.playOrder ?? audio.play_order,
          noiseSpl: audio.noiseSpl ?? audio.noise_spl,
          deviceId: audio.playbackDeviceId ?? audio.deviceId ?? audio.device_id,
          deviceName: audio.playbackDeviceName ?? audio.deviceName ?? audio.device_name
        }
      })
    }

    return normalized
  }

  // 从reportData中提取用例数据
  // 优先级：1. /api/v1/reports/{id}/cases/search API 2. testReportsCases 3. reportData.cases 4. summary.cases 5. detailedResults
  const extractCasesFromReportData = (reportData: any) => {
    // 优先级1: 使用 test_reports_cases 字段（新格式）
    if (reportData.testReportsCases && Array.isArray(reportData.testReportsCases) && reportData.testReportsCases.length > 0) {
      console.log('从 testReportsCases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.testReportsCases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级2: 使用 reportData.cases
    if (reportData.cases && Array.isArray(reportData.cases) && reportData.cases.length > 0) {
      console.log('从 reportData.cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级3: 使用 summary.cases
    if (reportData.summary?.cases && Array.isArray(reportData.summary.cases) && reportData.summary.cases.length > 0) {
      console.log('从 summary.cases 提取用例数据')
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return reportData.summary.cases.map((c: any) => normalizeAudioFields(c, taskType))
    }

    // 优先级4: 使用 detailedResults
    if (reportData.detailedResults && Array.isArray(reportData.detailedResults) && reportData.detailedResults.length > 0) {
      console.log('从 detailedResults 提取用例数据')
      // 从detailedResults中提取数据，构建cases
      const casesMap = new Map();

      reportData.detailedResults.forEach((result: any) => {
        // 兼容后端返回的 test_case_id 格式
        const testCaseId = result.testCaseId ?? result.test_case_id ?? result.testCase?.id;
        const testCaseName = result.testCaseName ?? result.test_case_name ?? result.testCase?.name ?? '未知用例';

        if (!testCaseId) return;

        // 确定资源名称（设备或API）
        let resourceName = '';
        let resourceKey = '';
        if (result.device) {
          resourceName = result.device.name;
          resourceKey = `${result.device.id}_${resourceName}`;
        } else if (result.api) {
          resourceName = result.api.name;
          resourceKey = `${result.api.id}_${resourceName}`;
        } else {
          resourceName = '默认资源';
          resourceKey = `default_${resourceName}`;
        }

        // 初始化或获取caseItem
        let caseItem: any = casesMap.get(testCaseId);
        if (!caseItem) {
          const asrRef = result.asr?.referenceText ?? result.asr?.reference_text ?? ''
          const tranRef = result.translation?.referenceText ?? result.translation?.reference_text ?? ''

          caseItem = {
            id: testCaseId,
            name: testCaseName,
            category: result.testCaseGroup?.name ?? result.test_case_group?.name ?? result.testCaseType ?? result.test_case_type ?? '其他',
            description: result.description || '',
            tags: processTags(result.testCaseTags ?? result.test_case_tags ?? []),
            audios: result.audios ?? [],
            asr: {
              referenceText: asrRef,
              results: {}
            },
            translation: {
              referenceText: tranRef,
              results: {}
            },
            metrics: {},
            results: [],
            logs: result.logs ?? ''
          };
          casesMap.set(testCaseId, caseItem);
        }

        // 更新audios字段
        if ((!caseItem.audios || caseItem.audios.length === 0) && Array.isArray(result.audios) && result.audios.length > 0) {
          caseItem.audios = result.audios;
        }

        // 更新ASR结果
        if (result.asr) {
          caseItem.asr.results[resourceKey] = {text: result.asr.resultText ?? result.asr.result_text ?? '', score: 0};
        }

        // 更新翻译结果
        if (result.translation) {
          caseItem.translation.results[resourceKey] = {text: result.translation.resultText ?? result.translation.result_text ?? '', score: 0};
        }

        // 更新metrics
        if (!caseItem.metrics[resourceKey]) {
          caseItem.metrics[resourceKey] = {};
        }

        // 提取维度得分
        const dimensionScores = result.dimensionScores ?? result.dimension_scores;
        if (Array.isArray(dimensionScores)) {
          dimensionScores.forEach((dim: any) => {
            const dimName = dim.dimensionName ?? dim.dimension_name;
            if (dimName) {
              caseItem.metrics[resourceKey][dimName] = dim.score;
            }
          });
        } else if (result.metrics) {
          // 如果没有dimensionScores，尝试从metrics中获取
          Object.entries(result.metrics).forEach(([dimName, value]) => {
            caseItem.metrics[resourceKey][dimName] = value;
          });
        }

        // 更新results状态
        const createdAt = result.createdAt ?? result.created_at ?? 0;
        if (!Array.isArray(caseItem.results)) {
          caseItem.results = [];
        }
        const existing = caseItem.results.find((r: any) => r.resource === resourceKey);
        const row = { resource: resourceKey, status: result.status || '未知', startTime: createdAt, endTime: createdAt };
        if (existing) {
          Object.assign(existing, row);
        } else {
          caseItem.results.push(row);
        }
      });

      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return Array.from(casesMap.values()).map((c: any) => normalizeAudioFields(c, taskType));
    }

    // 备选方案：使用reportData中的cases或summary中的cases
    if (reportData.cases) {
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return (reportData.cases || []).map((c: any) => normalizeAudioFields(c, taskType));
    } else if (reportData.summary?.cases) {
      const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
      return (reportData.summary.cases || []).map((c: any) => normalizeAudioFields(c, taskType));
    }

    return [];
  };

  const normalizeCasesForUi = (caseItems: any) => {
    const taskType = props.reportData?.taskType || 'all'
    try {
      return (caseItems || []).map((c0: any) => {
        const c = normalizeAudioFields(c0, taskType)
        if (!c || typeof c !== 'object') return c
        const metricsMap = toMetricsMap(c)
        const asrMap = toTextMap(c.asr)
        const tranMap = toTextMap(c.translation)

        const algoResults = c.algorithmResults || c.algorithm_results || c.algorithmResults || []
        const refParams = c.referenceParams || c.reference_params || c.referenceParams || {}

        return {
          ...c,
          metrics: metricsMap,
          asr: c.asr ? { ...c.asr, results: asrMap } : c.asr,
          translation: c.translation ? { ...c.translation, results: tranMap } : c.translation,
          algorithm_results: algoResults,
          algorithmType: c.algorithmType || c.algorithm_type || '',
          reference_params: refParams,
          rttmRes: c.rttmRes,
          stmRes: c.stmRes,
          rttmRef: c.rttmRef,
          stmRef: c.stmRef
        }
      })
    } catch (e) {
      console.error('normalizeCasesForUi error:', e)
      return caseItems || []
    }
  }

  const loadCasesFromApi = async (reportId: any) => {
    casesLoading.value = true
    casesLoadError.value = ''
    try {
      const perPage = 200
      let page = 1
      let pages = 1
      const allItems: any[] = []
      while (page <= pages) {
        const data = await reportsApi.searchCases(reportId, { page, per_page: perPage })
        const items = data?.items || []
        pages = data?.pages || 1
        allItems.push(...items)
        page += 1
        if (allItems.length >= 5000) break
      }
      cases.value = normalizeCasesForUi(allItems)
    } catch (e: any) {
      console.error('加载报告用例失败:', e)
      casesLoadError.value = e?.message || '加载用例失败'
    } finally {
      casesLoading.value = false
    }
  }

  // 初始化时优先调用 API 获取用例数据
  const initializeCases = async () => {
    const reportId = props.reportData?.id || props.reportData?.reportId
    if (reportId) {
      // 优先调用 API
      console.log('优先调用 /api/v1/reports/{id}/cases/search API 获取用例数据')
      await loadCasesFromApi(reportId)
    }

    // 如果 API 返回空数据，尝试从本地数据提取
    if (!cases.value || cases.value.length === 0) {
      console.log('API 返回空数据，尝试从本地数据提取')
      cases.value = extractCasesFromReportData(props.reportData)
    }
  }

  // 页面加载时初始化 —— 由下方 watch immediate 覆盖，不需要单独调用
  // initializeCases() 已移除，避免与 watch immediate 重复调用 search 接口

  const _metricsMapCache = new WeakMap()
  const _textMapCache = new WeakMap()

  function toMetricsMap(caseItem: any) {
    if (!caseItem || typeof caseItem !== 'object') return {}
    if (_metricsMapCache.has(caseItem)) {
      return _metricsMapCache.get(caseItem)
    }
    const metrics = caseItem?.metrics
    let result: any = {}
    if (Array.isArray(metrics)) {
      if (metrics.length > 0 && metrics[0]?.resource) {
        const map: any = {}
        metrics.forEach((group: any) => {
          if (!group || !group.resource) return
          const resource = group.resource
          if (!map[resource]) map[resource] = {}
          if (Array.isArray(group.metrics)) {
            group.metrics.forEach((m: any) => {
              if (!m || !m.metric) return
              map[resource][m.metric] = m.value
            })
          }
        })
        result = map
      } else {
        const flatMap: any = {}
        metrics.forEach((m: any) => {
          if (!m || !m.metric) return
          flatMap[m.metric] = m.value
        })
        result = flatMap
      }
    } else {
      result = metrics || {}
    }
    _metricsMapCache.set(caseItem, result)
    return result
  }

  function toTextMap(objWithResults: any) {
    if (!objWithResults || typeof objWithResults !== 'object') return {}
    if (_textMapCache.has(objWithResults)) {
      return _textMapCache.get(objWithResults)
    }
    const results = objWithResults?.results
    let result: any = {}
    if (Array.isArray(results)) {
      const map: any = {}
      results.forEach((r: any) => {
        if (!r || !r.resource) return
        map[r.resource] = { text: r.text || '' }
      })
      result = map
    } else {
      result = results || {}
    }
    _textMapCache.set(objWithResults, result)
    return result
  }

  // Computed
  const allDevices = computed(() => {
    // 从所有可能的cases数据源中获取设备和API名称
    const allCases = cases.value || []
    if (allCases.length > 0) {
      const resourcesSet = new Set()
      allCases.forEach((caseItem: any) => {
        if (caseItem.asr) {
          const asrMap = toTextMap(caseItem.asr)
          Object.keys(asrMap).forEach(resource => resourcesSet.add(resource))
        }
        if (caseItem.translation) {
          const tranMap = toTextMap(caseItem.translation)
          Object.keys(tranMap).forEach(resource => resourcesSet.add(resource))
        }
        if (caseItem.metrics) {
          const metricsMap = toMetricsMap(caseItem)
          Object.keys(metricsMap).forEach(resource => resourcesSet.add(resource))
        }
      })
      return Array.from(resourcesSet)
    }
    // 如果没有cases，使用devices或resources作为备选
    return devices.value || []
  })

  // Helper function to extract device/API name from resource key
  const getResourceName = (resourceKey: string) => {
    // 如果资源键包含下划线，提取下划线后面的部分作为显示名称
    // 注意：在对比模式下，后端现在返回 TaskName_ResourceName
    if (resourceKey.includes('_')) {
      const parts = resourceKey.split('_');
      if (parts.length >= 2) {
        // 如果是对比报告，显示 "任务名 - 设备名"
        return `${parts[0]} - ${parts.slice(1).join('_')}`;
      }
      return parts.slice(1).join('_');
    }
    return resourceKey;
  }

  const filteredCases = computed(() => {
    // 使用我们新定义的cases.value获取案例数据，否则使用空数组
    const caseData = cases.value || []

    // First, filter cases based on keyword, category, and tags
    let filtered = caseData.filter((caseItem: any) => {
      // Keyword filter
      const keywordMatch = !searchKeyword.value ||
        caseItem.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
        (caseItem.description && caseItem.description.toLowerCase().includes(searchKeyword.value.toLowerCase()))

      // Category filter
      const categoryMatch = selectedCategories.value.length === 0 ||
        selectedCategories.value.includes(caseItem.category)

      // Tag filter - if all tags are selected, match all cases
      const allTagsSelected = selectedTags.value.length === allTags.value.length
      const tagMatch = allTagsSelected || selectedTags.value.length === 0 ||
        selectedTags.value.some(tag => {
          if (!caseItem.tags) return false
          const tagNames = caseItem.tags.map((t: any) => typeof t === 'object' ? t.name : t)
          return tagNames.includes(tag)
        })

      // Metric filter - if all metrics are selected, match all cases
      const allMetricsSelected = selectedMetrics.value.length === actualAllMetrics.value.length
      const metricMatch = allMetricsSelected || selectedMetrics.value.length === 0 ||
        selectedMetrics.value.every(metric => {
          // Check if at least one device has this metric
          const metricsMap = toMetricsMap(caseItem)
          return Object.values(metricsMap).some((deviceMetrics: any) => deviceMetrics && typeof deviceMetrics[metric] === 'number')
        })

      return keywordMatch && categoryMatch && tagMatch && metricMatch
    })

    // Then, sort the filtered cases
    filtered.sort((a: any, b: any) => {
      let aVal: any, bVal: any

      // Determine the value to sort by
      if (sortDimension.value === '评估维度') {
        // Calculate average of the selected metric across devices
        const aMap = toMetricsMap(a)
        const bMap = toMetricsMap(b)
        aVal = Object.values(aMap).reduce((sum: number, metrics: any) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(aMap).length || 1)
        bVal = Object.values(bMap).reduce((sum: number, metrics: any) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(bMap).length || 1)
      } else {
        // Traditional sorting by other dimensions
        switch (sortDimension.value) {
          case 'name':
            aVal = a.name.toLowerCase()
            bVal = b.name.toLowerCase()
            break
          case 'category':
            aVal = (a.category || '').toLowerCase()
            bVal = (b.category || '').toLowerCase()
            break
          case 'tags':
            // Sort by the first tag in alphabetical order
            const aTags = a.tags ? a.tags.map((t: any) => typeof t === 'object' ? t.name : t) : []
            const bTags = b.tags ? b.tags.map((t: any) => typeof t === 'object' ? t.name : t) : []
            aVal = aTags.length > 0 ? aTags[0].toLowerCase() : ''
            bVal = bTags.length > 0 ? bTags[0].toLowerCase() : ''
            break
          case 'createdAt': {
            // 使用startTime作为createdAt的代理
            const aResults = (Array.isArray(a.results) ? a.results : Object.values(a.results || {})) as any[]
            const bResults = (Array.isArray(b.results) ? b.results : Object.values(b.results || {})) as any[]
            aVal = aResults[0]?.startTime || 0
            bVal = bResults[0]?.startTime || 0
            break
          }
          default:
            aVal = 0
            bVal = 0
        }
      }

      // Apply sort order
      if (aVal < bVal) {
        return sortOrder.value === 'asc' ? -1 : 1
      }
      if (aVal > bVal) {
        return sortOrder.value === 'asc' ? 1 : -1
      }
      return 0
    })

    return filtered
  })

  const unpinnedFilteredCases = computed(() => {
    const pinnedIds = new Set((pinnedCases.value || []).map((p: any) => p?.id))
    return (filteredCases.value || []).filter((c: any) => c && !pinnedIds.has(c.id))
  })

  const pageSize = ref(10)
  const currentPage = ref(1)

  const totalPages = computed(() => {
    const total = unpinnedFilteredCases.value.length
    return Math.max(1, Math.ceil(total / pageSize.value))
  })

  watch([unpinnedFilteredCases, pageSize], () => {
    if (currentPage.value > totalPages.value) currentPage.value = totalPages.value
    if (currentPage.value < 1) currentPage.value = 1
  })

  const paginatedCases = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return unpinnedFilteredCases.value.slice(start, start + pageSize.value)
  })

  // 为 TestCaseReportDetail 准备数据
  const prepareComparisonData = (caseItem: any) => {
    const data: any = {}
    const metricsMap = toMetricsMap(caseItem)  // 扁平格式: {WER: 63.0, wer_zh: 0.0}
    const asrMap = toTextMap(caseItem.asr)
    const tranMap = toTextMap(caseItem.translation)

    // 判断 metrics 是否是扁平格式（不在设备分组内）
    const isFlatFormat = !Object.keys(metricsMap).some(k => allDevices.value.includes(k))

    allDevices.value.forEach((device: string) => {
      if (isFlatFormat) {
        // 扁平格式：所有设备共享相同的指标数据
        data[device] = {
          metrics: metricsMap,  // 使用完整的指标对象
          asr: { text: asrMap?.[device]?.text || '-' },
          trans: { text: tranMap?.[device]?.text || '-' }
        }
      } else {
        // 按设备分组的格式
        data[device] = {
          metrics: metricsMap[device] || {},
          asr: { text: asrMap?.[device]?.text || '-' },
          trans: { text: tranMap?.[device]?.text || '-' }
        }
      }
    })
    return data
  }

  /**
   * 从 caseItem 提取 algorithm_results，返回扁平列表格式
   *
   * 新后端格式（report_controller_task.py >= 当前版本）：已经是扁平列表
   * 旧后端格式（快照数据）：dict {resource: {param_key: value}}
   *
   * 返回值：[{device, param_code, param_type, label, value}, ...]
   */
  const getAlgorithmResults = (caseItem: any) => {
    const algoResults = caseItem.algorithm_results || caseItem.algorithmResults;

    // 新格式：已经是扁平列表，直接返回
    if (Array.isArray(algoResults)) {
      return algoResults;
    }

    // 旧格式：dict {resource: {param_key: value}}，转换为扁平列表
    const result: any[] = [];
    const excludedKeys = new Set([
      'evaluation_data', 'eval_data', 'raw_response', 'result_type',
      'error_message', 'status', 'duration', 'adjusted_reference_params',
      'reference_params', 'config'
    ]);

    if (algoResults && typeof algoResults === 'object') {
      for (const [resource, data] of Object.entries(algoResults)) {
        if (data && typeof data === 'object') {
          for (const [paramKey, paramValue] of Object.entries(data as any)) {
            if (paramValue && !excludedKeys.has(paramKey)) {
              result.push({
                device: resource,
                param_code: paramKey,
                param_type: _inferParamType(paramKey),
                label: paramKey,
                value: paramValue
              });
            }
          }
        }
      }
    }

    // 从 caseItem 获取直接的时间轴数据（兼容更旧的数据结构）
    const directKeys = ['rttmRes', 'stmRes', 'rttm_res', 'stm_res', 'rttm_hyp', 'stm_hyp', 'rttmHyp', 'stmHyp'];
    for (const key of directKeys) {
      if (caseItem[key]) {
        result.push({
          device: 'default',
          param_code: key,
          param_type: _inferParamType(key),
          label: key,
          value: caseItem[key]
        });
      }
    }

    return result;
  };

  /**
   * 根据参数键名推断 param_type
   */
  const _inferParamType = (paramKey: string) => {
    const lower = paramKey.toLowerCase();
    if (lower.includes('rttm')) return 'rttm';
    if (lower.includes('stm')) return 'stm';
    if (lower.includes('audio')) return 'audio';
    return 'text';
  };

  const prepareAudioList = (caseItem: any) => {
    const taskType = props.reportData?.taskType || 'all' // 'api', 'e2e' or 'all'

    if (!caseItem.audioList || !Array.isArray(caseItem.audioList) || caseItem.audioList.length === 0) {
      return []
    }

    return caseItem.audioList.filter((audio: any) => {
      if (taskType === 'api') {
        return audio.type === 'api'
      } else if (taskType === 'e2e') {
        return audio.type === 'e2e' || audio.type === 'noise'
      } else {
        return true // all: 显示所有
      }
    })
  }

  const currentCaseDetailWithPreparedData = computed(() => {
    if (!currentCaseDetail.value) return null
    const caseItem = currentCaseDetail.value
    return {
      ...caseItem,
      _preparedComparisonData: prepareComparisonData(caseItem),
      _preparedAudioList: prepareAudioList(caseItem),
      _preparedReferenceAsr: caseItem.asr?.referenceText || caseItem.asr?.reference_text || '',
      _preparedReferenceTrans: caseItem.translation?.referenceText || caseItem.translation?.reference_text || '',
      _preparedAlgorithmResults: getAlgorithmResults(caseItem),
      _preparedReferenceParams: caseItem.referenceParams || caseItem.reference_params || {},
      _preparedAlgorithmType: caseItem.algorithmType || caseItem.algorithm_type || ''
    }
  })

  // Search and pagination for tags
  const tagSearchQuery = ref('')
  const tagPage = ref(1)
  const tagPageSize = ref(50)

  const filteredTags = computed(() => {
    if (!tagSearchQuery.value.trim()) {
      return allTags.value
    }
    const query = tagSearchQuery.value.toLowerCase()
    return allTags.value.filter((tag: string) => tag.toLowerCase().includes(query))
  })

  const totalTagPages = computed(() => Math.ceil(filteredTags.value.length / tagPageSize.value) || 1)

  const paginatedTags = computed(() => {
    const start = (tagPage.value - 1) * tagPageSize.value
    const end = start + tagPageSize.value
    return filteredTags.value.slice(start, end)
  })

  // Search and pagination for metrics
  const metricSearchQuery = ref('')
  const metricPage = ref(1)
  const metricPageSize = ref(30)

  const filteredMetricsForDisplay = computed(() => {
    if (!metricSearchQuery.value.trim()) {
      return actualAllMetrics.value
    }
    const query = metricSearchQuery.value.toLowerCase()
    return actualAllMetrics.value.filter((metric: any) => metric.name.toLowerCase().includes(query))
  })

  const totalMetricPages = computed(() => Math.ceil(filteredMetricsForDisplay.value.length / metricPageSize.value) || 1)

  const paginatedMetrics = computed(() => {
    const start = (metricPage.value - 1) * metricPageSize.value
    const end = start + metricPageSize.value
    return filteredMetricsForDisplay.value.slice(start, end)
  })

  const paginatedCasesWithPreparedData = computed(() => {
    return paginatedCases.value.map((caseItem: any) => ({
      ...caseItem,
      _preparedComparisonData: prepareComparisonData(caseItem),
      _preparedAudioList: prepareAudioList(caseItem),
      _preparedReferenceAsr: caseItem.asr?.referenceText || caseItem.asr?.reference_text || '',
      _preparedReferenceTrans: caseItem.translation?.referenceText || caseItem.translation?.reference_text || '',
      _preparedAlgorithmResults: getAlgorithmResults(caseItem),
      _preparedReferenceParams: caseItem.referenceParams || caseItem.reference_params || {},
      _preparedAlgorithmType: caseItem.algorithmType || caseItem.algorithm_type || ''
    }))
  })

  const handlePrevPage = () => {
    if (currentPage.value > 1) currentPage.value -= 1
  }

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) currentPage.value += 1
  }

  const handleGoToPage = (page: any) => {
    const p = Number(page)
    if (!Number.isFinite(p)) return
    currentPage.value = Math.min(Math.max(1, p), totalPages.value)
  }

  // Methods
  const toggleCaseExpand = (caseId: any) => {
    const index = expandedCases.value.indexOf(caseId)
    if (index > -1) {
      expandedCases.value.splice(index, 1)
      console.log('Case collapsed:', caseId, 'Expanded cases:', expandedCases.value)
    } else {
      expandedCases.value.push(caseId)
      console.log('Case expanded:', caseId, 'Expanded cases:', expandedCases.value)
    }
  }

  const toggleTag = (tag: any) => {
    const index = selectedTags.value.indexOf(tag)
    if (index > -1) {
      selectedTags.value.splice(index, 1)
    } else {
      selectedTags.value.push(tag)
    }
  }

  const toggleCategoryFilter = (category: any) => {
    const index = selectedCategories.value.indexOf(category)
    if (index > -1) {
      selectedCategories.value.splice(index, 1)
    } else {
      selectedCategories.value.push(category)
    }
  }

  const togglePin = (caseId: any) => {
    const caseItem = cases.value.find((c: any) => c.id === caseId) || filteredCases.value.find((c: any) => c.id === caseId)
    if (!caseItem) return

    const pinnedIndex = pinnedCases.value.findIndex((p: any) => p.id === caseId)
    if (pinnedIndex > -1) {
      pinnedCases.value.splice(pinnedIndex, 1)
    } else {
      pinnedCases.value.push(caseItem)
    }
  }

  const openCaseDetail = (caseItem: any) => {
    currentCaseDetail.value = caseItem
  }

  const closeCaseDetail = () => {
    currentCaseDetail.value = null
  }

  // 监听键盘事件，处理 ESC 退出
  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && currentCaseDetail.value) {
      closeCaseDetail();
    }
  };

  watch(() => currentCaseDetail.value, (newVal) => {
    if (newVal) {
      window.addEventListener('keydown', handleKeyDown);
    } else {
      window.removeEventListener('keydown', handleKeyDown);
    }
  }, { immediate: true });

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown);
  });

  const getOverallStatus = (caseItem: any) => {
    const statuses = (Array.isArray(caseItem.results) ? caseItem.results : []).map((r: any) => r.status)
    if (statuses.includes('失败') || statuses.includes('Failed')) return 'failed'
    if (statuses.includes('警告') || statuses.includes('Warning')) return 'warning'
    return 'success'
  }

  const getCaseTaskId = (caseItem: any) => {
    return caseItem.taskId || caseItem.task_id || props.reportData?.taskId || props.reportData?.summary?.taskId || ''
  }

  const copyToClipboard = (text: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        const notification = useNotification()
        notification.success('ID已复制到剪贴板')
      }).catch(() => {
        const notification = useNotification()
        notification.error('复制失败')
      })
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const downloadCaseLogZip = async (caseItem: any) => {
    const notification = useNotification()
    const reportId = props.reportData?.id || props.reportData?.reportId
    if (!reportId) {
      console.error('无法获取报告ID')
      notification.error('无法获取报告ID')
      return
    }

    const caseId = caseItem.id
    if (!caseId) {
      console.error('无法获取用例ID')
      notification.error('无法获取用例ID')
      return
    }

    isDownloadingLog.value = true
    downloadingCaseName.value = caseItem.name || caseId
    downloadProgress.value = 0
    downloadSpeed.value = ''
    downloadSize.value = ''
    downloadTotal.value = ''

    try {
      const downloadUrl = reportsApi.getCaseLogsDownloadUrl(reportId, caseId)
      const response = await fetch(downloadUrl)

      if (!response.ok) {
        let errorMsg = '下载日志失败'
        try {
          const errorData = await response.json()
          errorMsg = errorData?.message || errorData?.detail || errorMsg
        } catch {
          if (response.status === 404) {
            errorMsg = '未找到用例日志目录'
          } else if (response.status === 500) {
            errorMsg = '服务器内部错误'
          }
        }
        notification.error(errorMsg)
        return
      }

      const contentLength = response.headers.get('content-length')
      const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
      downloadTotal.value = formatFileSize(totalBytes)

      if (!response.body) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `case_${caseId}_logs.zip`)
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        notification.success('日志下载成功')
        return
      }

      const reader = response.body.getReader()
      const chunks: any[] = []
      let receivedBytes = 0
      let lastTime = Date.now()
      let lastBytes = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        chunks.push(value)
        receivedBytes += value.length
        downloadSize.value = formatFileSize(receivedBytes)

        if (totalBytes > 0) {
          downloadProgress.value = Math.round((receivedBytes / totalBytes) * 100)
        }

        const now = Date.now()
        const timeDiff = now - lastTime
        if (timeDiff >= 500) {
          const bytesDiff = receivedBytes - lastBytes
          const speed = bytesDiff / (timeDiff / 1000)
          downloadSpeed.value = formatFileSize(speed) + '/s'
          lastTime = now
          lastBytes = receivedBytes
        }
      }

      const blob = new Blob(chunks, { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `case_${caseId}_logs.zip`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      downloadProgress.value = 100
      notification.success('日志下载成功')
    } catch (error: any) {
      console.error('下载日志失败:', error)
      const errorMsg = error?.message || '下载日志失败，请稍后重试'
      notification.error(errorMsg)
    } finally {
      setTimeout(() => {
        isDownloadingLog.value = false
        downloadingCaseName.value = ''
        downloadProgress.value = 0
        downloadSpeed.value = ''
        downloadSize.value = ''
        downloadTotal.value = ''
      }, 500)
    }
  }

  const formatTime = (timestamp: any) => {
    return new Date(timestamp).toLocaleString()
  }

  const toggleMetric = (metricName: any) => {
    const index = selectedMetrics.value.indexOf(metricName)
    if (index > -1) {
      selectedMetrics.value.splice(index, 1)
    } else {
      selectedMetrics.value.push(metricName)
    }
  }

  const resetFilters = () => {
    searchKeyword.value = ''
    selectedCategories.value = []
    categorySearchQuery.value = ''
    categoryPage.value = 1
    selectedTags.value = []
    selectedMetrics.value = []
    sortDimension.value = 'name'
    selectedSortMetric.value = ''
    sortOrder.value = 'asc'
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
  }

  const applyFilters = () => {
    // 这里可以添加筛选逻辑
    console.log('应用筛选:', {
      searchKeyword: searchKeyword.value,
      selectedCategories: selectedCategories.value,
      selectedTags: selectedTags.value,
      selectedMetrics: selectedMetrics.value,
      sortDimension: sortDimension.value,
      selectedSortMetric: selectedSortMetric.value,
      sortOrder: sortOrder.value
    })
  }

  watch(actualAllMetrics, (newMetrics: any) => {
    const names = (newMetrics || []).map((m: any) => m?.name).filter(Boolean)
    if (selectedMetrics.value.length > 0) {
      selectedMetrics.value = selectedMetrics.value.filter((n: any) => names.includes(n))
    }
    if (selectedSortMetric.value && !names.includes(selectedSortMetric.value)) {
      selectedSortMetric.value = ''
    }
  }, { immediate: true })

  // 调试信息：确保cases数据被正确获取
  console.log('SpecificCaseComparisonComponent - reportData:', props.reportData)
  console.log('SpecificCaseComparisonComponent - cases:', cases.value)
  console.log('SpecificCaseComparisonComponent - caseItem.metrics sample:', cases.value.length > 0 ? JSON.stringify(Object.values(cases.value[0].metrics || {})) : 'no cases')
  console.log('SpecificCaseComparisonComponent - actualAllMetrics:', actualAllMetrics.value)
  console.log('SpecificCaseComparisonComponent - devices:', devices.value)

  // 防止同一 reportId 重复加载
  let loadedReportId: any = null

  // 监听reportData变化，更新内部状态
  watch([
    () => props.reportData?.id,
    () => props.reportData?.reportId,
    () => props.reportData?.cases?.length,
    () => props.reportData?.testReportsCases?.length,
    () => props.reportData?.summary?.cases?.length
  ], async ([id, reportId, casesLen, testReportsCasesLen, summaryCasesLen]: any, [oldId, oldReportId]: any) => {
    const newReportData = props.reportData

    categories.value = processCategories(newReportData.categories || newReportData.summary?.categories || newReportData.summary?.caseCategories)
    allTags.value = processTags(newReportData.allTags || newReportData.summary?.allTags || newReportData.summary?.allCaseTags)
    allMetrics.value = newReportData.allMetrics || newReportData.summary?.allMetrics || []
    devices.value = getValidResources(newReportData);

    const effectiveReportId = id || reportId
    if (effectiveReportId) {
      // 只有在 id 变化时才重新加载用例数据，且跳过已加载过的 reportId
      if (effectiveReportId !== loadedReportId && effectiveReportId !== oldId && effectiveReportId !== oldReportId) {
        loadedReportId = effectiveReportId
        console.log('watch: 优先调用 /api/v1/reports/{id}/cases/search API 获取用例数据')
        await loadCasesFromApi(effectiveReportId)

        // 如果 API 返回空数据，尝试从本地数据提取
        if (!cases.value || cases.value.length === 0) {
          console.log('watch: API 返回空数据，尝试从本地数据提取')
          cases.value = extractCasesFromReportData(newReportData)
        }
      }
    } else {
      cases.value = extractCasesFromReportData(newReportData)
    }

    // 重置选中状态：默认不选中任何标签/维度（显示全部）
    selectedTags.value = []
    selectedMetrics.value = []
    selectedCategories.value = []
    categorySearchQuery.value = ''
    categoryPage.value = 1
    tagSearchQuery.value = ''
    tagPage.value = 1
    metricSearchQuery.value = ''
    metricPage.value = 1
  }, { immediate: true })

  return {
    // Audio player state
    showAudioModal,
    currentAudioId,
    currentAudioTitle,
    currentAudioTypeLabel,
    currentAudioType,
    currentAudioSpl,
    currentAudioPlayOrder,
    currentAudioNoiseSpl,
    currentAudioDeviceName,
    playAudio,
    // Collapse
    isCollapsed,
    toggleCollapse,
    // Loading state
    casesLoading,
    casesLoadError,
    // Filter - search
    searchKeyword,
    // Filter - categories
    selectedCategories,
    categorySearchQuery,
    paginatedCategories,
    toggleCategoryFilter,
    filteredCategoriesForSelection,
    categoryPage,
    categoryPageSize,
    totalCategoryPages,
    // Filter - tags
    selectedTags,
    tagSearchQuery,
    paginatedTags,
    toggleTag,
    filteredTags,
    tagPage,
    tagPageSize,
    totalTagPages,
    // Filter - metrics
    selectedMetrics,
    metricSearchQuery,
    paginatedMetrics,
    toggleMetric,
    filteredMetricsForDisplay,
    metricPage,
    metricPageSize,
    totalMetricPages,
    // Sort
    sortDimension,
    selectedSortMetric,
    secondSortMetric,
    sortOrder,
    actualAllMetrics,
    // Filter actions
    resetFilters,
    applyFilters,
    // Pinned cases
    pinnedCases,
    togglePin,
    // Resource labels
    getResourceLabel,
    resourceHeaders,
    // Case list
    paginatedCasesWithPreparedData,
    toggleCaseExpand,
    getOverallStatus,
    copyToClipboard,
    downloadCaseLogZip,
    expandedCases,
    allDevices,
    // Pagination
    unpinnedFilteredCases,
    currentPage,
    pageSize,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    // Case detail modal
    currentCaseDetailWithPreparedData,
    closeCaseDetail,
    openCaseDetail,
    // Misc methods
    getResourceName,
    getCaseTaskId,
    formatTime,
    // Download state
    isDownloadingLog,
    downloadingCaseName,
    downloadProgress,
    downloadSpeed,
    downloadSize,
    downloadTotal
  }
}
