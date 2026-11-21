/**
 * 设备监控统计域模型（domain 层；16_设备域.md §3.7「历史监控 → 统计分析」四图）。
 * 形态对照《设备监控统计与播放设备控制接口契约》§1.2（INT-1573 定稿 / INT-1578 落地）：
 * - availability / cpu / memory / battery 当日无采点为 null → 图表断点，**不得补 0**；
 * - errors / operations / healthCheckSamples 为当日计数（0 是有效值）；
 * - date 为展示用 MM-DD（契约要求在基础设施层格式化），isoDate 保留原始 YYYY-MM-DD。
 */
export interface DeviceStatsPoint {
  /** 展示用日期 MM-DD（vChart x 轴） */
  date: string
  /** 原始 ISO 日期 YYYY-MM-DD */
  isoDate: string
  /** 当日可用率(%)；无可评估设备/时长 → null */
  availability: number | null
  /** 当日 health_check 采点 CPU 均值(%)；无采点 → null */
  cpu: number | null
  /** 当日内存均值(%)；无采点 → null */
  memory: number | null
  /** 当日电量均值(%)；无采点 → null */
  battery: number | null
  /** 当日失败事件数（health_check/operation 失败 + to_status=error） */
  errors: number
  /** 当日成功操作事件数 */
  operations: number
  /** 当日 health_check 事件数（采点密度标注用） */
  healthCheckSamples: number
}

export interface DeviceMonitorStats {
  granularity: string
  startDate: string
  endDate: string
  /** 条件命中的测试设备数量（与参与可用率平均的设备数无强制相等关系） */
  deviceCount: number
  points: DeviceStatsPoint[]
}
