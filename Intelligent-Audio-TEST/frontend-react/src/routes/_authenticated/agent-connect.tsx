import { createFileRoute } from '@tanstack/react-router'

import { AgentConnectPage } from '@/features/agent-connect'

/**
 * /agent-connect 连接你的 agent 入口页（INT-1153/INT-1140 方案 2）：
 * 登录壳 _authenticated 组内页面，无权限码 meta（登录即可，00 总表 §2.1）；
 * 导航「连接你的 agent」炫彩按钮与侧栏项均指向此处。
 * 浏览器标题「连接你的 agent」由页面组件设置。
 */
export const Route = createFileRoute('/_authenticated/agent-connect')({
  component: AgentConnectPage,
})
