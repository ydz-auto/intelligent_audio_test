/**
 * 设置卡片（interfaces 层，对齐 newAPI settings-card 实测）：
 * CardHeader（标题 + 描述）+ CardContent。
 */
import { memo, type ReactNode } from 'react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

type SettingsCardProps = {
  title: string
  description?: string
  children: ReactNode
  className?: string
}

export const SettingsCard = memo(function SettingsCard({
  title,
  description,
  children,
  className,
}: SettingsCardProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
})
