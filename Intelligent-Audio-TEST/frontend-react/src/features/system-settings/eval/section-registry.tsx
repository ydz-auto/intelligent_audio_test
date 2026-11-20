/**
 * 评估服务域分区注册器（interfaces 层）：createSectionRegistry 实例 + lazy 构建器。
 * settings = 系统选项 KV（SettingsPage resolveSettings 传入）。
 */
import { lazy } from 'react'

import type { SystemOptions } from '@/domain/models/option'
import {
  resolveEvalAsrSettings,
  resolveEvalLlmSettings,
  resolveEvalRelaySettings,
} from '@/domain/models/evalSettings'
import {
  createSectionRegistry,
  type SectionDefinition,
} from '../utils/section-registry'

import {
  EVAL_DEFAULT_SECTION,
  EVAL_SECTIONS,
  type EvalSectionId,
} from './section-data'

export { EVAL_DEFAULT_SECTION, EVAL_SECTION_IDS } from './section-data'
export type { EvalSectionId } from './section-data'

const EvalLlmPage = lazy(() =>
  import('./llm-page').then((module) => ({ default: module.EvalLlmPage }))
)
const EvalAsrPage = lazy(() =>
  import('./asr-page').then((module) => ({ default: module.EvalAsrPage }))
)
const EvalRelayPage = lazy(() =>
  import('./relay-page').then((module) => ({ default: module.EvalRelayPage }))
)

const EVAL_SECTION_BUILDERS: Record<
  EvalSectionId,
  SectionDefinition<EvalSectionId, SystemOptions>['build']
> = {
  llm: (settings) => (
    <EvalLlmPage defaultValues={resolveEvalLlmSettings(settings)} />
  ),
  asr: (settings) => (
    <EvalAsrPage defaultValues={resolveEvalAsrSettings(settings)} />
  ),
  relay: (settings) => (
    <EvalRelayPage defaultValues={resolveEvalRelaySettings(settings)} />
  ),
}

const evalRegistry = createSectionRegistry<EvalSectionId, SystemOptions>({
  sections: EVAL_SECTIONS.map((section) => ({
    ...section,
    build: EVAL_SECTION_BUILDERS[section.id],
  })),
  defaultSection: EVAL_DEFAULT_SECTION,
  basePath: '/system-settings/eval',
})

export const getEvalSectionNavItems = evalRegistry.getSectionNavItems
export const getEvalSectionContent = evalRegistry.getSectionContent
export const getEvalSectionMeta = evalRegistry.getSectionMeta
export const getEvalSectionIds = evalRegistry.getSectionIds
export const getEvalDefaultSection = evalRegistry.getDefaultSection
