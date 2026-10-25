// -*- coding: utf-8 -*-
/**
 * Agent Skill 下载 API（INT-1193「连接你的 agent」入口页；INT-1150 后端实现）
 *
 * 契约：`GET /api/v1/agent/skill` —— 下载 skill 包 zip（SKILL.md + mcp.json），
 * 服务地址经 `?base_url=` 注入包内 MCP 配置模板（后端未收到时按 Origin / Host 兜底）。
 * 请求经基础设施层（request → /api/v1 前缀），调用方只接触 Blob。
 */
import { request } from '../http/client'

/** 下载 skill 包的可选配置 */
export interface DownloadSkillOptions {
  /** skill 包内 MCP 配置模板预填的服务地址（默认取浏览器地址栏） */
  serviceUrl?: string
}

/**
 * 下载 skill 包（zip：SKILL.md + mcp.json，后端 INT-1150 动态拼装）。
 * 参数名为 `base_url`（后端 `download_skill(request, base_url: str = '')`）；
 * 不传时后端按 Origin / Host 兜底。
 */
export async function downloadSkillPackage(options: DownloadSkillOptions = {}): Promise<Blob> {
  return request<Blob>('GET', '/agent/skill', null, {
    responseType: 'blob',
    params: { base_url: options.serviceUrl },
  })
}
