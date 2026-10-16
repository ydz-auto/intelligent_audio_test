/**
 * 用例分组 API 桩（infrastructure 层，11_用例域.md §3.5 分组视图 + §5.7.4）。
 * 全部返回 mock 常量（红线④），接线时替换为真实请求：
 *   GET /api/v1/groups                    （group.py GroupListData）
 *   GET /api/v1/groups/{id}
 *   POST /api/v1/groups | PUT /api/v1/groups/{id} | DELETE /api/v1/groups/{id}（含 move-cases）
 *   POST /api/v1/testcases/ids            （组全选 ID 圈定，group.py GroupMoveCasesRequest 同源）
 */
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import { MOCK_GROUPS } from '../mock/testcases-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), 120))
}

/** 分组列表（分组 facet 选项 + 分组头行渲染共用） */
export async function fetchGroups(): Promise<TestCaseGroup[]> {
  // TODO(API 接线): GET /api/v1/groups?page=1&per_page=100
  return mockLatency(MOCK_GROUPS)
}
