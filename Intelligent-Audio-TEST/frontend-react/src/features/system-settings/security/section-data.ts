/**
 * 安全设置域分区常量（interfaces 层，INT-347 §3.2/§6）：
 * 访问控制（预留壳，随后端能力补齐）；域门槛 admin（随 user:read 口径）。
 */
export const SECURITY_SECTIONS = [
  { id: 'access-control', title: '访问控制' },
] as const

export type SecuritySectionId = (typeof SECURITY_SECTIONS)[number]['id']

export const SECURITY_SECTION_IDS = SECURITY_SECTIONS.map((s) => s.id) as [
  SecuritySectionId,
  ...SecuritySectionId[],
]

export const SECURITY_DEFAULT_SECTION = 'access-control'
