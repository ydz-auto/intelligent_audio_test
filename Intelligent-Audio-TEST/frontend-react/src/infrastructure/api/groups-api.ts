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

/** 分组 facet/表头共用（现接口无分组管理分页 UI），拉大页供全量渲染。
 * 200 覆盖共享库全量分组（当前 128+；100 会漏掉最新创建的分组，组头/facet 缺失）。 */
const GROUP_LIST_PAGE_SIZE = 200

/** 分组列表（GET /groups；分组 facet 选项 + 分组头行渲染共用） */
export async function fetchGroups(): Promise<TestCaseGroup[]> {
  const dto = await apiClient.get<GroupListDataDto>('/groups', {
    params: { page: 1, per_page: GROUP_LIST_PAGE_SIZE },
  })
  return (dto.items ?? []).map(toTestCaseGroup)
}

/** 分组写侧载荷（camelCase Domain；对照 group.py GroupCreateRequest/GroupUpdateRequest） */
export interface TestCaseGroupDraft {
  name: string
  description?: string | null
  algorithmType?: string | null
}

/** 创建分组（POST /groups；GroupCreateRequest → StringIdData，重复名后端 400） */
export async function createGroup(
  draft: TestCaseGroupDraft
): Promise<{ id: string }> {
  const dto = await apiClient.post<{ id?: string | number }>('/groups', {
    name: draft.name,
    description: draft.description ?? '',
    algorithm_type: draft.algorithmType ?? '',
  })
  return { id: String(dto?.id ?? '') }
}

/** 更新分组（PUT /groups/{id}；GroupUpdateRequest） */
export async function updateGroup(
  id: string,
  draft: TestCaseGroupDraft
): Promise<void> {
  await apiClient.put(`/groups/${id}`, {
    name: draft.name,
    description: draft.description ?? '',
    algorithm_type: draft.algorithmType ?? '',
  })
}

/** 删除分组（DELETE /groups/{id}?cascade；cascade=true 连同组下用例删除，对照 Vue deleteGroup；
 *  INT-1138 开始测试删除分组照用例管理页口径传 cascade=true） */
export async function deleteGroup(id: string, cascade = false): Promise<void> {
  await apiClient.delete(`/groups/${id}`, { params: { cascade } })
}
