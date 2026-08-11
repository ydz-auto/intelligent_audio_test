export function extractInitialMetricData(reportData: any) {
  // 1. 优先使用后端预计算的 metricData
  const preCalculatedRows = reportData.metricData || reportData.summary?.metricData ||
                           reportData.metric_data || reportData.summary?.metric_data;

  // 处理 dict 格式: {category: {resource: {metric: value}}}
  if (preCalculatedRows && !Array.isArray(preCalculatedRows) && typeof preCalculatedRows === 'object') {
    const mergedData = {};
    Object.keys(preCalculatedRows).forEach(category => {
      const resData = preCalculatedRows[category];
      if (!resData || typeof resData !== 'object') return;
      mergedData[category] = {};
      Object.keys(resData).forEach(resourceKey => {
        const metrics = resData[resourceKey];
        if (!metrics || typeof metrics !== 'object') return;
        mergedData[category][resourceKey] = {};
        Object.keys(metrics).forEach(metricName => {
          mergedData[category][resourceKey][metricName] = Number(metrics[metricName] ?? 0);
        });
      });
    });

    const rawRows = reportData.rawData || reportData.summary?.rawData ||
                   reportData.raw_data || reportData.summary?.raw_data;
    if (rawRows && !Array.isArray(rawRows) && typeof rawRows === 'object') {
      Object.keys(mergedData).forEach(category => {
        const resources = mergedData[category] || {};
        Object.keys(resources).forEach(resourceKey => {
          const resourceObj = resources[resourceKey];
          if (!resourceObj || typeof resourceObj !== 'object') return;
          const resourceRawData = rawRows[resourceKey];
          if (!resourceRawData || typeof resourceRawData !== 'object') return;
          Object.keys(resourceRawData).forEach(key => {
            resourceObj[`${key}`] = resourceRawData[key];
          });
        });
      });
    }

    return mergedData;
  }

  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData = {};
    preCalculatedRows.forEach(row => {
      if (!row) return;
      if (Array.isArray(row.categories)) {
        const resourceKey = row.resource || '0-默认资源';
        row.categories.forEach(c => {
          if (!c) return;
          const category = c.categoryName || c.categoryId || '未分类';
          if (!mergedData[category]) mergedData[category] = {};
          if (!mergedData[category][resourceKey]) mergedData[category][resourceKey] = {};
          (c.metrics || []).forEach(m => {
            if (!m || !m.metric) return;
            mergedData[category][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        });
      } else {
        const category = row.categoryName || row.categoryId || '未分类';
        const resourceKey = row.resource || '0-默认资源';
        if (!mergedData[category]) mergedData[category] = {};
        if (!mergedData[category][resourceKey]) mergedData[category][resourceKey] = {};
        if (Array.isArray(row.metrics)) {
          row.metrics.forEach(m => {
            if (!m || !m.metric) return;
            mergedData[category][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        } else {
          const metricName = row.metric;
          if (!metricName) return;
          mergedData[category][resourceKey][metricName] = Number(row.value ?? 0);
        }
      }
    });

    const rawRows = reportData.rawData || reportData.summary?.rawData ||
                   reportData.raw_data || reportData.summary?.raw_data || [];
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

      Object.keys(mergedData).forEach(category => {
        const resources = mergedData[category] || {};
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey];
          if (!resourceRawData) return;
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[category][resourceKey][`${metricName}_raw`] = resourceRawData[metricName];
          });
        });
      });
    }

    return mergedData;
  }

  // 3. Fallback: Reconstruct metricData from reportData.summary.cases if available
  const cases = reportData.cases || reportData.summary?.cases;
  if (cases && Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseCategoryComparison] Reconstructing metricData from cases');
    const reconstructedData = {};
    const accumulator = {};

    cases.forEach(caseItem => {
      const category = caseItem.category || 'Uncategorized';
      const caseMetrics = caseItem.metrics || {};

      if (!accumulator[category]) accumulator[category] = {};

      if (Array.isArray(caseMetrics)) {
        caseMetrics.forEach(group => {
          if (!group || !group.resource || !Array.isArray(group.metrics)) return;
          const resourceKey = group.resource;
          if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {};
          group.metrics.forEach(m => {
            if (!m || !m.metric) return;
            const dim = m.metric;
            if (!accumulator[category][resourceKey][dim]) {
              accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] };
            }
            const val = m.value;
            if (val !== null && val !== undefined) {
              accumulator[category][resourceKey][dim].sum += Number(val);
              accumulator[category][resourceKey][dim].count += 1;
              accumulator[category][resourceKey][dim].values.push(Number(val));
            }
          });
        });
      } else {
        Object.keys(caseMetrics).forEach(resourceKey => {
          if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {};

          const metrics = caseMetrics[resourceKey];
          Object.keys(metrics).forEach(dim => {
            if (!accumulator[category][resourceKey][dim]) {
              accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] };
            }
            const val = metrics[dim];
            if (val !== null && val !== undefined) {
               accumulator[category][resourceKey][dim].sum += Number(val);
               accumulator[category][resourceKey][dim].count += 1;
               accumulator[category][resourceKey][dim].values.push(Number(val));
            }
          });
        });
      }
    });

    // Calculate averages and populate reconstructedData
    Object.keys(accumulator).forEach(category => {
      reconstructedData[category] = {};
      Object.keys(accumulator[category]).forEach(resourceKey => {
        reconstructedData[category][resourceKey] = {};
        Object.keys(accumulator[category][resourceKey]).forEach(dim => {
          const stats = accumulator[category][resourceKey][dim];
          if (stats.count > 0) {
            reconstructedData[category][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4));
            reconstructedData[category][resourceKey][`${dim}_raw`] = stats.values;
          } else {
            reconstructedData[category][resourceKey][dim] = 0;
          }
        });
      });
    });

    return reconstructedData;
  }

  // 2. 如果没有预计算数据，则从 detailedResults 中提取 (原有逻辑)
  const dataAccumulator = {};

  const detailedResults = reportData.detailedResults || reportData.summary?.detailedResults || [];
  if (detailedResults && detailedResults.length > 0) {
    detailedResults.forEach(result => {
        const testCaseId = result.testCaseId;
        let category = '其他';
        let categoryId = 'default';
        let tags = [];

        if (result.testCaseGroup) {
          category = result.testCaseGroup.name;
          categoryId = result.testCaseGroup.id;
        }
        if (result.testCaseTags) {
          tags = result.testCaseTags.map(tag => tag.name);
        }
        else if (result.testCaseName) {
          category = result.testCaseName;
          categoryId = testCaseId;
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

      if (!dataAccumulator[category]) {
        dataAccumulator[category] = {};
      }
      if (!dataAccumulator[category][resourceKey]) {
        dataAccumulator[category][resourceKey] = {
          counts: {},
          sums: {},
          values: {}
        };
      }

      if (result.dimensionScores) {
        result.dimensionScores.forEach(dim => {
          if (!dataAccumulator[category][resourceKey].counts[dim.dimensionName]) {
            dataAccumulator[category][resourceKey].counts[dim.dimensionName] = 0;
            dataAccumulator[category][resourceKey].sums[dim.dimensionName] = 0;
            dataAccumulator[category][resourceKey].values[dim.dimensionName] = [];
          }

          dataAccumulator[category][resourceKey].counts[dim.dimensionName]++;
          dataAccumulator[category][resourceKey].sums[dim.dimensionName] += dim.score;
          dataAccumulator[category][resourceKey].values[dim.dimensionName].push(dim.score);
        });
      } else if (result.metrics) {
        Object.entries(result.metrics).forEach(([dimName, value]) => {
          if (!dataAccumulator[category][resourceKey].counts[dimName]) {
            dataAccumulator[category][resourceKey].counts[dimName] = 0;
            dataAccumulator[category][resourceKey].sums[dimName] = 0;
            dataAccumulator[category][resourceKey].values[dimName] = [];
          }

          dataAccumulator[category][resourceKey].counts[dimName]++;
          dataAccumulator[category][resourceKey].sums[dimName] += value;
          dataAccumulator[category][resourceKey].values[dimName].push(value);
        });
      }
    });
  }

  const extractedMetricData = {};

  Object.entries(dataAccumulator).forEach(([category, resources]) => {
    extractedMetricData[category] = {};

    Object.entries(resources).forEach(([resourceKey, data]) => {
      if (!extractedMetricData[category][resourceKey]) {
        extractedMetricData[category][resourceKey] = {};
      }

      Object.entries(data.counts).forEach(([dimName, count]) => {
        const sum = data.sums[dimName];
        const average = count > 0 ? sum / count : 0;

        extractedMetricData[category][resourceKey][dimName] = average;

        extractedMetricData[category][resourceKey][`${dimName}_raw`] = data.values[dimName];
      });
    });
  });

  return extractedMetricData;
}

export function computeMetricDataFromCases(cases: any, deps: {
  selectedCategories: any
  selectedTags: any
  allAvailableCategories: any
  allAvailableTags: any
}) {
  const { selectedCategories, selectedTags, allAvailableCategories, allAvailableTags } = deps
  const reconstructedData = {}
  const accumulator = {}

  const selectedCategorySet = new Set(selectedCategories.value || [])
  const selectedTagSet = new Set(selectedTags.value || [])
  const includeUntagged = selectedTagSet.has('无标签') || selectedTagSet.has('未标记')
  selectedTagSet.delete('无标签')
  selectedTagSet.delete('未标记')
  const useCategoryFilter = selectedCategorySet.size > 0 && selectedCategorySet.size !== (allAvailableCategories.value || []).length
  const useTagFilter =
    (selectedTagSet.size > 0 || includeUntagged) &&
    ((selectedTags.value || []).length !== (allAvailableTags.value || []).length)

  ;(cases || []).forEach(caseItem => {
    if (!caseItem) return
    const category = caseItem.category || '未分类'
    if (useCategoryFilter && !selectedCategorySet.has(category)) return

    const caseTagsRaw = caseItem.tags || []
    const caseTagNames = Array.isArray(caseTagsRaw)
      ? caseTagsRaw.map(t => (typeof t === 'object' ? t?.name : t)).filter(Boolean)
      : []
    if (useTagFilter) {
      const hasTagMatch = caseTagNames.some(t => selectedTagSet.has(t))
      const isUntagged = caseTagNames.length === 0
      if (!hasTagMatch && !(includeUntagged && isUntagged)) return
    }

    const caseMetrics = caseItem.metrics || {}
    if (!accumulator[category]) accumulator[category] = {}

    if (Array.isArray(caseMetrics)) {
      caseMetrics.forEach(group => {
        if (!group || !group.resource || !Array.isArray(group.metrics)) return
        const resourceKey = group.resource
        if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {}
        group.metrics.forEach(m => {
          if (!m || !m.metric) return
          const dim = m.metric
          if (!accumulator[category][resourceKey][dim]) {
            accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] }
          }
          const val = m.value
          if (val !== null && val !== undefined) {
            accumulator[category][resourceKey][dim].sum += Number(val)
            accumulator[category][resourceKey][dim].count += 1
            accumulator[category][resourceKey][dim].values.push(Number(val))
          }
        })
      })
    } else {
      Object.keys(caseMetrics).forEach(resourceKey => {
        if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {}
        const metrics = caseMetrics[resourceKey] || {}
        Object.keys(metrics).forEach(dim => {
          if (!accumulator[category][resourceKey][dim]) {
            accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] }
          }
          const val = metrics[dim]
          if (val !== null && val !== undefined) {
            accumulator[category][resourceKey][dim].sum += Number(val)
            accumulator[category][resourceKey][dim].count += 1
            accumulator[category][resourceKey][dim].values.push(Number(val))
          }
        })
      })
    }
  })

  Object.keys(accumulator).forEach(category => {
    reconstructedData[category] = {}
    Object.keys(accumulator[category]).forEach(resourceKey => {
      reconstructedData[category][resourceKey] = {}
      Object.keys(accumulator[category][resourceKey]).forEach(dim => {
        const stats = accumulator[category][resourceKey][dim]
        if (stats.count > 0) {
          reconstructedData[category][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4))
          reconstructedData[category][resourceKey][`${dim}_raw`] = stats.values
        } else {
          reconstructedData[category][resourceKey][dim] = 0
        }
      })
    })
  })

  return reconstructedData
}

export function createCategoryChartData(deps: {
  activeDisplayType: any
  devices: any
  filteredCategories: any
  getRawDataValue: (category: any, device: any, metricName: any) => any
  getMetricValue: (category: any, device: any, metricName: any) => any
  getResourceLabel: (key: any) => any
  generateDistributionChartData: any
  chartColors: any
  chartBorderColors: any
}) {
  const {
    activeDisplayType, devices, filteredCategories, getRawDataValue, getMetricValue,
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
        filteredCategories.value.forEach(category => {
          const rawData = getRawDataValue(category, device, metricName);
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
      labels: filteredCategories.value,
      datasets: devices.value.map((device: any, index: number) => {
        const color = chartColors[index % chartColors.length]
        const borderColor = chartBorderColors[index % chartBorderColors.length]

        const data = filteredCategories.value.map((category: any) => {
          return parseFloat(getMetricValue(category, device, metricName))
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

export function createCategoryMetricValueGetters(deps: {
  metricData: any
}) {
  const { metricData } = deps

  const getMetricValue = (category: any, device: any, metricName: any) => {
    if (metricData.value) {
      const categoryData = metricData.value[category];
      if (categoryData) {
        if (categoryData[device] && categoryData[device][metricName] !== undefined) {
          return categoryData[device][metricName];
        }

        if (typeof device === 'object' && device !== null) {
          const resourceKey = `${device.id}-${device.name}`;
          if (categoryData[resourceKey] && categoryData[resourceKey][metricName] !== undefined) {
            return categoryData[resourceKey][metricName];
          }
        }

        const deviceName = typeof device === 'object' ? (device.name || device.deviceName) :
                          (typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device);

        const entries = Object.entries(categoryData);
        for (const [key, data] of entries) {
          const currentResourceName = key.includes('-') ? key.split('-').slice(1).join('-') : key;
          if (currentResourceName === deviceName && data[metricName] !== undefined) {
            return data[metricName];
          }
        }
      }
    }

    return 0
  }

  const getRawDataValue = (category: any, device: any, metricName: any) => {
    const rawDataKey = `${metricName}_raw`;
    if (metricData.value) {
      const categoryData = metricData.value[category];
      if (categoryData) {
        if (categoryData[device] && Array.isArray(categoryData[device][rawDataKey])) {
          return categoryData[device][rawDataKey];
        }

        if (typeof device === 'object' && device !== null) {
          const resourceKey = `${device.id}-${device.name}`;
          if (categoryData[resourceKey] && Array.isArray(categoryData[resourceKey][rawDataKey])) {
            return categoryData[resourceKey][rawDataKey];
          }
        }

        const deviceName = typeof device === 'object' ? (device.name || device.deviceName) :
                          (typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device);
        const entries = Object.entries(categoryData);
        for (const [key, data] of entries) {
          const currentResourceName = key.includes('-') ? key.split('-').slice(1).join('-') : key;
          if (currentResourceName === deviceName && Array.isArray(data[rawDataKey])) {
            return data[rawDataKey];
          }
        }
      }
    }
    return [];
  };

  return { getMetricValue, getRawDataValue }
}
