/**
 * 用户与权限域分区常量（interfaces 层，INT-347 §3.2/§4.4）：
 * 用户管理 / 角色权限管理；域门槛 user:read。
 */
export const IAM_SECTIONS = [
  { id: 'users', title: '用户管理' },
  { id: 'roles', title: '角色权限管理' },
] as const

export type IamSectionId = (typeof IAM_SECTIONS)[number]['id']

export const IAM_SECTION_IDS = IAM_SECTIONS.map((s) => s.id) as [
  IamSectionId,
  ...IamSectionId[],
]

export const IAM_DEFAULT_SECTION = 'users'
