import { createFileRoute, Link } from '@tanstack/react-router'

import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SYSTEM_SETTINGS_VIEW } from '@/components/layout/config/system-settings.config'

/**
 * 系统设置总览 /system-settings（drill-in 视图由侧栏树接管，见
 * layout/config/system-settings.config.ts；正式分区树归 INT-347 卡）。
 */
export const Route = createFileRoute('/_authenticated/system-settings/')({
  component: SystemSettingsIndex,
})

function SystemSettingsIndex() {
  const groups = SYSTEM_SETTINGS_VIEW.getNavGroups()
  return (
    <SectionPageLayout>
      <SectionPageLayout.Title>系统设置</SectionPageLayout.Title>
      <SectionPageLayout.Content>
        <div className='grid gap-4 sm:grid-cols-2'>
          {groups.map((group) => (
            <Card key={group.id ?? group.title}>
              <CardHeader>
                <CardTitle>{group.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className='grid gap-1'>
                  {group.items.map((item) => (
                    <li key={item.url}>
                      <Link
                        to={item.url}
                        className='hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
                      >
                        {item.icon && <item.icon className='size-4 shrink-0' />}
                        {item.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
