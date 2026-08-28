export function extractInitialTagMetricData(reportData: any) {
  // 添加防御性检查
  if (!reportData) {
    return {};
  }

  // 1. 优先使用后端预计算的 tagMetricData
  const preCalculatedRows = reportData.tag_metric_data || reportData.summary?.tag_metric_data;

  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData = {};
    preCalculatedRows.forEach(row => {
      if (!row) return;
      if (Array.isArray(row.tags)) {
        const resourceKey = row.resource || '0-默认资源';
        row.tags.forEach(t => {
          if (!t) return;
          const tag = t.tag_name || t.tag_id || '未标记';
          if (!mergedData[tag]) mergedData[tag] = {};
          if (!mergedData[tag][resourceKey]) mergedData[tag][resourceKey] = {};
          (t.metrics || []).forEach(m => {
            if (!m || !m.metric) return;
            mergedData[tag][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        });
      } else {
        const tag = row.tag_name || row.tag_id || '未标记';
        const resourceKey = row.resource || '0-默认资源';
        if (!mergedData[tag]) mergedData[tag] = {};
        if (!mergedData[tag][resourceKey]) mergedData[tag][resourceKey] = {};
        if (Array.isArray(row.metrics)) {
          row.metrics.forEach(m => {
            if (!m || !m.metric) return;
            mergedData[tag][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        } else {
          const metricName = row.metric;
          if (!metricName) return;
          mergedData[tag][resourceKey][metricName] = Number(row.value ?? 0);
        }
      }
    });

    const rawRows = reportData.raw_data || reportData.summary?.raw_data || [];
    if (Array.isArray(rawRows) && rawRows.length > 0) {
      const rawMap = {};
      rawRows.forEach(r => {
        if (!r || !r.resource) return;
        if (!rawMap[r.resource]) rawMap[r.resource] = {};
        if (Array.isArray(r.metrics)) {
          r.metrics.forEach(m => {
            if (!m || !m.metric) return;
            rawMap[r.resource][m.metric] = Array.isArray(m.values) ? m.values : [];
          });
        } else if (r.metric) {
          rawMap[r.resource][r.metric] = Array.isArray(r.values) ? r.values : [];
        }
      });

      Object.keys(mergedData).forEach(tag => {
        const resources = mergedData[tag] || {};
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey];
          if (!resourceRawData) return;
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[tag][resourceKey][`${metricName}_raw`] = resourceRawData[metricName];
          });
        });
      });
    }

    return mergedData;
  }

  // 3. Fallback: Reconstruct tagMetricData from reportData.summary.cases
  const cases = reportData.cases || reportData.summary?.cases;
  if (cases && Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseTagComparison] Reconstructing tagMetricData from cases');
    const reconstructedData = {};
    const accumulator = {};

    cases.forEach(caseItem => {
      const rawTags = caseItem.tags;
      const tags = Array.isArray(rawTags) && rawTags.length > 0 ? rawTags : ['未标记'];
      const caseMetrics = caseItem.metrics || {};

      tags.forEach(tag => {
        const tagName = typeof tag === 'string' ? tag : tag.name;
        if (!tagName) return;

        if (!accumulator[tagName]) accumulator[tagName] = {};

        if (Array.isArray(caseMetrics)) {
          caseMetrics.forEach(group => {
            if (!group || !group.resource || !Array.isArray(group.metrics)) return;
            const resourceKey = group.resource;
            if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {};
            group.metrics.forEach(m => {
              if (!m || !m.metric) return;
              const dim = m.metric;
              if (!accumulator[tagName][resourceKey][dim]) {
                accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] };
              }
              const val = m.value;
              if (val !== null && val !== undefined) {
                accumulator[tagName][resourceKey][dim].sum += Number(val);
                accumulator[tagName][resourceKey][dim].count += 1;
                accumulator[tagName][resourceKey][dim].values.push(Number(val));
              }
            });
          });
        } else {
          Object.keys(caseMetrics).forEach(resourceKey => {
            if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {};

            const metrics = caseMetrics[resourceKey];
            Object.keys(metrics).forEach(dim => {
              if (!accumulator[tagName][resourceKey][dim]) {
                accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] };
              }
              const val = metrics[dim];
              if (val !== null && val !== undefined) {
                 accumulator[tagName][resourceKey][dim].sum += Number(val);
                 accumulator[tagName][resourceKey][dim].count += 1;
                 accumulator[tagName][resourceKey][dim].values.push(Number(val));
              }
            });
          });
        }
      });
    });

    // Calculate averages
    Object.keys(accumulator).forEach(tag => {
      reconstructedData[tag] = {};
      Object.keys(accumulator[tag]).forEach(resourceKey => {
        reconstructedData[tag][resourceKey] = {};
        Object.keys(accumulator[tag][resourceKey]).forEach(dim => {
          const stats = accumulator[tag][resourceKey][dim];
          if (stats.count > 0) {
            reconstructedData[tag][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4));
            reconstructedData[tag][resourceKey][`${dim}_raw`] = stats.values;
          } else {
            reconstructedData[tag][resourceKey][dim] = 0;
          }
        });
      });
    });

    return reconstructedData;
  }

  // 2. 如果没有预计算数据，则从 detailed_results 中提取 (原有逻辑)
  const detailedResults = reportData.detailed_results || reportData.summary?.detailed_results || [];
  if (detailedResults && detailedResults.length > 0) {
    const dataAccumulator = {};

    detailedResults.forEach(result => {
      const testCaseId = result.test_case_id;
      let tagObjects = [];
      let tags = [];

      if (result.test_case_tags && result.test_case_tags.length > 0) {
        tagObjects = result.test_case_tags;
        tags = tagObjects.map(tag => tag.name);
      }
      else if (reportData.cases) {
        const testCase = reportData.cases.find(c => c.id === testCaseId);
        if (testCase && testCase.tags) {
          tags = testCase.tags;
          tagObjects = tags.map(tag => ({ id: tag, name: tag }));
        }
      }

      if (result.test_case?.tags && result.test_case.tags.length > 0) {
        tags = result.test_case.tags;
        tagObjects = tags.map(tag => ({ id: tag, name: tag }));
      }

      if (tags.length === 0) {
        if (result.asr?.reference_text) {
          const defaultTag = result.asr.reference_text.slice(0, 5);
          tags = [defaultTag];
          tagObjects = [{ id: defaultTag, name: defaultTag }];
        } else {
          const defaultTag = testCaseId.slice(0, 5);
          tags = [defaultTag];
          tagObjects = [{ id: defaultTag, name: defaultTag }];
        }
      }

      let resourceId = '';
      let resourceName = '';
      if (result.device) {
        resourceId = result.device.id;
        resourceName = result.device.name;
      } else if (result.api) {
        resourceId = result.api.id;
        resourceName = result.api.name;
      } else {
        resourceId = 'default';
        resourceName = '默认资源';
      }

      const resourceKey = `${resourceId}_${resourceName}`;

      tagObjects.forEach(tagObj => {
        const tagName = tagObj.name;

        if (!dataAccumulator[tagName]) {
          dataAccumulator[tagName] = {};
        }
        if (!dataAccumulator[tagName][resourceKey]) {
          dataAccumulator[tagName][resourceKey] = {
            counts: {},
            sums: {},
            values: {}
          };
        }

        if (result.dimension_scores) {
          result.dimension_scores.forEach(dim => {
            if (!dataAccumulator[tagName][resourceKey].counts[dim.dimension_name]) {
              dataAccumulator[tagName][resourceKey].counts[dim.dimension_name] = 0;
              dataAccumulator[tagName][resourceKey].sums[dim.dimension_name] = 0;
              dataAccumulator[tagName][resourceKey].values[dim.dimension_name] = [];
            }

            dataAccumulator[tagName][resourceKey].counts[dim.dimension_name]++;
            dataAccumulator[tagName][resourceKey].sums[dim.dimension_name] += dim.score;
            dataAccumulator[tagName][resourceKey].values[dim.dimension_name].push(dim.score);
          });
        } else if (result.metrics) {
          Object.entries(result.metrics).forEach(([dimName, value]) => {
            if (!dataAccumulator[tagName][resourceKey].counts[dimName]) {
              dataAccumulator[tagName][resourceKey].counts[dimName] = 0;
              dataAccumulator[tagName][resourceKey].sums[dimName] = 0;
              dataAccumulator[tagName][resourceKey].values[dimName] = [];
            }

            dataAccumulator[tagName][resourceKey].counts[dimName]++;
            dataAccumulator[tagName][resourceKey].sums[dimName] += value;
            dataAccumulator[tagName][resourceKey].values[dimName].push(value);
          });
        }
      });
    });

    const extractedTagMetricData = {};

    Object.entries(dataAccumulator).forEach(([tag, resources]) => {
      extractedTagMetricData[tag] = {};

      Object.entries(resources).forEach(([resourceKey, data]) => {
        const resourceName = resourceKey.includes('_') ? resourceKey.split('_').slice(1).join('_') : resourceKey;

        if (!extractedTagMetricData[tag][resourceName]) {
          extractedTagMetricData[tag][resourceName] = {};
        }
        if (!extractedTagMetricData[tag][resourceKey]) {
          extractedTagMetricData[tag][resourceKey] = {};
        }

        Object.entries(data.counts).forEach(([dimName, count]) => {
          const sum = data.sums[dimName];
          const average = count > 0 ? sum / count : 0;

          extractedTagMetricData[tag][resourceName][dimName] = average;
          extractedTagMetricData[tag][resourceKey][dimName] = average;

          extractedTagMetricData[tag][resourceName][`${dimName}_raw`] = data.values[dimName];
          extractedTagMetricData[tag][resourceKey][`${dimName}_raw`] = data.values[dimName];
        });
      });
    });

    return extractedTagMetricData;
  }

  return {};
}

export function computeTagMetricDataFromCases(cases: any, deps: {
  selectedTags: any
  selectedCategories: any
}) {
  const { selectedTags, selectedCategories } = deps
  const selectedTagSet = new Set(selectedTags.value || [])
  const selectedCategorySet = new Set(selectedCategories.value || [])
  const includeUntagged = selectedTagSet.has('无标签') || selectedTagSet.has('未标记')
  selectedTagSet.delete('无标签')
  selectedTagSet.delete('未标记')
  const useTagFilter = selectedTagSet.size > 0 || includeUntagged
  const useCategoryFilter = selectedCategorySet.size > 0

  const accumulator = {}

  ;(cases || []).forEach(caseItem => {
    if (!caseItem) return

    const category = caseItem.category || '未分类'
    if (useCategoryFilter && !selectedCategorySet.has(category)) return

    const caseTagsRaw = caseItem.tags || []
    const caseTagNames = Array.isArray(caseTagsRaw)
      ? caseTagsRaw.map(t => (typeof t === 'object' ? t?.name : t)).filter(Boolean)
      : []

    const tagsToAggregate = useTagFilter
      ? caseTagNames.filter(t => selectedTagSet.has(t))
      : caseTagNames

    if (useTagFilter && includeUntagged && caseTagNames.length === 0) {
      tagsToAggregate.push('未标记')
    }

    if (tagsToAggregate.length === 0) return

    const caseMetrics = caseItem.metrics || {}

    tagsToAggregate.forEach(tagName => {
      if (!accumulator[tagName]) accumulator[tagName] = {}

      if (Array.isArray(caseMetrics)) {
        caseMetrics.forEach(group => {
          if (!group || !group.resource || !Array.isArray(group.metrics)) return
          const resourceKey = group.resource
          if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {}
          group.metrics.forEach(m => {
            if (!m || !m.metric) return
            const dim = m.metric
            if (!accumulator[tagName][resourceKey][dim]) {
              accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] }
            }
            const val = m.value
            if (val !== null && val !== undefined) {
              accumulator[tagName][resourceKey][dim].sum += Number(val)
              accumulator[tagName][resourceKey][dim].count += 1
              accumulator[tagName][resourceKey][dim].values.push(Number(val))
            }
          })
        })
      } else {
        Object.keys(caseMetrics).forEach(resourceKey => {
          if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {}
          const metrics = caseMetrics[resourceKey] || {}
          Object.keys(metrics).forEach(dim => {
            if (!accumulator[tagName][resourceKey][dim]) {
              accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] }
            }
            const val = metrics[dim]
            if (val !== null && val !== undefined) {
              accumulator[tagName][resourceKey][dim].sum += Number(val)
              accumulator[tagName][resourceKey][dim].count += 1
              accumulator[tagName][resourceKey][dim].values.push(Number(val))
            }
          })
        })
      }
    })
  })

  const reconstructedData = {}
  Object.keys(accumulator).forEach(tag => {
    reconstructedData[tag] = {}
    Object.keys(accumulator[tag]).forEach(resourceKey => {
      reconstructedData[tag][resourceKey] = {}
      Object.keys(accumulator[tag][resourceKey]).forEach(dim => {
        const stats = accumulator[tag][resourceKey][dim]
        if (stats.count > 0) {
          reconstructedData[tag][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4))
          reconstructedData[tag][resourceKey][`${dim}_raw`] = stats.values
        } else {
          reconstructedData[tag][resourceKey][dim] = 0
        }
      })
    })
  })

  return reconstructedData
}

export function createTagChartData(deps: {
  activeDisplayType: any
  devices: any
  filteredTags: any
  getRawDataValue: (tag: any, device: any, metricName: any) => any
  getMetricValue: (tag: any, device: any, metricName: any) => any
  getResourceLabel: (key: any) => any
  generateDistributionChartData: any
  chartColors: any
  chartBorderColors: any
}) {
  const {
    activeDisplayType, devices, filteredTags, getRawDataValue, getMetricValue,
    getResourceLabel, generateDistributionChartData, chartColors, chartBorderColors
  } = deps

  const getChartData = (metricName: any) => {
    if (activeDisplayType.value === 'distribution') {
      let allRawData = [];
      const deviceRawDataMap = {};

      devices.value.forEach(device => {
        deviceRawDataMap[device] = [];
      });

      devices.value.forEach(device => {
        const seenArrays = new Set();
        filteredTags.value.forEach(tag => {
          const rawData = getRawDataValue(tag, device, metricName);
          if (seenArrays.has(rawData)) return;
          seenArrays.add(rawData);
          deviceRawDataMap[device] = deviceRawDataMap[device].concat(rawData);
          allRawData = allRawData.concat(rawData);
        });
      });

      allRawData = allRawData.filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v));
      Object.keys(deviceRawDataMap).forEach(device => {
        deviceRawDataMap[device] = deviceRawDataMap[device].filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v));
      });

      return generateDistributionChartData(devices.value, deviceRawDataMap, allRawData, getResourceLabel);
    }

    const chartData = {
      labels: filteredTags.value,
      datasets: devices.value.map((device: any, index: number) => {
        const color = chartColors[index % chartColors.length]
        const borderColor = chartBorderColors[index % chartBorderColors.length]

        const data = filteredTags.value.map((tag: any) => {
          return parseFloat(getMetricValue(tag, device, metricName))
        })

        return {
          label: getResourceLabel(device),
          data: data,
          backgroundColor: color,
          borderColor: borderColor,
          borderWidth: 1
        }
      })
    }

    return chartData
  }

  return { getChartData }
}
