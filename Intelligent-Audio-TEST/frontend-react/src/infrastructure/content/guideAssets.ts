import userGuideMarkdown from '@/features/user-guide/content/使用手册.md?raw'
import apiGuideMarkdown from '@/features/user-guide/content/API手册.md?raw'
import integrationGuideMarkdown from '@/features/user-guide/content/接入指南.md?raw'

/**
 * 平台使用手册正文（infrastructure 层，构建期 ?raw 静态资产）。
 * 07_文档.md §4.1：本平台站内单语言中文，不建多语言 content 目录；
 * getDocumentLanguage 固化返回 zh（机制保留以便将来扩展）。
 */
export const USER_GUIDE_DOCUMENT = userGuideMarkdown

/** 平台 API 手册正文（构建期 ?raw 静态资产） */
export const API_GUIDE_DOCUMENT = apiGuideMarkdown

/** 接入指南正文（构建期 ?raw 静态资产；Realtime/HTTP/设备三章，源稿 doc/接入指南_*.md） */
export const INTEGRATION_GUIDE_DOCUMENT = integrationGuideMarkdown
