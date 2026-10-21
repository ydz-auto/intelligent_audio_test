/**
 * Agent Skill API module（INT-1140 联接你的 agent）
 *
 * skill 包下载：GET /api/v1/agent/skill?base_url=<浏览器地址栏，可改>
 * 网关动态拼装 zip（SKILL.md + MCP 配置模板），登录即可下载
 * （JWT 由 http/client.ts 拦截器注入）。
 */
import { request, type RequestOptions } from '../http/client';

/** skill 包下载文件名（后端 zip：SKILL.md + MCP 配置模板） */
export const SKILL_DOWNLOAD_FILENAME = 'intelligent-audio-test-skill.zip'

/** 下载接口在 request blob 分支下 401/404 不抛错，识别错误 JSON Blob 转异常 */
async function assertSkillBlob(blob: Blob): Promise<Blob> {
  if (blob instanceof Blob
    && typeof blob.text === 'function'
    && (blob.type.includes('json') || blob.size < 2048)) {
    const text = await blob.text()
    const t = text.trim()
    if (t.startsWith('{') || t.startsWith('[')) {
      try {
        const parsed = JSON.parse(t)
        const detail = parsed?.detail ?? parsed?.message
        if (detail) throw new Error(detail)
      } catch (e) {
        if (e instanceof Error && e.message && !(e instanceof SyntaxError)) throw e
      }
    }
  }
  return blob
}

export const agentSkillApi = {
  /**
   * 下载智能音频测试 skill 包（zip：SKILL.md + MCP 配置模板）
   * GET /agent/skill?base_url=<浏览器地址栏，可改>
   * base_url 为空时后端从 Host / Origin 头兜底。
   */
  async downloadSkill(baseUrl: string, options: RequestOptions = {}): Promise<Blob> {
    const blob = await request<Blob>('GET', '/agent/skill', null, {
      ...options,
      params: { base_url: baseUrl },
      responseType: 'blob',
    });
    return assertSkillBlob(blob instanceof Blob ? blob : new Blob([blob as unknown as BlobPart]));
  },
}
