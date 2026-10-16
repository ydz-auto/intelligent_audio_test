/**
 * 用例分组领域模型（domain 层；11_用例域.md §3.5 分组视图）。
 * 形态对照 api_gateway/schemas/group.py GroupItem 实测：
 * id/name/description/algorithm_type/created_at/updated_at/test_case_count。
 */

export interface TestCaseGroup {
  id: string
  name: string
  description: string | null
  /** 关联算法类型（算法中文名经 algorithm 登记表映射） */
  algorithmType: string | null
  createdAt: string
  updatedAt: string
  /** 分组下用例计数（后端 GroupItem.test_case_count 实测） */
  testCaseCount: number
}
