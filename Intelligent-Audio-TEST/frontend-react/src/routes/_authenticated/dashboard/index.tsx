import { createFileRoute } from '@tanstack/react-router'
import { Link } from '@tanstack/react-router'
import { toast } from 'sonner'

import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import { usePermissions } from '@/application/hooks/use-permissions'

/**
 * /dashboard 工作台（home:read；路径拍板见 04_控制台.md §2）。
 * 页面本体（引导卡/概览卡/双面板/任务统计图表三卡）归 INT-346 卡，当前为占位稿；
 * Title 右侧 Actions 仍按规范出：「刷新统计」ghost 钮（home:refresh）+「查看任务」link（task:read）。
 */
export const Route = createFileRoute('/_authenticated/dashboard/')({
  component: DashboardPage,
})

function DashboardPage() {
  const { hasPermission } = usePermissions()

  return (
    <SectionPageLayout>
      <SectionPageLayout.Title>工作台</SectionPageLayout.Title>
      <SectionPageLayout.Actions>
        {hasPermission('home:refresh') && (
          <Button
            variant='ghost'
            size='sm'
            // TODO(API 接线): POST /home/stats/refresh，成功 toast「统计已刷新」
            onClick={() => toast.info('统计已刷新')}
          >
            刷新统计
          </Button>
        )}
        {hasPermission('task:read') && (
          <Button variant='ghost' size='sm' render={<Link to='/tasks' />}>
            查看任务
          </Button>
        )}
      </SectionPageLayout.Actions>
      <SectionPageLayout.Content>
        <div className='flex min-h-[50vh] flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-8 text-center'>
          <h3 className='text-sm font-medium'>工作台占位稿</h3>
          <p className='text-muted-foreground max-w-md text-sm'>
            工作台四分区（引导卡双形态 / 概览卡双区 / 最近任务与分组排行双面板 /
            任务统计图表三卡）随 INT-346 卡落地。
          </p>
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
