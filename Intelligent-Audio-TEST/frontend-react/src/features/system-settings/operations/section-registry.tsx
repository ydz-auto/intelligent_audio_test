/**
 * 运维设置域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 * 日志维护分区 = 母版 A 保留天数 + 归档管理小节（§4.7）。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import { resolveLogMaintenanceSettings } from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  OPERATIONS_DEFAULT_SECTION,
  OPERATIONS_SECTIONS,
  type OperationsSectionId,
} from './section-data'

export { OPERATIONS_DEFAULT_SECTION, OPERATIONS_SECTION_IDS } from './section-data'
export type { OperationsSectionId } from './section-data'

const LogMaintenancePage = lazy(() =>
  import('./log-maintenance-page').then((module) => ({
    default: module.LogMaintenancePage,
  }))
)

const OPERATIONS_SECTION_BUILDERS: Record<
  OperationsSectionId,
  SectionDefinition<OperationsSectionId, SystemOptions>['build']
> = {
  'log-maintenance': (settings) => (
    <LogMaintenancePage
      defaultValues={resolveLogMaintenanceSettings(settings)}
    />
  ),
}

const operationsRegistry = createSectionRegistry<
  OperationsSectionId,
  SystemOptions
>({
  sections: OPERATIONS_SECTIONS.map((section) => ({
    ...section,
    build: OPERATIONS_SECTION_BUILDERS[section.id],
  })),
  defaultSection: OPERATIONS_DEFAULT_SECTION,
  basePath: '/system-settings/operations',
})

export const getOperationsSectionNavItems =
  operationsRegistry.getSectionNavItems
export const getOperationsSectionContent =
  operationsRegistry.getSectionContent
export const getOperationsSectionMeta = operationsRegistry.getSectionMeta
export const getOperationsSectionIds = operationsRegistry.getSectionIds
export const getOperationsDefaultSection = operationsRegistry.getDefaultSection
