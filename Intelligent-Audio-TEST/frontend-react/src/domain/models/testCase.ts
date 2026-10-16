/**
 * 用例域领域模型（domain 层；10_测试执行.md §9 落位）。
 * 形态对照 api_gateway/schemas/testcase.py TestCaseListItem/TestCaseConfig 实测：
 * id/name/description/group_id/group_name/type/tags/algorithm_type/total_duration/updated_at。
 * 本卡消费子集（选择场景列裁剪），完整用例管理页模型归 11_用例域.md。
 */

export type TestCaseType = 'e2e' | 'api'

/** 用例列表项（选择场景所需子集） */
export interface TestCase {
  id: string
  name: string
  description: string | null
  groupId: string | null
  groupName: string | null
  /** 执行类型（api/e2e）；schema type 字段实测 */
  type: TestCaseType | null
  tags: string[]
  algorithmType: string | null
  /** 轮次数（由 config.rounds 长度派生；展示「{n} 轮」） */
  rounds: number
  /** 总时长（秒，total_duration 实测；展示「{x}m {y}s」） */
  totalDuration: number | null
  updatedAt: string | null
}

/** 评估维度简报（testcase.py TestCaseDimensionBrief） */
export interface EvaluationDimension {
  id: number
  name: string
  type: string | null
}
