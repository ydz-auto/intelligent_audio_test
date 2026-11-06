/**
 * 声压级映射校准曲线 spec（features/spl-mapping/lib；VChart 封装随基座 use-chart-theme）。
 * §6.8 物理域增益映射详情：SPL↔增益散点/折线（x=增益偏移 dB，y=实测 SPL dB）；
 * §6.10 数字域校准弹窗：增益曲线预览（SPL→gain，dB，x=目标 SPL，y=线性增益换算 dB）。
 * 色值走 getDashboardChartColors 色板；深浅色由调用方 useChartTheme 门控整图重建。
 */
import { dataScheme as vchartDefaultDataScheme } from '@visactor/vchart/esm/theme/color-scheme/builtin/default'

export type VChartSpec = Record<string, unknown>

export function getSplChartColors(domainLength: number): string[] {
  const scheme =
    vchartDefaultDataScheme.find(
      (item) => !item.maxDomainLength || domainLength <= item.maxDomainLength
    ) ?? vchartDefaultDataScheme.at(-1)

  return (scheme?.scheme ?? []).filter(
    (color): color is string => typeof color === 'string'
  )
}

export interface CurvePoint {
  x: number
  y: number
}

const EMPTY_TITLE = {
  visible: true,
  text: '暂无数据',
}

/** 物理域校准曲线（§6.8；x=增益偏移 gainOffset，y=实测 SPL spl，散点 + 折线） */
export function buildCalibrationCurveSpec(points: CurvePoint[]): VChartSpec {
  const values = [...points]
    .sort((a, b) => a.x - b.x)
    .map((point) => ({ gainOffset: point.x, spl: point.y }))

  if (values.length === 0) {
    return {
      type: 'line',
      data: [{ id: 'calibrationData', values: [] }],
      xField: 'gainOffset',
      yField: 'spl',
      legends: { visible: false },
      label: { visible: false },
      title: { ...EMPTY_TITLE, subtext: '尚无校准数据' },
      animation: true,
    }
  }

  const color = getSplChartColors(1)[0]
  return {
    type: 'common',
    data: [{ id: 'calibrationData', values }],
    series: [
      {
        type: 'line',
        name: '校准曲线',
        xField: 'gainOffset',
        yField: 'spl',
        point: { visible: true, size: 8, style: { fill: color } },
        line: {
          style: {
            lineWidth: 2,
            curveType: 'monotone',
          },
        },
      },
      {
        type: 'scatter',
        name: '校准点',
        xField: 'gainOffset',
        yField: 'spl',
        point: { size: 8, style: { fill: color } },
      },
    ],
    axes: [
      { orient: 'left', label: { formatMethod: (v: unknown) => `${v} dB` } },
      { orient: 'bottom', label: { formatMethod: (v: unknown) => `${v} dB` } },
    ],
    legends: { visible: false },
    tooltip: {
      mark: {
        content: [
          {
            key: '增益偏移',
            value: (datum: Record<string, unknown>) => `${datum?.gainOffset} dB`,
          },
          {
            key: '实测 SPL',
            value: (datum: Record<string, unknown>) => `${datum?.spl} dB`,
          },
        ],
      },
    },
    animation: true,
  }
}

/** 数字域增益曲线预览（§6.10；x=目标 SPL，y=线性增益换算 dB；≥2 点才显示） */
export function buildDigitalGainCurveSpec(points: CurvePoint[]): VChartSpec {
  const values = [...points]
    .sort((a, b) => a.x - b.x)
    .map((point) => ({ targetSpl: point.x, gainDb: point.y }))

  if (values.length < 2) {
    return {
      type: 'line',
      data: [{ id: 'digitalCurveData', values: [] }],
      xField: 'targetSpl',
      yField: 'gainDb',
      legends: { visible: false },
      label: { visible: false },
      title: { ...EMPTY_TITLE, subtext: '至少 2 个校准点后显示曲线预览' },
      animation: true,
    }
  }

  const color = getSplChartColors(1)[0]
  return {
    type: 'line',
    data: [{ id: 'digitalCurveData', values }],
    xField: 'targetSpl',
    yField: 'gainDb',
    color,
    line: {
      style: {
        lineWidth: 2,
        curveType: 'monotone',
      },
    },
    point: { visible: true, size: 6, style: { fill: color } },
    axes: [
      { orient: 'left', label: { formatMethod: (v: unknown) => `${v} dB` } },
      { orient: 'bottom', label: { formatMethod: (v: unknown) => `${v} dB SPL` } },
    ],
    legends: { visible: false },
    tooltip: {
      mark: {
        content: [
          {
            key: '目标 SPL',
            value: (datum: Record<string, unknown>) => `${datum?.targetSpl} dB`,
          },
          {
            key: '增益',
            value: (datum: Record<string, unknown>) => `${datum?.gainDb} dB`,
          },
        ],
      },
    },
    animation: true,
  }
}
