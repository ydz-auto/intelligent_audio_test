// -*- coding: utf-8 -*-
/**
 * 「连接你的 agent」入口页 Composable（INT-1193 文案统一；INT-1154 基线）
 *
 * - skill 服务地址：默认取浏览器地址栏（window.location.origin），可改；
 *   localStorage `iatp:agent-connect:v1` 持久化，下载 skill 包时预填进包内 MCP 模板。
 * - 下载：经基础设施层 agentSkillApi 取 zip（真实 GET /api/v1/agent/skill，
 *   服务地址经 ?base_url= 注入包内 MCP 模板）。
 */
import { ref } from 'vue'
import { downloadSkillPackage } from '../../infrastructure/api/agentSkillApi'
import type { DownloadSkillOptions } from '../../infrastructure/api/agentSkillApi'

const AGENT_CONNECT_STORAGE_KEY = 'iatp:agent-connect:v1'

export function useAgentConnect() {
  /** 当前配置的 skill 服务地址（默认浏览器地址栏） */
  const serviceUrl = ref<string>(loadServiceUrl())

  /** 保存服务地址（trim 后持久化；localStorage 不可用时会话内仍生效） */
  function saveServiceUrl(url: string): void {
    const trimmed = url.trim()
    serviceUrl.value = trimmed
    try {
      localStorage.setItem(AGENT_CONNECT_STORAGE_KEY, trimmed)
    } catch {
      // localStorage 配额/隐私模式：静默失败，不阻断 UI
    }
  }

  /** 下载 skill 包（Blob，调用方负责触发浏览器下载） */
  async function downloadSkill(options: DownloadSkillOptions = {}): Promise<Blob> {
    return downloadSkillPackage({ serviceUrl: serviceUrl.value, ...options })
  }

  return { serviceUrl, saveServiceUrl, downloadSkill }
}

/** 读取存量服务地址；无存量返回浏览器地址栏 origin（默认值） */
function loadServiceUrl(): string {
  let saved = ''
  try {
    saved = localStorage.getItem(AGENT_CONNECT_STORAGE_KEY) ?? ''
  } catch {
    saved = ''
  }
  return saved || window.location.origin
}
