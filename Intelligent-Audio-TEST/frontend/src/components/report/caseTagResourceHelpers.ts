export function createResourceLabelGetter(resourceHeaderMap: any) {
  const getResourceLabel = (resourceKey: any) => {
    const key = String(resourceKey ?? '')
    const mapped = resourceHeaderMap.value?.[key]
    if (mapped) return mapped

    if (typeof resourceKey === 'string' && /^t\d+-\d{12}-/.test(resourceKey)) {
      const parts = resourceKey.split('-')
      if (parts.length >= 4) {
        const name = parts.slice(3).join('-')
        if (name) return name
      }
    }

    if (typeof resourceKey === 'string' && resourceKey.includes('_')) {
      const parts = resourceKey.split('_')
      const prefix = parts[0]
      const name = parts.slice(1).join('_')
      if (/^\d{14}$/.test(prefix)) {
        const month = prefix.substring(4, 6)
        const day = prefix.substring(6, 8)
        const hour = prefix.substring(8, 10)
        const minute = prefix.substring(10, 12)
        return `${month}-${day} ${hour}:${minute} ${name}`
      }
      return name
    }

    return resourceKey
  }

  return { getResourceLabel }
}

export function createTagMetricValueGetters(deps: {
  filteredTagMetricData: any
}) {
  const { filteredTagMetricData } = deps

  const getMetricValue = (tag: any, device: any, metricName: any) => {
    const dataToUse = filteredTagMetricData.value;
    if (dataToUse) {
      const tagData = dataToUse[tag];
      if (tagData) {
        let deviceData = tagData[device];

        if (!deviceData || deviceData[metricName] === undefined) {
          const deviceName = typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device;
          for (const [resourceKey, data] of Object.entries(tagData)) {
            const currentResourceName = resourceKey.includes('-') ? resourceKey.split('-').slice(1).join('-') : resourceKey;
            if (currentResourceName === deviceName) {
              deviceData = data;
              break;
            }
          }
        }

        if (deviceData && deviceData[metricName] !== undefined) {
          return deviceData[metricName];
        }
      }
    }

    return 0
  }

  const getRawDataValue = (tag: any, device: any, metricName: any) => {
    const rawDataKey = `${metricName}_raw`;
    const dataToUse = filteredTagMetricData.value;
    if (dataToUse) {
      const tagData = dataToUse[tag];
      if (tagData) {
        if (tagData[device] && Array.isArray(tagData[device][rawDataKey])) {
          return tagData[device][rawDataKey];
        }

        const deviceName = typeof device === 'string' && device.includes('-') ? device.split('-').slice(1).join('-') : device;
        for (const [resourceKey, data] of Object.entries(tagData)) {
          const currentResourceName = resourceKey.includes('-') ? resourceKey.split('-').slice(1).join('-') : resourceKey;
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
