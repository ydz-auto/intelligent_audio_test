/**
 * 分区注册器工厂（interfaces 层 utils，对齐 newAPI section-registry 实测）：
 * nav items / 按 id 取内容 / 分区元信息；URL 风格 path（/system-settings/<域>/<分区>）。
 * 域目录（site|iam|auth|appearance|security|operations）各持一个实例。
 */
import type { ReactNode } from 'react'

export type SectionNavItem = {
  id: string
  title: string
  url: string
  /** 分区级可见性权限（域内独立判定，如 OAuth 提供方需 auth:manage_provider） */
  requiredPermission?: string
  requiredPermissions?: string[]
}

export type SectionMeta = {
  title: string
  /** 分区级权限门槛（路由守卫与侧栏共用） */
  requiredPermission?: string
  requiredPermissions?: string[]
}

export type SectionDefinition<
  TSectionId extends string,
  TSettings,
  TExtraArgs extends unknown[] = [],
> = {
  id: TSectionId
  title: string
  requiredPermission?: string
  requiredPermissions?: string[]
  build: (
    settings: TSettings,
    ...extraArgs: TExtraArgs
  ) => ReactNode
}

export type SectionRegistryOptions<
  TSectionId extends string,
  TSettings,
  TExtraArgs extends unknown[],
> = {
  sections: Array<SectionDefinition<TSectionId, TSettings, TExtraArgs>>
  defaultSection: TSectionId
  /** 域路径前缀，如 '/system-settings/site' */
  basePath: string
}

export function createSectionRegistry<
  TSectionId extends string,
  TSettings,
  TExtraArgs extends unknown[] = [],
>(options: SectionRegistryOptions<TSectionId, TSettings, TExtraArgs>) {
  const sectionMap = new Map(
    options.sections.map((section) => [section.id, section])
  )
  const sectionIds = options.sections.map((section) => section.id)

  return {
    getSectionNavItems: (): SectionNavItem[] =>
      options.sections.map((section) => ({
        id: section.id,
        title: section.title,
        url: `${options.basePath}/${section.id}`,
        requiredPermission: section.requiredPermission,
        requiredPermissions: section.requiredPermissions,
      })),
    getSectionContent: (
      sectionId: TSectionId,
      settings: TSettings,
      ...extraArgs: TExtraArgs
    ): ReactNode => {
      const section = sectionMap.get(sectionId)
      return section ? section.build(settings, ...extraArgs) : null
    },
    getSectionMeta: (sectionId: TSectionId): SectionMeta => {
      const section = sectionMap.get(sectionId)
      return {
        title: section?.title ?? String(sectionId),
        requiredPermission: section?.requiredPermission,
        requiredPermissions: section?.requiredPermissions,
      }
    },
    getSectionIds: (): TSectionId[] => sectionIds,
    getDefaultSection: (): TSectionId => options.defaultSection,
    getSectionById: (sectionId: TSectionId) => sectionMap.get(sectionId),
  }
}

export type SectionRegistry<
  TSectionId extends string,
  TSettings,
  TExtraArgs extends unknown[] = [],
> = ReturnType<typeof createSectionRegistry<TSectionId, TSettings, TExtraArgs>>
