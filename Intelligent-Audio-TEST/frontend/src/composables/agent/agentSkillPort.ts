// -*- coding: utf-8 -*-
/**
 * Agent Skill 域 Application Port —— 下载智能音频测试 skill 包的唯一入口。
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 agentSkillApi 的直通薄封装；views 禁止直连 @/infrastructure/api。
 */
import { agentSkillApi, SKILL_DOWNLOAD_FILENAME } from '../../infrastructure/api'

export const agentSkillPort = agentSkillApi

/** skill 包下载文件名（与 agentSkillApi 同源，供视图提示用） */
export { SKILL_DOWNLOAD_FILENAME }
