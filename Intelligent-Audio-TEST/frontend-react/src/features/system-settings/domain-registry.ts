/**
 * 域 → 分区注册器索引（interfaces 层）：路由层按 domain 参数取分区内容/元信息。
 * 各域 registry 的 TSectionId 不同，统一收窄为 (id: string, settings) 签名。
 */
import type { ReactNode } from 'react'

import type { SystemOptions } from '@/domain/models/option'

import { getAuthDefaultSection, getAuthSectionContent, getAuthSectionMeta, type AuthSectionId } from './auth/section-registry'
import { getAppearanceDefaultSection, getAppearanceSectionContent, getAppearanceSectionMeta, type AppearanceSectionId } from './appearance/section-registry'
import { getIamDefaultSection, getIamSectionContent, getIamSectionMeta, type IamSectionId } from './iam/section-registry'
import { getOperationsDefaultSection, getOperationsSectionContent, getOperationsSectionMeta, type OperationsSectionId } from './operations/section-registry'
import { getSecurityDefaultSection, getSecuritySectionContent, getSecuritySectionMeta, type SecuritySectionId } from './security/section-registry'
import { getSiteDefaultSection, getSiteSectionContent, getSiteSectionMeta, type SiteSectionId } from './site/section-registry'

type DomainRegistry = {
  getSectionContent: (sectionId: string, settings: SystemOptions) => ReactNode
  getSectionMeta: (sectionId: string) => { title: string }
  getDefaultSection: () => string
}

export const SETTINGS_DOMAIN_REGISTRY: Record<string, DomainRegistry> = {
  site: {
    getSectionContent: (id, settings) =>
      getSiteSectionContent(id as SiteSectionId, settings),
    getSectionMeta: (id) => getSiteSectionMeta(id as SiteSectionId),
    getDefaultSection: () => getSiteDefaultSection(),
  },
  iam: {
    getSectionContent: (id, settings) =>
      getIamSectionContent(id as IamSectionId, settings),
    getSectionMeta: (id) => getIamSectionMeta(id as IamSectionId),
    getDefaultSection: () => getIamDefaultSection(),
  },
  auth: {
    getSectionContent: (id, settings) =>
      getAuthSectionContent(id as AuthSectionId, settings),
    getSectionMeta: (id) => getAuthSectionMeta(id as AuthSectionId),
    getDefaultSection: () => getAuthDefaultSection(),
  },
  appearance: {
    getSectionContent: (id, settings) =>
      getAppearanceSectionContent(id as AppearanceSectionId, settings),
    getSectionMeta: (id) => getAppearanceSectionMeta(id as AppearanceSectionId),
    getDefaultSection: () => getAppearanceDefaultSection(),
  },
  security: {
    getSectionContent: (id, settings) =>
      getSecuritySectionContent(id as SecuritySectionId, settings),
    getSectionMeta: (id) => getSecuritySectionMeta(id as SecuritySectionId),
    getDefaultSection: () => getSecurityDefaultSection(),
  },
  operations: {
    getSectionContent: (id, settings) =>
      getOperationsSectionContent(id as OperationsSectionId, settings),
    getSectionMeta: (id) => getOperationsSectionMeta(id as OperationsSectionId),
    getDefaultSection: () => getOperationsDefaultSection(),
  },
}
