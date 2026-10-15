import { createFileRoute } from '@tanstack/react-router'

import { SectionPageLayout } from '@/components/layout/components/section-page-layout'

/**
 * 系统设置分区页 /system-settings/$section（占位稿；分区树与页签归 INT-347 卡）。
 */
export const Route = createFileRoute('/_authenticated/system-settings/$section')(
  {
    component: SystemSettingsSection,
  }
)

const SECTION_TITLES: Record<string, string> = {
  site: '站点设置',
  users: '用户管理',
  roles: '角色与权限',
  algorithms: '算法配置',
  evaluation: '评估维度',
  spl: 'SPL 映射',
  tags: '标签管理',
}

function SystemSettingsSection() {
  const { section } = Route.useParams()
  const title = SECTION_TITLES[section] ?? section
  return (
    <SectionPageLayout>
      <SectionPageLayout.Title>{title}</SectionPageLayout.Title>
      <SectionPageLayout.Content>
        <div className='flex min-h-[50vh] flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-8 text-center'>
          <h3 className='text-sm font-medium'>{title}占位稿</h3>
          <p className='text-muted-foreground max-w-md text-sm'>
            {title}的设置分区与表单随 INT-347 设置工作区卡落地。
          </p>
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
