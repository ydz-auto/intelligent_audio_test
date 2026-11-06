/**
 * 连接你的 agent 入口页常量（features/agent-connect，INT-1153/INT-1140 方案 2）。
 * 文案全中文硬编码（AGENTS.md §3.1）；页面含使用说明 / skill 服务地址配置（默认取
 * 浏览器地址栏，可编辑）/ Access Token 指引（跳 /profile）/ 炫彩「下载 skill」按钮。
 */

export const AGENT_CONNECT_PAGE_TITLE = '连接你的 agent'
export const AGENT_CONNECT_PAGE_DESCRIPTION =
  '让外部 agent（Claude Code / Codex 等）经 skill / MCP 调用本平台的智能音频测试能力。'

/** 使用说明 */
export const AGENT_CONNECT_USAGE_TITLE = '使用说明'
export const AGENT_CONNECT_USAGE_DESCRIPTION =
  '三步接入外部 agent：创建 Access Token → 配置服务地址 → 下载并安装 skill。'
export const AGENT_CONNECT_STEPS: {
  key: string
  title: string
  description: string
  link?: string
  linkLabel?: string
}[] = [
  {
    key: 'token',
    title: '创建 Access Token',
    description:
      '前往「个人中心 → Access Token」创建令牌，按需勾选业务权限与有效时间。Token 明文只显示一次，请立即复制保存。',
    link: '/profile',
    linkLabel: '前往个人中心',
  },
  {
    key: 'url',
    title: '配置服务地址',
    description:
      'skill 内嵌的服务地址默认取当前浏览器地址栏（IP 或 http(s) 链接），可按下表修改以适配你的网络环境。',
  },
  {
    key: 'skill',
    title: '下载并安装 skill',
    description:
      '点击下方「下载 skill」按钮获取 ZIP 包，按包内 SKILL.md 说明把 skill / MCP 配置安装到外部 agent。',
  },
] as const

/** skill 服务地址 */
export const AGENT_CONNECT_URL_TITLE = 'Skill 服务地址'
export const AGENT_CONNECT_URL_DESCRIPTION =
  '外部 agent 访问本平台的地址。默认取当前浏览器地址栏，可按部署环境（IP / 域名 / 端口）修改。'
export const AGENT_CONNECT_URL_PLACEHOLDER = '例如：http://192.168.1.100:5000'
export const AGENT_CONNECT_URL_VALIDATE_ERROR = '请输入有效的 http(s) 地址'

/** Access Token 指引 */
export const AGENT_CONNECT_TOKEN_TITLE = 'Access Token'
export const AGENT_CONNECT_TOKEN_DESCRIPTION =
  '外部 agent 经 skill / MCP 调用平台能力时需要 Access Token 鉴权。'
export const AGENT_CONNECT_TOKEN_GO_PROFILE = '前往个人中心创建 / 管理 Access Token'

/** 下载 skill */
export const AGENT_CONNECT_DOWNLOAD_TITLE = '下载 skill'
export const AGENT_CONNECT_DOWNLOAD_BUTTON = '下载 skill'
export const AGENT_CONNECT_DOWNLOADING = '正在生成…'
export const AGENT_CONNECT_DOWNLOAD_ARIA = '下载智能音频测试 skill 包'
export const AGENT_CONNECT_DOWNLOAD_SUCCESS = 'skill 包已开始下载'
export const AGENT_CONNECT_DOWNLOAD_ERROR =
  '下载失败，请检查服务地址后重试；若后端 skill 端点尚未部署，可稍后再试。'
