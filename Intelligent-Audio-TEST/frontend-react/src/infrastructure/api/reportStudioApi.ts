/**
 * Report Studio API 占位桩（infrastructure 层；08_AI对话页.md §3.8）。
 * Report Studio 业务 API 五组端点（documents/versions/charts/exports）全部待后端立项；
 * 报告工作模式（§3.6 双栏）在 Agent 后端立项前整块隐藏，本桩只留契约形状。
 *
 * TODO(API 接线): 实现 POST/GET/PUT /api/v1/report-studio/documents（expected_version 乐观锁）
 *   GET /documents/{id}/versions、POST /documents/{id}/restore（恢复产生新版本，不覆盖）
 *   GET /documents/{id}/charts/{chartId}（ChartSpec 服务端校验渲染）
 *   POST /exports、GET /exports/{id}/download（异步作业）
 */
export const reportStudioApi = {
  createDraft: null as unknown,
  getDocument: null as unknown,
  updateDocument: null as unknown,
  listVersions: null as unknown,
  restoreVersion: null as unknown,
  getChartData: null as unknown,
  requestExport: null as unknown,
  getExportJob: null as unknown,
}
