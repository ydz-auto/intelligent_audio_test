// -*- coding: utf-8 -*-
/**
 * Agent Skill 下载 API（INT-1154「联接你的 agent」入口页）
 *
 * 契约：`GET /api/v1/agent/skill` —— 下载 skill 包 zip（SKILL.md + MCP 配置模板），
 * 服务地址 URL 默认取浏览器地址栏、可改，预填进包内 MCP 配置模板。
 * 请求经基础设施层（request → /api/v1 前缀），调用方只接触 Blob。
 *
 * // 待接线：后端 INT-1150（api_gateway skill+MCP 分道）未合栈 → 本函数为契约桩，
 * 返回符合后端 schema 的示例 zip（SKILL.md + mcp.json，URL 按调用方配置预填）；
 * 合栈后由【接线·新Vue】卡替换为真实请求：
 *   return request<Blob>('GET', '/agent/skill', null, {
 *     responseType: 'blob',
 *     params: { url: options.serviceUrl },
 *   });
 */
import JSZip from 'jszip'

/** 下载 skill 包的可选配置 */
export interface DownloadSkillOptions {
  /** skill 包内 MCP 配置模板预填的服务地址（默认取浏览器地址栏） */
  serviceUrl?: string
}

/**
 * 下载 skill 包（zip：SKILL.md + MCP 配置模板）。
 * // 待接线 桩：后端 INT-1150 未合栈，此处生成符合后端 schema 的示例 zip；
 * 合栈后上述 doc 注释里的真实请求体即落地，示例数据删除，不留双口径。
 */
export async function downloadSkillPackage(options: DownloadSkillOptions = {}): Promise<Blob> {
  const serviceUrl = (options.serviceUrl || window.location.origin).replace(/\/$/, '')
  const zip = new JSZip()
  zip.file('SKILL.md', buildSampleSkillMarkdown(serviceUrl))
  zip.file('mcp.json', buildSampleMcpTemplate(serviceUrl))
  return zip.generateAsync({ type: 'blob' })
}

/** 示例 SKILL.md（后端契约模板的占位；描述安装/配置/能力范围） */
function buildSampleSkillMarkdown(serviceUrl: string): string {
  return `# 智能音频测试平台 Skill

本 skill 让外部 agent（Claude Code / Codex 等）经 skill / MCP 调用智能音频测试平台的业务能力。

## 前置条件
1. 在平台「个人中心 → Access Token」创建访问令牌（仅创建时明文显示一次，\`at_\` 开头）。
2. 确认服务地址可达（本包 mcp.json 已按下载时的配置预填）。

## 配置
- 服务地址：${serviceUrl}
- 鉴权：Authorization: Bearer <Access Token>

## 使用步骤
1. 安装本 skill：将 SKILL.md 与 mcp.json 放入 agent 工作区对应目录。
2. 在 mcp.json 中填入你的 Access Token。
3. 在 MCP 客户端中导入 mcp.json 并启用，即可调用平台能力。

## 能力范围
- 覆盖：任务 / 用例 / 音频 / 设备 / 评估 / 报告 / 算法 / 标签 等业务接口。
- 除外：个人信息（个人资料、修改密码、登录态、token 管理本身）与系统设置（用户/权限、系统参数、集成配置）。
`
}

/** 示例 mcp.json（MCP 配置模板，服务地址预填、token 留占位） */
function buildSampleMcpTemplate(serviceUrl: string): string {
  const template = {
    mcpServers: {
      'intelligent-audio-test': {
        url: `${serviceUrl}/api/v1/mcp`,
        headers: {
          Authorization: 'Bearer <YOUR_ACCESS_TOKEN>',
        },
      },
    },
  }
  return JSON.stringify(template, null, 2)
}
