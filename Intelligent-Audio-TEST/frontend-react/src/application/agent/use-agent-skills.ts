/**
 * 自定义 Skill query + mutation（application 层；INT-2550 / 方案 §4.4 / §11）。
 *
 * 单一缓存口径：技能列表一个 query key（含意图工具清单），版本历史与编辑器
 * 文档各一个子 key。新建 / 保存 / fork / 导入 / 发布 / 停用 / 删除成功后一律
 * invalidateQueries：列表、来源页签计数、状态页签计数、门槛面板同源刷新，
 * 不做局部改 state。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type {
  AgentSkill,
  AgentSkillDraftInput,
  AgentSkillForkInput,
  AgentSkillList,
  SkillDocument,
  SkillPublishResult,
  SkillVersion,
} from '@/domain/models/agentSkill'
import {
  createAgentSkill,
  deleteAgentSkill,
  disableAgentSkill,
  exportAgentSkillPackage,
  fetchAgentSkillDocument,
  forkAgentSkill,
  importAgentSkill,
  listAgentSkills,
  listAgentSkillVersions,
  publishAgentSkill,
  skillApiErrorCode,
  skillIssuesFromError,
  updateAgentSkill,
} from '@/infrastructure/api/agentSkillApi'
import { ApiError } from '@/infrastructure/api/api-error'

/** 技能列表缓存键（列表 / 页签计数 / 门槛面板共用） */
export const AGENT_SKILLS_QUERY_KEY = ['agent', 'skills'] as const

/** 版本历史缓存键 */
export function agentSkillVersionsQueryKey(skillId: string) {
  return [...AGENT_SKILLS_QUERY_KEY, skillId, 'versions'] as const
}

/** 编辑器文档缓存键（导出包里的 SKILL.md 正文） */
export function agentSkillDocumentQueryKey(skillId: string) {
  return [...AGENT_SKILLS_QUERY_KEY, skillId, 'document'] as const
}

/**
 * 页面可直接展示的错误文案：已知业务码查 `codeCopy` 表（features 传入，
 * 避免 application 反向依赖 features 文案），否则回退 ApiError 归一文案。
 */
export function skillErrorMessage(
  error: unknown,
  fallback: string,
  codeCopy?: Record<string, string>
): string {
  const code = skillApiErrorCode(error)
  if (code && codeCopy?.[code]) return codeCopy[code]
  if (error instanceof ApiError && error.userMessage) return error.userMessage
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export function useAgentSkillsQuery() {
  return useQuery<AgentSkillList>({
    queryKey: [...AGENT_SKILLS_QUERY_KEY],
    queryFn: listAgentSkills,
    staleTime: 10_000,
    retry: false,
  })
}

export function useAgentSkillVersionsQuery(skillId: string | null) {
  return useQuery<SkillVersion[]>({
    queryKey: agentSkillVersionsQueryKey(skillId ?? ''),
    queryFn: () => listAgentSkillVersions(skillId as string),
    enabled: Boolean(skillId),
    staleTime: 0,
    retry: false,
  })
}

/** 编辑器正文（来自导出包根级 SKILL.md；同一 skill 打开一次后缓存） */
export function useAgentSkillDocumentQuery(
  skillId: string | null,
  enabled = true
) {
  return useQuery<SkillDocument>({
    queryKey: agentSkillDocumentQueryKey(skillId ?? ''),
    queryFn: () => fetchAgentSkillDocument(skillId as string),
    enabled: Boolean(skillId) && enabled,
    staleTime: 0,
    retry: false,
  })
}

export function useAgentSkillMutations() {
  const queryClient = useQueryClient()

  const invalidateSkills = () =>
    void queryClient.invalidateQueries({ queryKey: AGENT_SKILLS_QUERY_KEY })

  const invalidateSkill = (skillId: string) => {
    void queryClient.invalidateQueries({ queryKey: AGENT_SKILLS_QUERY_KEY })
    void queryClient.invalidateQueries({
      queryKey: agentSkillVersionsQueryKey(skillId),
    })
    void queryClient.invalidateQueries({
      queryKey: agentSkillDocumentQueryKey(skillId),
    })
  }

  const create = useMutation({
    mutationFn: (input: AgentSkillDraftInput) => createAgentSkill(input),
    onSuccess: () => {
      toast.success('Skill 草稿已创建')
      invalidateSkills()
    },
    // 逐项校验明细由页面按 issues 定位；这里只提示错误码文案，避免静默
    onError: (error: unknown) => {
      if (skillIssuesFromError(error).length > 0) return
      toast.error(skillErrorMessage(error, '创建 Skill 失败'))
    },
  })

  const update = useMutation({
    mutationFn: (args: { id: string; input: AgentSkillDraftInput }) =>
      updateAgentSkill(args.id, args.input),
    onSuccess: (_skill, args) => {
      toast.success('Skill 已保存')
      invalidateSkill(args.id)
    },
    onError: (error: unknown) => {
      if (skillIssuesFromError(error).length > 0) return
      toast.error(skillErrorMessage(error, '保存 Skill 失败'))
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteAgentSkill(id),
    onSuccess: () => {
      toast.success('Skill 已删除')
      invalidateSkills()
    },
    onError: (error: unknown) => {
      toast.error(skillErrorMessage(error, '删除 Skill 失败'))
    },
  })

  const fork = useMutation({
    mutationFn: (args: { id: string; input?: AgentSkillForkInput }) =>
      forkAgentSkill(args.id, args.input),
    onSuccess: () => {
      toast.success('已从该 Skill fork 出草稿')
      invalidateSkills()
    },
    onError: (error: unknown) => {
      toast.error(skillErrorMessage(error, 'fork Skill 失败'))
    },
  })

  const importPackage = useMutation({
    mutationFn: (file: File) => importAgentSkill(file),
    onSuccess: () => {
      toast.success('Skill 已导入为草稿')
      invalidateSkills()
    },
    onError: (error: unknown) => {
      if (skillIssuesFromError(error).length > 0) return
      toast.error(skillErrorMessage(error, '导入 Skill 失败'))
    },
  })

  const publish = useMutation({
    mutationFn: (id: string): Promise<SkillPublishResult> =>
      publishAgentSkill(id),
    onSuccess: (result, id) => {
      if (result.gate.passed) {
        toast.success('Skill 已发布（ACTIVE）')
      } else {
        // 门槛未达标不是错误：仍为草稿，明细由门槛面板展示
        toast.warning('未达发布门槛：Skill 仍为草稿')
      }
      invalidateSkill(id)
    },
    onError: (error: unknown) => {
      if (skillIssuesFromError(error).length > 0) return
      toast.error(skillErrorMessage(error, '发布 Skill 失败'))
    },
  })

  const disable = useMutation({
    mutationFn: (id: string): Promise<AgentSkill> => disableAgentSkill(id),
    onSuccess: () => {
      toast.success('Skill 已停用')
      invalidateSkills()
    },
    onError: (error: unknown) => {
      toast.error(skillErrorMessage(error, '停用 Skill 失败'))
    },
  })

  /** 导出（调用方负责把 blob 交给浏览器下载） */
  const exportPackage = useMutation({
    mutationFn: (id: string) => exportAgentSkillPackage(id),
    onError: (error: unknown) => {
      toast.error(skillErrorMessage(error, '导出 Skill 失败'))
    },
  })

  return {
    create,
    update,
    remove,
    fork,
    importPackage,
    publish,
    disable,
    exportPackage,
    invalidateSkills,
    invalidateSkill,
  }
}
