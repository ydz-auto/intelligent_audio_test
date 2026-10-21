/**
 * 用例分组 API（infrastructure/api 层；接线 INT-639，经统一 client.ts）。
 * 对照后端 api_gateway/routes/group_bp.py + schemas/group.py GroupListQuery：
 *   GET /api/v1/groups?page=1&per_page=100（分组 facet 选项 + 分组头行渲染共用）
 * 响应 GroupListData（PaginatedData 内 GroupItem snake_case）；
 * snake→camel 转换收敛在 dto；application/domain 层只见 camelCase Domain。
 */
import { apiClient } from './client'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import {
  toTestCaseGroup,
  type GroupListDataDto,
} from '@/infrastructure/dto/testcase-group.dto'

/** 分组 facet/表头共用（现接口无分组管理分页 UI），拉大页供全量渲染 */
const GROUP_LIST_PAGE_SIZE = 100

/** 分组列表（GET /groups；分组 facet 选项 + 分组头行渲染共用） */
export async function fetchGroups(): Promise<TestCaseGroup[]> {
  const dto = await apiClient.get<GroupListDataDto>('/groups', {
    params: { page: 1, per_page: GROUP_LIST_PAGE_SIZE },
  })
  return (dto.items ?? []).map(toTestCaseGroup)
}

/** 删除分组（DELETE /groups/{id}?cascade=true，group:delete；级联删除分组下全部用例） */
export async function deleteGroup(id: string): Promise<void> {
  await apiClient.delete(`/groups/${id}`, { params: { cascade: true } })
}
