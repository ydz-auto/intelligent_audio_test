// -*- coding: utf-8 -*-
/**
 * 报告统计分析 API stub（G04，INT-741）
 *
 * 后端状态：**待 FEAT** —— api_gateway report_bp.py 无 `/reports/statistics*` 端点
 * （总表 §3.3 F1）。本文件为 infrastructure 层契约桩，供 UI 出壳期标注缺口；
 * 页面当前不发起真实请求（不造数据兜底）。
 *
 * 端点命名与响应形状为**保守预估**（对齐 React 15_报告域 §2.2 口径：
 * 报告数量统计 / 测试用例执行统计 / 评估指标统计 / 设备性能统计；
 * 维度=时间/任务类型/设备类型/评估维度；结果=统计表格/图表/报告/异常）。
 * FEAT 落地后由【接线·新Vue·报告域】卡按真实 schema 替换，本页解除注释接入。
 */

// 待接线：FEAT（/reports/statistics* 端点）落地后替换为真实请求
export const reportStatisticsApi = {
  /**
   * 统计维度/统计结果
   * GET /reports/statistics
   * 参数：dimension(time|task_type|device_type|evaluation_metric)、start_time、end_time、...
   */
  async getStatistics(_params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    // 待接线：无后端端点，暂不返回示例数据（避免页面造数兜底）
    throw new Error('待接线：GET /reports/statistics 端点未实现（FEAT 挂主项目）')
  },

  /**
   * 趋势分析
   * GET /reports/statistics/trend
   * 参数：trend_type(time|dimension)、metric、start_time、end_time、...
   */
  async getTrend(_params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    // 待接线：无后端端点
    throw new Error('待接线：GET /reports/statistics/trend 端点未实现（FEAT 挂主项目）')
  },

  /**
   * 报表生成
   * POST /reports/statistics/report
   * 参数：report_type、content、format(csv|excel|pdf|html)、time_range、...
   */
  async generateReport(_params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    // 待接线：无后端端点
    throw new Error('待接线：POST /reports/statistics/report 端点未实现（FEAT 挂主项目）')
  },
}
