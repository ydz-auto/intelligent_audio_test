/**
 * 分节标题（interfaces 层，对齐 newAPI settings-section 实测）：
 * 母版 A 表单页（SettingsPage suppressSectionHeader=true）隐藏 h3，标题即分区名；
 * 母版 B/C 资源页显示分节标题 + 说明。
 */
import type { HTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { useSuppressSettingsSectionHeader } from './settings-page-context'

type SettingsSectionProps = {
  title?: string
  description?: string
  titleProps?: HTMLAttributes<HTMLHeadingElement>
  children: ReactNode
  className?: string
}

export function SettingsSection(props: SettingsSectionProps) {
  const suppressHeader = useSuppressSettingsSectionHeader()

  return (
    <section className={cn('flex flex-col gap-4', props.className)}>
      {!suppressHeader && props.title && (
        <div className='flex flex-col gap-1'>
          <h3
            {...props.titleProps}
            className={cn('text-base font-semibold', props.titleProps?.className)}
          >
            {props.title}
          </h3>
          {props.description && (
            <p className='text-muted-foreground text-sm'>{props.description}</p>
          )}
        </div>
      )}
      {props.children}
    </section>
  )
}
