/**
 * 未保存标记（interfaces 层，对齐 newAPI form-dirty-indicator 实测）：
 * isDirty 时页头标题旁琥珀圆点徽标「未保存的更改」，经 SettingsPageTitleStatusPortal
 * 挂到页头标题状态位。
 */
import { SettingsPageTitleStatusPortal } from './settings-page-context'

type FormDirtyIndicatorProps = {
  isDirty: boolean
  message?: string
}

export function FormDirtyIndicator({ isDirty, message }: FormDirtyIndicatorProps) {
  if (!isDirty) return null

  return (
    <SettingsPageTitleStatusPortal>
      <span className='ring-amber-500/20 ring-inset inline-flex h-5 items-center gap-1.5 rounded-full bg-amber-500/10 px-2 text-[11px] font-medium whitespace-nowrap text-amber-700 ring-1 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20'>
        <span className='bg-amber-500 dark:bg-amber-300 size-1.5 rounded-full' />
        {message ?? '未保存的更改'}
      </span>
    </SettingsPageTitleStatusPortal>
  )
}
