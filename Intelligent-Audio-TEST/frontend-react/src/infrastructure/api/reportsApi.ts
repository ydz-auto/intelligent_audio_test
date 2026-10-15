/**
 * 报告 API client（infrastructure 层；08_AI对话页.md §3.8 报告上下文列表「可先行」）。
 * 数据 mock 常量（红线④）；TODO(API 接线): 改为 GET /api/v1/reports（report:read，report_bp.py:29 实测）。
 */
import { MOCK_REPORTS, type MockReportListItem } from '@/infrastructure/mock/ai-chat-mock'

export const reportsApi = {
  list(): Promise<MockReportListItem[]> {
    return Promise.resolve(MOCK_REPORTS)
  },
}
