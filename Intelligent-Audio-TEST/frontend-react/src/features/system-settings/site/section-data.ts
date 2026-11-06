/**
 * 站点设置域分区常量（interfaces 层，INT-347 §3.2/§6）：
 * 站点信息 / 站点公告 / 导航模块；域门槛 user:read（admin 口径，无独立权限码）。
 */
export const SITE_SECTIONS = [
  { id: 'info', title: '站点信息' },
  { id: 'notice', title: '站点公告' },
  { id: 'navigation', title: '导航模块' },
] as const

export type SiteSectionId = (typeof SITE_SECTIONS)[number]['id']

export const SITE_SECTION_IDS = SITE_SECTIONS.map((s) => s.id) as [
  SiteSectionId,
  ...SiteSectionId[],
]

export const SITE_DEFAULT_SECTION = 'info'
