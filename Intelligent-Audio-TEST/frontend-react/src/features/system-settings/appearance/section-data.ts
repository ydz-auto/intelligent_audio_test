/**
 * 外观与主题域分区常量（interfaces 层，INT-347 §3.2/§4.6）：
 * 主题预设 / 外观微调；全员登录用户（个人偏好，无资源写权限，无权限码门槛）。
 */
export const APPEARANCE_SECTIONS = [
  { id: 'presets', title: '主题预设' },
  { id: 'fine-tuning', title: '外观微调' },
] as const

export type AppearanceSectionId = (typeof APPEARANCE_SECTIONS)[number]['id']

export const APPEARANCE_SECTION_IDS = APPEARANCE_SECTIONS.map(
  (s) => s.id
) as [AppearanceSectionId, ...AppearanceSectionId[]]

export const APPEARANCE_DEFAULT_SECTION = 'presets'
