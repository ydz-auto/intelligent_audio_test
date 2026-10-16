/**
 * 安全设置域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import { resolveAccessControlSettings } from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  SECURITY_DEFAULT_SECTION,
  SECURITY_SECTIONS,
  type SecuritySectionId,
} from './section-data'

export { SECURITY_DEFAULT_SECTION, SECURITY_SECTION_IDS } from './section-data'
export type { SecuritySectionId } from './section-data'

const AccessControlPage = lazy(() =>
  import('./access-control-page').then((module) => ({
    default: module.AccessControlPage,
  }))
)

const SECURITY_SECTION_BUILDERS: Record<
  SecuritySectionId,
  SectionDefinition<SecuritySectionId, SystemOptions>['build']
> = {
  'access-control': (settings) => (
    <AccessControlPage defaultValues={resolveAccessControlSettings(settings)} />
  ),
}

const securityRegistry = createSectionRegistry<SecuritySectionId, SystemOptions>({
  sections: SECURITY_SECTIONS.map((section) => ({
    ...section,
    build: SECURITY_SECTION_BUILDERS[section.id],
  })),
  defaultSection: SECURITY_DEFAULT_SECTION,
  basePath: '/system-settings/security',
})

export const getSecuritySectionNavItems = securityRegistry.getSectionNavItems
export const getSecuritySectionContent = securityRegistry.getSectionContent
export const getSecuritySectionMeta = securityRegistry.getSectionMeta
export const getSecuritySectionIds = securityRegistry.getSectionIds
export const getSecurityDefaultSection = securityRegistry.getDefaultSection
