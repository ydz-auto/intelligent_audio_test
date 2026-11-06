/**
 * IAM DTO → 领域适配器测试（INT-729 返修）：
 * toPermissionModules 对后端新增权限码做前缀归组——前缀命中目录模块 id 必须并入
 * 该模块，不得生成同 id 双模块（INT-729 审计 P3：权限矩阵 duplicate-key 根因）。
 */
import { describe, expect, it } from 'vitest'

import { toPermissionModules } from '../iam-adapter'
import type { AuthPermissionDto } from '@/infrastructure/dto/iam.dto'

const dto = (id: number, name: string, description: string): AuthPermissionDto => ({
  id,
  name,
  description,
})

describe('toPermissionModules', () => {
  it('目录外新增码前缀命中目录模块 id → 并入该模块，模块 id 无重复', () => {
    const dtos = [
      dto(1, 'task:read', '查看任务'),
      dto(2, 'task:share', '分享任务'),
      dto(3, 'audio:share', '分享音频'),
      dto(4, 'report:studio:read', '查看报告工作室'),
      dto(5, 'evaluation:share', '分享评估'),
      dto(6, 'group:share', '分享分组'),
      dto(7, 'tag:share', '分享标签'),
      dto(8, 'benchmark:report:read', '查看 Benchmark 报告'),
    ]
    const modules = toPermissionModules(dtos)
    const ids = modules.map((m) => m.id)
    // 无同 id 双模块（React duplicate key 根因）
    expect(new Set(ids).size).toBe(ids.length)
    // 并入后目录模块仍唯一，且目录外码落进对应目录模块
    expect(ids.filter((id) => id === 'task')).toHaveLength(1)
    const task = modules.find((m) => m.id === 'task')
    expect(task?.permissions.map((p) => p.code)).toContain('task:share')
    const report = modules.find((m) => m.id === 'report')
    expect(report?.permissions.map((p) => p.code)).toContain('report:studio:read')
  })

  it('真新前缀（目录模块 id 之外的）才建新组', () => {
    const dtos = [
      dto(1, 'task:read', '查看任务'),
      dto(2, 'lab:start', '启动实验室'),
      dto(3, 'status:read', '查看站点状态'),
      dto(4, 'option:read', '查看系统选项'),
      dto(5, 'task.result.review:read', '复核任务结果'),
    ]
    const modules = toPermissionModules(dtos)
    const ids = modules.map((m) => m.id)
    expect(ids).toContain('task')
    for (const prefix of ['lab', 'status', 'option', 'task.result.review']) {
      expect(ids).toContain(prefix)
    }
    // 真新前缀模块不重复
    expect(new Set(ids).size).toBe(ids.length)
  })
})
