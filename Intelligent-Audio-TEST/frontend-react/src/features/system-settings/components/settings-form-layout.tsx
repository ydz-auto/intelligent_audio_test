/**
 * 设置表单栅格/开关行（interfaces 层，对齐 newAPI settings-form-layout 实测）：
 * - SettingsFormGrid：`grid gap-y-6 lg:grid-cols-2`，开关行/textarea 自动跨双列；
 * - SettingsSwitchField：`flex flex-row items-center justify-between gap-4 py-2.5`
 *   左 Label+Description 右 Switch；
 * - SettingsControlGroup：`bg-muted/20 rounded-xl border px-3 py-2.5` 包联动输入行；
 * - SettingsControlChildren：左侧竖线缩进。
 */
import type { ComponentProps, ReactNode } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

type SettingsFormGridProps = {
  children: ReactNode
  className?: string
}

type SettingsFormGridItemProps = SettingsFormGridProps & {
  span?: 'default' | 'full'
}

type SettingsSwitchFieldProps = ComponentProps<'div'> & {
  controlId?: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
}

const settingsSwitchRowClassName =
  'flex min-w-0 flex-row items-center justify-between gap-4 py-2.5'

export function SettingsFormGrid(props: SettingsFormGridProps) {
  return (
    <div
      data-settings-form-span='full'
      className={cn(
        'grid min-w-0 gap-x-5 gap-y-6 lg:grid-cols-2',
        'lg:[&>[data-settings-form-span=full]]:col-span-2',
        '[&>[data-slot=form-item]]:min-w-0',
        'lg:[&>[data-slot=form-item]:has(textarea)]:col-span-2',
        'lg:[&>[data-slot=form-item]:has([data-slot=switch])]:col-span-2',
        props.className
      )}
    >
      {props.children}
    </div>
  )
}

export function SettingsFormGridItem(props: SettingsFormGridItemProps) {
  return (
    <div
      data-settings-form-span={props.span === 'full' ? 'full' : undefined}
      className={cn(
        'min-w-0',
        props.span === 'full' && 'lg:col-span-2',
        props.className
      )}
    >
      {props.children}
    </div>
  )
}

export function SettingsSwitchContent(props: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0 space-y-0.5', props.className)}>{props.children}</div>
  )
}

export function SettingsSwitchField(props: SettingsSwitchFieldProps) {
  const {
    controlId,
    checked,
    onCheckedChange,
    label,
    description,
    disabled,
    className,
    ...rest
  } = props
  return (
    <div
      data-settings-form-span='full'
      className={cn(settingsSwitchRowClassName, className)}
      {...rest}
    >
      <SettingsSwitchContent>
        <Label htmlFor={controlId} className='text-sm font-medium'>
          {label}
        </Label>
        {description && (
          <p
            id={controlId ? `${controlId}-description` : undefined}
            className='text-muted-foreground text-xs'
          >
            {description}
          </p>
        )}
      </SettingsSwitchContent>
      <Switch
        id={controlId}
        aria-describedby={
          controlId && description ? `${controlId}-description` : undefined
        }
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      />
    </div>
  )
}

export function SettingsControlGroup(props: ComponentProps<'div'>) {
  return (
    <div
      data-settings-form-span='full'
      className={cn(
        'bg-muted/20 min-w-0 space-y-3 rounded-xl border px-3 py-2.5',
        props.className
      )}
      {...props}
    />
  )
}

export function SettingsControlChildren(props: ComponentProps<'div'>) {
  return (
    <div
      className={cn('border-border/70 ml-2 min-w-0 border-l pl-3', props.className)}
      {...props}
    />
  )
}
