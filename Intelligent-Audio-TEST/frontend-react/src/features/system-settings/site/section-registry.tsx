/**
 * 站点设置域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 * settings = 系统选项 KV（SettingsPage resolveSettings 传入），各分区自行解析类型化值。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import {
  resolveSiteInfoSettings,
  resolveSiteNavigationSettings,
  resolveSiteNoticeSettings,
} from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  SITE_DEFAULT_SECTION,
  SITE_SECTIONS,
  type SiteSectionId,
} from './section-data'

export { SITE_DEFAULT_SECTION, SITE_SECTION_IDS } from './section-data'
export type { SiteSectionId } from './section-data'

const SiteInfoPage = lazy(() =>
  import('./info-page').then((module) => ({ default: module.SiteInfoPage }))
)
const SiteNoticePage = lazy(() =>
  import('./notice-page').then((module) => ({ default: module.SiteNoticePage }))
)
const SiteNavigationPage = lazy(() =>
  import('./navigation-page').then((module) => ({
    default: module.SiteNavigationPage,
  }))
)

const SITE_SECTION_BUILDERS: Record<
  SiteSectionId,
  SectionDefinition<SiteSectionId, SystemOptions>['build']
> = {
  info: (settings) => (
    <SiteInfoPage defaultValues={resolveSiteInfoSettings(settings)} />
  ),
  notice: (settings) => (
    <SiteNoticePage defaultValues={resolveSiteNoticeSettings(settings)} />
  ),
  navigation: (settings) => (
    <SiteNavigationPage defaultValues={resolveSiteNavigationSettings(settings)} />
  ),
}

const siteRegistry = createSectionRegistry<SiteSectionId, SystemOptions>({
  sections: SITE_SECTIONS.map((section) => ({
    ...section,
    build: SITE_SECTION_BUILDERS[section.id],
  })),
  defaultSection: SITE_DEFAULT_SECTION,
  basePath: '/system-settings/site',
})

export const getSiteSectionNavItems = siteRegistry.getSectionNavItems
export const getSiteSectionContent = siteRegistry.getSectionContent
export const getSiteSectionMeta = siteRegistry.getSectionMeta
export const getSiteSectionIds = siteRegistry.getSectionIds
export const getSiteDefaultSection = siteRegistry.getDefaultSection
