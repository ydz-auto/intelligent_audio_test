/**
 * 用户与权限域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  IAM_DEFAULT_SECTION,
  IAM_SECTIONS,
  type IamSectionId,
} from './section-data'

export { IAM_DEFAULT_SECTION, IAM_SECTION_IDS } from './section-data'
export type { IamSectionId } from './section-data'

const UsersPage = lazy(() =>
  import('./users-page').then((module) => ({ default: module.UsersPage }))
)
const RolesPage = lazy(() =>
  import('./roles-page').then((module) => ({ default: module.RolesPage }))
)

const IAM_SECTION_BUILDERS: Record<
  IamSectionId,
  SectionDefinition<IamSectionId, SystemOptions>['build']
> = {
  users: () => <UsersPage />,
  roles: () => <RolesPage />,
}

const iamRegistry = createSectionRegistry<IamSectionId, SystemOptions>({
  sections: IAM_SECTIONS.map((section) => ({
    ...section,
    build: IAM_SECTION_BUILDERS[section.id],
  })),
  defaultSection: IAM_DEFAULT_SECTION,
  basePath: '/system-settings/iam',
})

export const getIamSectionNavItems = iamRegistry.getSectionNavItems
export const getIamSectionContent = iamRegistry.getSectionContent
export const getIamSectionMeta = iamRegistry.getSectionMeta
export const getIamSectionIds = iamRegistry.getSectionIds
export const getIamDefaultSection = iamRegistry.getDefaultSection
