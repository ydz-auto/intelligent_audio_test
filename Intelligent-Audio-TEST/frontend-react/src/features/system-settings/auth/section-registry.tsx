/**
 * 认证设置域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 * OAuth 提供方分区持 auth:manage_provider 独立分区门槛（分区级路由守卫与侧栏过滤共用）。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import { resolveAuthMethodSettings } from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  AUTH_DEFAULT_SECTION,
  AUTH_SECTIONS,
  type AuthSectionId,
} from './section-data'

export { AUTH_DEFAULT_SECTION, AUTH_SECTION_IDS } from './section-data'
export type { AuthSectionId } from './section-data'

const AuthMethodsPage = lazy(() =>
  import('./methods-page').then((module) => ({
    default: module.AuthMethodsPage,
  }))
)
const OAuthProvidersPage = lazy(() =>
  import('./oauth-providers-page').then((module) => ({
    default: module.OAuthProvidersPage,
  }))
)

const AUTH_SECTION_BUILDERS: Record<
  AuthSectionId,
  SectionDefinition<AuthSectionId, SystemOptions>['build']
> = {
  methods: (settings) => (
    <AuthMethodsPage defaultValues={resolveAuthMethodSettings(settings)} />
  ),
  'oauth-providers': () => <OAuthProvidersPage />,
}

const authRegistry = createSectionRegistry<AuthSectionId, SystemOptions>({
  sections: AUTH_SECTIONS.map((section) => ({
    ...section,
    build: AUTH_SECTION_BUILDERS[section.id],
  })),
  defaultSection: AUTH_DEFAULT_SECTION,
  basePath: '/system-settings/auth',
})

export const getAuthSectionNavItems = authRegistry.getSectionNavItems
export const getAuthSectionContent = authRegistry.getSectionContent
export const getAuthSectionMeta = authRegistry.getSectionMeta
export const getAuthSectionIds = authRegistry.getSectionIds
export const getAuthDefaultSection = authRegistry.getDefaultSection
