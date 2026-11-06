/**
 * 外观与主题域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 * 两分区即时生效（共用 useThemeCustomization），无保存按钮，settings 参数不使用。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  APPEARANCE_DEFAULT_SECTION,
  APPEARANCE_SECTIONS,
  type AppearanceSectionId,
} from './section-data'

export { APPEARANCE_DEFAULT_SECTION, APPEARANCE_SECTION_IDS } from './section-data'
export type { AppearanceSectionId } from './section-data'

const ThemePresetsPage = lazy(() =>
  import('./presets-page').then((module) => ({
    default: module.ThemePresetsPage,
  }))
)
const AppearanceFineTuningPage = lazy(() =>
  import('./fine-tuning-page').then((module) => ({
    default: module.AppearanceFineTuningPage,
  }))
)

const APPEARANCE_SECTION_BUILDERS: Record<
  AppearanceSectionId,
  SectionDefinition<AppearanceSectionId, SystemOptions>['build']
> = {
  presets: () => <ThemePresetsPage />,
  'fine-tuning': () => <AppearanceFineTuningPage />,
}

const appearanceRegistry = createSectionRegistry<
  AppearanceSectionId,
  SystemOptions
>({
  sections: APPEARANCE_SECTIONS.map((section) => ({
    ...section,
    build: APPEARANCE_SECTION_BUILDERS[section.id],
  })),
  defaultSection: APPEARANCE_DEFAULT_SECTION,
  basePath: '/system-settings/appearance',
})

export const getAppearanceSectionNavItems =
  appearanceRegistry.getSectionNavItems
export const getAppearanceSectionContent = appearanceRegistry.getSectionContent
export const getAppearanceSectionMeta = appearanceRegistry.getSectionMeta
export const getAppearanceSectionIds = appearanceRegistry.getSectionIds
export const getAppearanceDefaultSection = appearanceRegistry.getDefaultSection
