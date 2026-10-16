/**
 * 设置页 Portal 上下文（interfaces 层，对齐 newAPI settings-page-context 实测）：
 * 动作区按钮与标题旁状态位经 createPortal 挂到页头（SectionPageLayout 槽位）。
 */
import {
  createContext,
  useContext,
  type ComponentProps,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { RotateCcw, Save } from 'lucide-react'

type SettingsPageContextValue = {
  actionsContainer: HTMLDivElement | null
  titleStatusContainer: HTMLSpanElement | null
  /** 多分区表单页（母版 A）头部分节隐藏，标题即分区名 */
  suppressSectionHeader: boolean
}

const SettingsPageContext = createContext<SettingsPageContextValue>({
  actionsContainer: null,
  titleStatusContainer: null,
  suppressSectionHeader: true,
})

export function SettingsPageProvider(props: {
  actionsContainer: HTMLDivElement | null
  titleStatusContainer?: HTMLSpanElement | null
  suppressSectionHeader?: boolean
  children: ReactNode
}) {
  return (
    <SettingsPageContext.Provider
      value={{
        actionsContainer: props.actionsContainer,
        titleStatusContainer: props.titleStatusContainer ?? null,
        suppressSectionHeader: props.suppressSectionHeader ?? true,
      }}
    >
      {props.children}
    </SettingsPageContext.Provider>
  )
}

export function useSuppressSettingsSectionHeader() {
  return useContext(SettingsPageContext).suppressSectionHeader
}

export function SettingsPageTitleStatusPortal(props: { children: ReactNode }) {
  const { titleStatusContainer } = useContext(SettingsPageContext)
  if (!titleStatusContainer) return null
  return createPortal(props.children, titleStatusContainer)
}

export function SettingsPageActionsPortal(props: { children: ReactNode }) {
  const { actionsContainer } = useContext(SettingsPageContext)
  if (!actionsContainer) return null
  return createPortal(
    <div className='flex flex-wrap items-center justify-end gap-2'>
      {props.children}
    </div>,
    actionsContainer
  )
}

export type SettingsPageFormActionsProps = {
  onSave: () => void
  onReset?: () => void
  isSaving?: boolean
  isSaveDisabled?: boolean
  isResetDisabled?: boolean
  saveLabel?: string
  savingLabel?: string
  resetLabel?: string
  resetVariant?: ComponentProps<typeof Button>['variant']
}

/** 表单动作区（重置/保存，经 Portal 送上页头，文案全中文 §6） */
export function SettingsPageFormActions(props: SettingsPageFormActionsProps) {
  const saveLabel = props.isSaving
    ? (props.savingLabel ?? '保存中…')
    : (props.saveLabel ?? '保存更改')

  return (
    <SettingsPageActionsPortal>
      {props.onReset && (
        <Button
          type='button'
          size='sm'
          variant={props.resetVariant ?? 'outline'}
          onClick={props.onReset}
          disabled={props.isResetDisabled || props.isSaving}
        >
          <RotateCcw data-icon='inline-start' />
          <span>{props.resetLabel ?? '重置'}</span>
        </Button>
      )}
      <Button
        type='button'
        size='sm'
        onClick={props.onSave}
        disabled={props.isSaving || props.isSaveDisabled}
      >
        <Save data-icon='inline-start' />
        <span>{saveLabel}</span>
      </Button>
    </SettingsPageActionsPortal>
  )
}
