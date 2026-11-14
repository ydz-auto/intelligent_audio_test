/**
 * 自定义 Skill API 单测（INT-2550 §4.4 / §11 契约）：路径 / 多行转换 / 逐项
 * 校验明细（顶层 issues）/ 导入 multipart / 导出包读正文 / 204 删除。
 * fetch 全部 mock；连真实后端的证据由 tests/ui/probe_int2550_skill_manage.py 补。
 */
import JSZip from 'jszip'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AGENT_SKILL_API_PATHS,
  createAgentSkill,
  deleteAgentSkill,
  fetchAgentSkillDocument,
  importAgentSkill,
  listAgentSkills,
  skillIssuesFromError,
  splitSkillMarkdown,
  updateAgentSkill,
} from '@/infrastructure/api/agentSkillApi'
import { ApiError } from '@/infrastructure/api/api-error'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function zipResponse(skillMd: string): Promise<Response> {
  const zip = new JSZip()
  zip.file('SKILL.md', skillMd)
  const bytes = await zip.generateAsync({ type: 'uint8array' })
  return new Response(bytes, {
    status: 200,
    headers: { 'Content-Type': 'application/zip' },
  })
}

describe('agentSkillApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
  })

  it('listAgentSkills：GET /agent/skills，items + tools 一并转 camelCase', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: 'platform:platform-reference',
            scope: 'PLATFORM',
            name: 'platform-reference',
            description: '平台契约',
            version: '1.0.0',
            status: 'ACTIVE',
            content_hash: 'ff00',
            allowed_tools: ['platform_contract'],
            permissions: [],
            budgets: {},
            updated_at: null,
          },
        ],
        tools: [
          { name: 'task_query', description: '查', risk: 'READ', permissions: ['task:read'], enabled: true },
        ],
        skills_count: 13,
        tools_count: 31,
        l1_tokens: 1200,
        l1_budget_tokens: 8000,
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listAgentSkills()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/agent/skills',
      expect.objectContaining({ method: 'GET' })
    )
    expect(result.items[0]).toMatchObject({
      id: 'platform:platform-reference',
      scope: 'PLATFORM',
      status: 'ACTIVE',
      allowedTools: ['platform_contract'],
    })
    expect(result.tools[0].name).toBe('task_query')
    expect(result.skillsCount).toBe(13)
    expect(result.l1BudgetTokens).toBe(8000)
  })

  it('createAgentSkill：POST 只发草稿字段（身份字段不出现）', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 's-1', scope: 'USER', name: 'demo', status: 'DRAFT' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await createAgentSkill({
      name: 'demo',
      description: '说明',
      frontmatter: { 'allowed-tools': [] },
      body: '## Gotchas\n\n## 验收\n',
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/agent/skills')
    expect(init.method).toBe('POST')
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect(body).toEqual({
      name: 'demo',
      description: '说明',
      body: '## Gotchas\n\n## 验收\n',
      frontmatter: { 'allowed-tools': [] },
    })
  })

  it('updateAgentSkill：422 / 400 的顶层 issues 归一为 ApiError.issues，页面可按 field 定位', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: 'Skill 校验未通过（2 项），未落库',
            code: 'SKILL_VALIDATION_FAILED',
            issues: [
              { code: 'INVALID_NAME', severity: 'ERROR', field: 'name', message: '名称格式不合法' },
              { code: 'MISSING_REQUIRED_SECTION', severity: 'ERROR', field: 'body', message: '缺少 ## Gotchas' },
            ],
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } }
        )
      )
    )

    const error = await updateAgentSkill('s-1', {
      name: 'Bad_Name',
      description: '',
      body: '',
    }).catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).httpStatus).toBe(400)
    expect((error as ApiError).userMessage).toContain('Skill 校验未通过')
    expect(skillIssuesFromError(error)).toEqual([
      { code: 'INVALID_NAME', severity: 'ERROR', field: 'name', message: '名称格式不合法' },
      { code: 'MISSING_REQUIRED_SECTION', severity: 'ERROR', field: 'body', message: '缺少 ## Gotchas' },
    ])
  })

  it('importAgentSkill：POST /agent/skills/import 以 multipart 上传原始文件', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 's-2', scope: 'USER', name: 'imported', status: 'DRAFT' }, 201))
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['zip-bytes'], 'demo.zip', { type: 'application/zip' })
    await importAgentSkill(file)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`/api/v1${AGENT_SKILL_API_PATHS.import}`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    const form = init.body as FormData
    expect((form.get('file') as File).name).toBe('demo.zip')
    // multipart 由浏览器生成边界，不手写 Content-Type
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('fetchAgentSkillDocument：读导出包根级 SKILL.md 并拆出正文', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () =>
        zipResponse(
          '---\nname: demo\ndescription: 说明\nallowed-tools:\n  - task_query\n---\n\n## Gotchas\n\n- 无\n\n## 验收\n\n- 通过\n'
        )
      )
    )

    const document = await fetchAgentSkillDocument('s-1')
    expect(document.frontmatterText).toContain('name: demo')
    expect(document.body.startsWith('## Gotchas')).toBe(true)
    expect(document.body).toContain('## 验收')
  })

  it('fetchAgentSkillDocument：缺根级 SKILL.md 时显式失败，不静默给空正文', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        const zip = new JSZip()
        zip.file('README.md', '# not a skill')
        const bytes = await zip.generateAsync({ type: 'uint8array' })
        return new Response(bytes, { status: 200 })
      })
    )

    await expect(fetchAgentSkillDocument('s-1')).rejects.toBeInstanceOf(ApiError)
  })

  it('deleteAgentSkill：DELETE 204 空响应体不报「无效 JSON」', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    )
    await expect(deleteAgentSkill('s-1')).resolves.toBeUndefined()
  })
})

describe('splitSkillMarkdown', () => {
  it('无 frontmatter 时正文原样返回', () => {
    expect(splitSkillMarkdown('# 标题\n正文')).toEqual({
      frontmatterText: '',
      body: '# 标题\n正文',
    })
  })

  it('CRLF 归一，正文只去掉 frontmatter 后的一个空行', () => {
    const document = splitSkillMarkdown(
      '---\r\nname: demo\r\n---\r\n\r\n## Gotchas\r\n\r\n- 无\r\n'
    )
    expect(document.frontmatterText).toBe('name: demo')
    expect(document.body).toBe('## Gotchas\n\n- 无\n')
  })
})
