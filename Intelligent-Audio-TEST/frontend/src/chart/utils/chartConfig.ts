/**
 * 图表配置工具函数
 */

export const colors: Record<string, string> = {
  primary: '#1677FF',
  secondary: '#FF6A00',
  success: '#52C41A',
  warning: '#FAAD14',
  info: '#13C2C2',
  purple: '#722ED1'
};

export const colorArray = Object.values(colors);

export const datasetTypeHasAlpha = (type: string): boolean => {
  return ['bar', 'line'].includes(type);
};

export const getDefaultChartConfig = (): any => {
  return {
    responsive: true,
    maintainAspectRatio: false,
    devicePixelRatio: window.devicePixelRatio || 1,
    responsiveAnimationDuration: 0,
    resizeDelay: 0,
    layout: {
      padding: {
        top: 10,
        right: 10,
        bottom: 50,
        left: 10
      }
    },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          usePointStyle: true,
          padding: 20,
          font: {
            size: 12,
            family: 'Inter, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif',
            weight: 500
          },
          color: '#333333'
        }
      },
      tooltip: {
        backgroundColor: '#FFFFFF',
        titleColor: '#333333',
        bodyColor: '#333333',
        borderColor: '#E5E5E5',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
        boxPadding: 8,
        usePointStyle: true,
        callbacks: {
          label: function(context: any) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            
            let value = 0;
            if (context.parsed.y !== undefined && context.parsed.y !== null) {
              value = context.parsed.y;
            } else if (context.parsed.r !== undefined && context.parsed.r !== null) {
              value = context.parsed.r;
            } else if (context.parsed !== undefined && context.parsed !== null) {
              value = context.parsed;
            }
            
            value = typeof value === 'number' ? value : 0;
            return `${label}${value.toFixed(2)}`;
          }
        }
      }
    },
    zoom: {
      zoom: {
        wheel: { enabled: true },
        drag: { enabled: true },
        pinch: { enabled: true },
        mode: 'x',
        speed: 0.1
      },
      pan: { enabled: true, mode: 'x', speed: 10, threshold: 5 }
    },
    scales: {
      x: {
        grid: { display: true, color: '#F0F0F0' },
        ticks: {
          padding: 10,
          color: '#777777',
          font: {
            size: 12,
            family: 'Inter, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif'
          }
        },
        border: { color: '#E5E5E5' }
      },
      y: {
        beginAtZero: true,
        grid: { display: true, color: '#F0F0F0' },
        ticks: {
          padding: 10,
          color: '#777777',
          font: {
            size: 12,
            family: 'Inter, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif'
          }
        },
        border: { color: '#E5E5E5' }
      }
    },
    animation: { duration: 1000, easing: 'easeInOutQuart' },
    interaction: { intersect: false, mode: 'index' },
    events: ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove']
  };
};

export const applyChartTypeConfig = (config: any, type: string, title?: string): any => {
  if (type === 'distribution') {
    config.plugins.title = {
      display: true,
      text: '正态分布分析',
      color: '#333333',
      font: { size: 16, weight: 600 }
    };
    config.scales = {
      x: {
        type: 'linear',
        title: { display: true, text: `不同区间的${title}`, color: '#777777' },
        grid: { display: true, color: '#F0F0F0' },
        ticks: {
          color: '#777777',
          maxRotation: 45,
          minRotation: 0,
          callback: function(value: any) {
            return typeof value === 'number' ? value.toFixed(1) : value;
          }
        },
        border: { color: '#E5E5E5' }
      },
      y: {
        title: { display: true, text: '区间内用例数量', color: '#777777' },
        grid: { color: '#F0F0F0' },
        ticks: { color: '#777777', stepSize: 1, precision: 0 },
        beginAtZero: true,
        border: { color: '#E5E5E5' }
      }
    };
    // 正态分布图的tooltip标题显示x值
    if (config.plugins && config.plugins.tooltip) {
      config.plugins.tooltip.callbacks = {
        ...config.plugins.tooltip.callbacks,
        title: function(context: any) {
          if (context[0] && typeof context[0].parsed.x === 'number') {
            return `区间: ${context[0].parsed.x.toFixed(2)}`;
          }
          return '';
        },
        label: function(context: any) {
          let label = context.dataset.label || '';
          if (label) {
            label += ': ';
          }
          const value = typeof context.parsed.y === 'number' ? context.parsed.y : 0;
          return `${label}${value} 个`;
        }
      };
    }
  } else if (type === 'pie' || type === 'doughnut' || type === 'polarArea') {
    delete config.scales;
    delete config.zoom;
    config.plugins.legend.position = 'right';
  } else if (type === 'radar') {
    config.scales = {
      r: {
        beginAtZero: true,
        min: 0,
        max: 100,
        stepSize: 20,
        grid: { color: 'rgba(0, 0, 0, 0.05)' },
        angleLines: { color: 'rgba(0, 0, 0, 0.1)' },
        ticks: { padding: 10, font: { size: 12 } }
      }
    };
    delete config.zoom;
    if (config.plugins) {
      delete config.plugins.zoom;
    }
    config.events = config.events.filter((event: string) => event !== 'wheel' && event !== 'touchstart' && event !== 'touchmove');
  }
  
  if (config.scales && config.scales.y) {
    config.scales.y.beginAtZero = true;
    config.scales.y.grid.color = 'rgba(0, 0, 0, 0.05)';
    config.scales.y.ticks.padding = 10;
    config.scales.y.autoSkip = true;
    config.scales.y.max = undefined;
    config.scales.y.min = undefined;
    config.scales.y.grace = 5;
  }
  
  return config;
};

export const mergeUserOptions = (defaultOptions: any, userOptions: any, type: string, enableZoom: boolean): any => {
  const options = { ...defaultOptions };
  
  Object.keys(userOptions).forEach(key => {
    if (key !== 'zoom') {
      options[key] = typeof userOptions[key] === 'object' && userOptions[key] !== null 
        ? { ...options[key], ...userOptions[key] } 
        : userOptions[key];
    }
  });
  
  if (enableZoom) {
    const defaultZoomConfig = getDefaultChartConfig().zoom;
    const zoomConfig = { ...defaultZoomConfig, ...userOptions.zoom };
    
    const chartType = type === 'distribution' ? 'line' : type;
    if (chartType === 'line' || chartType === 'bar') {
      zoomConfig.zoom.wheel.enabled = true;
      zoomConfig.zoom.drag.enabled = true;
      zoomConfig.zoom.pinch.enabled = true;
      zoomConfig.zoom.mode = 'xy';
      zoomConfig.pan.enabled = true;
      zoomConfig.pan.mode = 'xy';
      zoomConfig.pan.threshold = 5;
      zoomConfig.pan.speed = 10;
      
      delete zoomConfig.zoom.limits;
      delete zoomConfig.pan.limits;
      delete zoomConfig.limits;
      
      options.zoom = zoomConfig;
      if (!options.plugins) {
        options.plugins = {};
      }
      options.plugins.zoom = zoomConfig;
    } else {
      delete options.zoom;
      if (options.plugins) {
        delete options.plugins.zoom;
      }
    }
  } else {
    delete options.zoom;
    if (options.plugins) {
      delete options.plugins.zoom;
    }
  }
  
  return options;
};

export const prepareChartData = (data: any, type: string): any => {
  const chartData = { ...data };
  
  chartData.datasets = chartData.datasets.map((dataset: any, index: number) => {
    const datasetColor = colorArray[index % colorArray.length];
    const alpha = datasetTypeHasAlpha(type) ? 'B3' : '';
    const shouldFill = dataset.fill !== undefined ? dataset.fill : 
      (type === 'line' || type === 'radar' || type === 'distribution' ? false : undefined);
    
    return {
      ...dataset,
      backgroundColor: dataset.backgroundColor || 
        (type === 'pie' || type === 'doughnut' || type === 'polarArea' ? colorArray[index % colorArray.length] : datasetColor + alpha),
      borderColor: dataset.borderColor || 
        (type === 'pie' || type === 'doughnut' || type === 'polarArea' ? '#ffffff' : datasetColor),
      borderWidth: dataset.borderWidth || 
        (type === 'pie' || type === 'doughnut' || type === 'polarArea' ? 2 : 2),
      hoverOffset: dataset.hoverOffset || 
        (type === 'pie' || type === 'doughnut' ? 4 : undefined),
      fill: shouldFill,
      tension: dataset.tension !== undefined ? dataset.tension : 
        (type === 'line' || type === 'distribution' ? 0.3 : undefined),
      borderRadius: dataset.borderRadius !== undefined ? dataset.borderRadius : 
        (type === 'bar' ? 4 : undefined),
      pointBackgroundColor: dataset.pointBackgroundColor || datasetColor,
      pointBorderColor: dataset.pointBorderColor || '#ffffff',
      pointBorderWidth: dataset.pointBorderWidth || 2,
      pointRadius: dataset.pointRadius || 4,
      pointHoverRadius: dataset.pointHoverRadius || 6,
      shadowColor: dataset.shadowColor || 'transparent',
      shadowOffsetX: dataset.shadowOffsetX || 0,
      shadowOffsetY: dataset.shadowOffsetY || 0,
      shadowBlur: dataset.shadowBlur || 0
    };
  });
  
  return chartData;
};

export const isCanvasInDom = (element: HTMLElement | null): boolean => {
  return !!(element && element.isConnected);
};

export interface DistributionStat {
  label: string;
  value: string | number;
}

const emptyDistributionStats: DistributionStat[] = [
  { label: '样本数量', value: 0 },
  { label: '平均值 (μ)', value: '0.00' },
  { label: '标准差 (σ)', value: '0.00' },
  { label: '最小值', value: '0.00' },
  { label: '下四分位数 (Q1)', value: '0.00' },
  { label: '中位数 (Q2)', value: '0.00' },
  { label: '上四分位数 (Q3)', value: '0.00' },
  { label: '最大值', value: '0.00' },
  { label: 'μ+1σ 内百分比', value: '0.0%' },
  { label: 'μ+2σ 内百分比', value: '0.0%' },
  { label: 'μ+3σ 内百分比', value: '0.0%' },
  { label: '超出+3σ 百分比', value: '0.0%' },
  { label: 'μ-1σ 内百分比', value: '0.0%' },
  { label: 'μ-2σ 内百分比', value: '0.0%' },
  { label: 'μ-3σ 内百分比', value: '0.0%' },
  { label: '超出-3σ 百分比', value: '0.0%' }
];

const calculateStatsFromData = (allData: number[]): DistributionStat[] => {
  if (allData.length === 0) {
    return emptyDistributionStats;
  }

  const count = allData.length;
  const sum = allData.reduce((acc, val) => acc + val, 0);
  const mean = sum / count;

  const squaredDifferences = allData.map(val => Math.pow(val - mean, 2));
  const variance = squaredDifferences.reduce((acc, val) => acc + val, 0) / count;
  const stdDev = Math.sqrt(variance);

  const sortedData = [...allData].sort((a, b) => a - b);
  const min = sortedData[0];
  const max = sortedData[count - 1];
  const median = count % 2 === 0
    ? (sortedData[count / 2 - 1] + sortedData[count / 2]) / 2
    : sortedData[Math.floor(count / 2)];
  const q1Index = Math.floor(count / 4);
  const q1 = sortedData[q1Index];
  const q3Index = Math.floor((count * 3) / 4);
  const q3 = sortedData[q3Index];

  const calculatePercent = (value: number) => `${((value / count) * 100).toFixed(1)}%`;

  const aboveMeanWithin1Sigma = allData.filter(val => val > mean && val <= mean + stdDev).length;
  const aboveMeanWithin2Sigma = allData.filter(val => val > mean + stdDev && val <= mean + 2 * stdDev).length;
  const aboveMeanWithin3Sigma = allData.filter(val => val > mean + 2 * stdDev && val <= mean + 3 * stdDev).length;
  const aboveMeanOutside3Sigma = allData.filter(val => val > mean + 3 * stdDev).length;

  // 下方区间按标准差划分，数据全非负时下界钳制为0
  const belowMeanWithin1Sigma = allData.filter(val => val < mean && val >= Math.max(mean - stdDev, 0)).length;
  const belowMeanWithin2Sigma = allData.filter(val => val < mean - stdDev && val >= Math.max(mean - 2 * stdDev, 0)).length;
  const belowMeanWithin3Sigma = allData.filter(val => val < mean - 2 * stdDev && val >= Math.max(mean - 3 * stdDev, 0)).length;
  const belowMeanOutside3Sigma = allData.filter(val => val < Math.max(mean - 3 * stdDev, 0)).length;
  // [0, μ) 区间：0到均值之间的数据点
  const zeroToMean = allData.filter(val => val >= 0 && val < mean).length;

  return [
    { label: '样本数量', value: count },
    { label: '平均值 (μ)', value: mean.toFixed(2) },
    { label: '标准差 (σ)', value: stdDev.toFixed(2) },
    { label: '最小值', value: min.toFixed(2) },
    { label: '下四分位数 (Q1)', value: q1.toFixed(2) },
    { label: '中位数 (Q2)', value: median.toFixed(2) },
    { label: '上四分位数 (Q3)', value: q3.toFixed(2) },
    { label: '最大值', value: max.toFixed(2) },
    { label: '(μ, μ+σ] 百分比', value: calculatePercent(aboveMeanWithin1Sigma) },
    { label: '(μ+σ, μ+2σ] 百分比', value: calculatePercent(aboveMeanWithin2Sigma) },
    { label: '(μ+2σ, μ+3σ] 百分比', value: calculatePercent(aboveMeanWithin3Sigma) },
    { label: '超出+3σ 百分比', value: calculatePercent(aboveMeanOutside3Sigma) },
    { label: '[0, μ) 百分比', value: calculatePercent(zeroToMean) },
    { label: '[max(μ-σ,0), μ) 百分比', value: calculatePercent(belowMeanWithin1Sigma) },
    { label: '[max(μ-2σ,0), μ-σ) 百分比', value: calculatePercent(belowMeanWithin2Sigma) },
    { label: '[max(μ-3σ,0), μ-2σ) 百分比', value: calculatePercent(belowMeanWithin3Sigma) },
    { label: '超出-3σ 百分比', value: calculatePercent(belowMeanOutside3Sigma) }
  ];
};

export const calculateDistributionStats = (data: any): DistributionStat[] => {
  let allData: number[] = [];

  if (data.rawData && Array.isArray(data.rawData)) {
    allData = data.rawData.filter((val: any) => typeof val === 'number' && !isNaN(val));
  } else {
    data.datasets.forEach((dataset: any) => {
      if (dataset.data) {
        allData.push(...dataset.data
          .map((item: any) => typeof item === 'object' && item !== null && typeof item.y === 'number' ? item.y : (typeof item === 'number' ? item : null))
          .filter((val: any) => val !== null && !isNaN(val))
        );
      }
    });
  }

  return calculateStatsFromData(allData);
};

export const calculateDistributionStatsByDevice = (data: any): { [device: string]: DistributionStat[] } => {
  const result: { [device: string]: DistributionStat[] } = {};

  if (data.deviceRawData && typeof data.deviceRawData === 'object') {
    Object.keys(data.deviceRawData).forEach(device => {
      const deviceData = (data.deviceRawData[device] || []).filter((val: any) => typeof val === 'number' && !isNaN(val));
      result[device] = calculateStatsFromData(deviceData);
    });
  }

  return result;
};

/**
 * 根据可见x轴范围重新分箱统计
 * @param chartData 原始图表数据（含rawData和deviceRawData）
 * @param visibleMin 可见区间下限
 * @param visibleMax 可见区间上限
 * @returns 新的datasets，每个区间内实际数据点数
 */
export const rebinDistributionData = (chartData: any, visibleMin: number, visibleMax: number): any[] => {
  if (!chartData || !chartData.datasets) return [];

  const range = visibleMax - visibleMin;
  if (range <= 0) return chartData.datasets;

  // 固定20个区间，放大后每个区间更细
  const intervals = 20;
  const step = range / intervals;

  return chartData.datasets.map((dataset: any) => {
    // 获取该设备的原始数据
    const deviceLabel = dataset.label;
    let deviceRaw: number[] = [];

    if (chartData.deviceRawData && chartData.deviceRawData[deviceLabel]) {
      deviceRaw = chartData.deviceRawData[deviceLabel].filter((v: any) => typeof v === 'number' && !isNaN(v) && isFinite(v));
    }

    // 按新区间重新统计
    const values = [];
    for (let i = 0; i < intervals; i++) {
      const intervalStart = visibleMin + i * step;
      const midPoint = visibleMin + (i + 0.5) * step;
      const count = deviceRaw.filter(v => i === intervals - 1 ? v >= intervalStart : v >= intervalStart && v < intervalStart + step).length;
      values.push({ x: parseFloat(midPoint.toFixed(2)), y: count });
    }

    return {
      ...dataset,
      data: values
    };
  });
};
