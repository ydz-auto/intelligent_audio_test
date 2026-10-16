import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CopyButton } from '@/components/copy-button'
import { cn } from '@/lib/utils'

import { TEST_OBJECT_ACCESS } from '../constants'

/**
 * 接入演示卡（03_首页.md §3.6 右列，照 newAPI hero-terminal-demo.tsx 外壳）：
 * 顶部 TabsList variant='line' + 三圆点装饰，每页签=请求行（method + endpoint + CopyButton）
 * + 终端底色代码区；示例值一律标注「示例数据」，禁止杜撰真实端点。
 */
export function AccessDemo({ className }: { className?: string }) {
  const tabs = TEST_OBJECT_ACCESS.demoTabs

  return (
    <Tabs
      defaultValue={tabs[0].id}
      className={cn(
        'min-w-0 gap-0 overflow-hidden rounded-2xl border bg-card shadow-xl shadow-blue-950/5',
        className
      )}
    >
      <div className='flex items-center justify-between gap-3 border-b px-4 py-3'>
        <TabsList
          aria-label='接入演示'
          variant='line'
          className='h-auto flex-wrap'
        >
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className='px-3 py-2'
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <span aria-hidden='true' className='hidden gap-1.5 sm:flex'>
          <span className='bg-muted-foreground/20 size-2 rounded-full' />
          <span className='bg-muted-foreground/20 size-2 rounded-full' />
          <span className='bg-primary/60 size-2 rounded-full' />
        </span>
      </div>
      {tabs.map((tab) => (
        <TabsContent
          key={tab.id}
          value={tab.id}
          className='mt-0 min-w-0'
        >
          <div className='bg-muted/30 flex min-w-0 items-center gap-2 border-b px-5 py-3'>
            <span className='text-primary font-mono text-xs font-semibold dark:text-primary'>
              {tab.method === '—' ? tab.group : tab.method}
            </span>
            <code className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>
              {tab.endpoint}
            </code>
            <CopyButton
              value={tab.code}
              aria-label='复制代码'
              className='size-7'
            />
          </div>
          <pre className='bg-[#101c30] text-blue-100 h-80 overflow-auto p-5 font-mono text-xs leading-7 sm:text-[13px]'>
            <code>{tab.code}</code>
          </pre>
        </TabsContent>
      ))}
      <p className='text-muted-foreground px-5 py-4 text-xs leading-5'>
        {TEST_OBJECT_ACCESS.demoNote}
      </p>
    </Tabs>
  )
}
