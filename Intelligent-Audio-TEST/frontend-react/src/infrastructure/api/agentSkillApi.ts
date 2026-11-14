/**
 * 自定义 Skill API（infrastructure 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §4.4 / §11，INT-2549 后端契约）。
 *
 * 端点（网关透明转发，无 {success,data} 信封）：
 *   GET    /agent/skills
 *   POST   /agent/skills
 *   PUT    /agent/skills/{id}
 *   DELETE /agent/skills/{id}
 *   POST   /agent/skills/{id}/publish
 *   POST   /agent/skills/{id}/disable
 *   POST   /agent/skills/{id}/fork
 *   POST   /agent/skills/import          （multipart，原字节上传）
 *   GET    /agent/skills/{id}/export     （application/zip，原字节下载）
 *   GET    /agent/skills/{id}/versions
 *
 * 传输统一走 client.ts（JWT / 错误码归一）；本文件只产出 camelCase 领域对象，
 * snake_case 转换在 infrastructure/dto/agentSkill.dto.ts。
 *
 * zip 是唯一格式口径：前端不拼装、不改写包结构——导入原字节上传服务端返回的
 * 包，正文经导出包的根级 `SKILL.md` 读取（§11 无单条详情接口）。
 */
import JSZip from 'jszip'

import type {
  AgentSkill,
  AgentSkillDraftInput,
  AgentSkillForkInput,
  AgentSkillList,
  SkillDocument,
  SkillIssue,
  SkillPublishResult,
  SkillVersion,
} from '@/domain/models/agentSkill'
import {
  toAgentSkill,
  toSkillDraftRequest,
  toSkillIssues,
  toSkillPublishResult,
  toSkillTools,
  toSkillVersions,
  type AgentSkillListDto,
  type AgentSkillViewDto,
  type SkillIssueDto,
  type SkillPublishDto,
  type SkillVersionListDto,
} from '@/infrastructure/dto/agentSkill.dto'

import { ApiError } from './api-error'
import { request } from './client'

/** 契约路径（相对 API_BASE_URL=/api/v1） */
export const AGENT_SKILL_API_PATHS = {
  skills: '/agent/skills',
  skill: (skillId: string) => `/agent/skills/${encodeURIComponent(skillId)}`,
  publish: (skillId: string) =>
    `/agent/skills/${encodeURIComponent(skillId)}/publish`,
  disable: (skillId: string) =>
    `/agent/skills/${encodeURIComponent(skillId)}/disable`,
  fork: (skillId: string) =>
    `/agent/skills/${encodeURIComponent(skillId)}/fork`,
  export: (skillId: string) =>
    `/agent/skills/${encodeURIComponent(skillId)}/export`,
  versions: (skillId: string) =>
    `/agent/skills/${encodeURIComponent(skillId)}/versions`,
  import: '/agent/skills/import',
} as const

/** SKILL.md 文件名（包结构根级唯一；与 shared/skill_package.py 同口径） */
const SKILL_FILE_NAME = 'SKILL.md'

/** GET /agent/skills —— 本人可见 Skill（平台层 + 自定义层，带遮蔽标注） */
export async function listAgentSkills(): Promise<AgentSkillList> {
  const dto = await request<AgentSkillListDto>('GET', AGENT_SKILL_API_PATHS.skills)
  return {
    items: (dto.items ?? []).map(toAgentSkill),
    tools: toSkillTools(dto.tools),
    skillsCount: dto.skills_count ?? 0,
    toolsCount: dto.tools_count ?? 0,
    l1Tokens: dto.l1_tokens ?? 0,
    l1BudgetTokens: dto.l1_budget_tokens ?? 0,
  }
}

/** POST /agent/skills —— 新建草稿（version=1, status=DRAFT） */
export async function createAgentSkill(
  input: AgentSkillDraftInput
): Promise<AgentSkill> {
  const dto = await request<AgentSkillViewDto>(
    'POST',
    AGENT_SKILL_API_PATHS.skills,
    toSkillDraftRequest(input)
  )
  return toAgentSkill(dto)
}

/** PUT /agent/skills/{id} —— 保存（version +1；ACTIVE 保存后回到 DRAFT） */
export async function updateAgentSkill(
  skillId: string,
  input: AgentSkillDraftInput
): Promise<AgentSkill> {
  const dto = await request<AgentSkillViewDto>(
    'PUT',
    AGENT_SKILL_API_PATHS.skill(skillId),
    toSkillDraftRequest(input)
  )
  return toAgentSkill(dto)
}

/** DELETE /agent/skills/{id} —— 删除自定义 Skill（版本行保留供回放；服务端 204 无响应体） */
export async function deleteAgentSkill(skillId: string): Promise<void> {
  await request<string>('DELETE', AGENT_SKILL_API_PATHS.skill(skillId), undefined, {
    responseType: 'text',
  })
}

/** POST /agent/skills/{id}/publish —— 发布门槛（未达标时返回 gate + 仍为 DRAFT） */
export async function publishAgentSkill(
  skillId: string
): Promise<SkillPublishResult> {
  const dto = await request<SkillPublishDto>(
    'POST',
    AGENT_SKILL_API_PATHS.publish(skillId)
  )
  return toSkillPublishResult(dto)
}

/** POST /agent/skills/{id}/disable —— 停用（立即退出 L1 / 触发候选） */
export async function disableAgentSkill(skillId: string): Promise<AgentSkill> {
  const dto = await request<AgentSkillViewDto>(
    'POST',
    AGENT_SKILL_API_PATHS.disable(skillId)
  )
  return toAgentSkill(dto)
}

/** POST /agent/skills/{id}/fork —— 从平台 / 可见 Skill 复制出本人草稿 */
export async function forkAgentSkill(
  skillId: string,
  input: AgentSkillForkInput = {}
): Promise<AgentSkill> {
  const dto = await request<AgentSkillViewDto>(
    'POST',
    AGENT_SKILL_API_PATHS.fork(skillId),
    { name: input.name ?? '', description: input.description ?? '' }
  )
  return toAgentSkill(dto)
}

/** POST /agent/skills/import —— zip 导入（原字节上传，不重打包） */
export async function importAgentSkill(file: File): Promise<AgentSkill> {
  const form = new FormData()
  form.append('file', file, file.name)
  const dto = await request<AgentSkillViewDto>(
    'POST',
    AGENT_SKILL_API_PATHS.import,
    form
  )
  return toAgentSkill(dto)
}

/**
 * GET /agent/skills/{id}/export —— 导出 zip（原字节）。
 * 文件名按卡面口径 `<name>-v<version>.zip` 由调用方拼装；字节本身原样透传。
 */
export async function exportAgentSkillPackage(skillId: string): Promise<Blob> {
  return request<Blob>('GET', AGENT_SKILL_API_PATHS.export(skillId), undefined, {
    responseType: 'blob',
  })
}

/** GET /agent/skills/{id}/versions —— 版本历史（不含正文） */
export async function listAgentSkillVersions(
  skillId: string
): Promise<SkillVersion[]> {
  const dto = await request<SkillVersionListDto>(
    'GET',
    AGENT_SKILL_API_PATHS.versions(skillId)
  )
  return toSkillVersions(dto)
}

/**
 * 读取 SKILL.md 文档（正文 + frontmatter 原文）。
 *
 * 来源是导出包的根级 `SKILL.md`（§11 未提供单条详情接口，导出包是服务端唯一
 * 内容口径）；只读取文本，不回写、不重打包。
 */
export async function fetchAgentSkillDocument(
  skillId: string
): Promise<SkillDocument> {
  const blob = await exportAgentSkillPackage(skillId)
  let archive: JSZip
  try {
    archive = await JSZip.loadAsync(blob)
  } catch {
    throw new ApiError({ message: '导出包不是合法 zip，无法打开编辑器' })
  }
  const entry = archive.file(SKILL_FILE_NAME)
  if (!entry) {
    throw new ApiError({
      message: `导出包缺少根级 ${SKILL_FILE_NAME}，无法打开编辑器`,
    })
  }
  const raw = await entry.async('string')
  return splitSkillMarkdown(raw)
}

/** `---` frontmatter + 正文拆分（只拆分，不改写） */
export function splitSkillMarkdown(raw: string): SkillDocument {
  const normalized = raw.replace(/^﻿/, '').replace(/\r\n/g, '\n')
  const match = /^---\n([\s\S]*?)\n---\n?/.exec(normalized)
  if (!match) {
    return { frontmatterText: '', body: normalized }
  }
  return {
    frontmatterText: match[1] ?? '',
    // 保留正文原样：只去掉 frontmatter 与紧随的一个空行
    body: normalized.slice(match[0].length).replace(/^\n/, ''),
  }
}

/** 从错误对象提取逐项校验明细（服务端 unprocessable / 校验失败共用顶层 issues） */
export function skillIssuesFromError(error: unknown): SkillIssue[] {
  if (!(error instanceof ApiError)) return []
  if (!Array.isArray(error.issues)) return []
  return toSkillIssues(error.issues as SkillIssueDto[])
}

/** 触发浏览器下载（导出的 zip 原字节） */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // 交给浏览器读完再释放
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
}
