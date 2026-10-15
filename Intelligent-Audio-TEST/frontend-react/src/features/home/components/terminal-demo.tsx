import { CopyButton } from '@/components/copy-button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

import { PROGRESS_EXAMPLE, SSE_EXAMPLE } from '../constants'

/**
 * 终端演示卡（照 newAPI hero-terminal-demo.tsx 版式，03_首页.md §3.6）：
 * line 页签 + 三圆点装饰 + method 行 + CopyButton + 深底代码区
 * （bg-[#101c30] 浅深同值——代码块语义色，规范 §4 唯一硬点豁免）。
 */
export function TerminalDemo({ className }: { className?: string }) {
  const examples = [PROGRESS_EXAMPLE, SSE_EXAMPLE]
  return (
    <Tabs
      defaultValue={PROGRESS_EXAMPLE.id}
      className={cn(
        'min-w-0 gap-0 overflow-hidden rounded-2xl border bg-card shadow-xl',
        className
      )}
    >
      <div className='flex items-center justify-between gap-3 border-b px-4 py-3'>
        <TabsList
          aria-label='接口示例'
          variant='line'
          className='h-auto flex-wrap'
        >
          {examples.map((example) => (
            <TabsTrigger
              key={example.id}
              value={example.id}
              className='px-3 py-2'
            >
              {example.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <span aria-hidden='true' className='hidden gap-1.5 sm:flex'>
          <span className='bg-muted-foreground/20 size-2 rounded-full' />
          <span className='bg-muted-foreground/20 size-2 rounded-full' />
          <span className='bg-primary/60 size-2 rounded-full' />
        </span>
      </div>
      {examples.map((example) => (
        <TabsContent key={example.id} value={example.id} className='mt-0 min-w-0'>
          <div className='bg-muted/30 flex min-w-0 items-center gap-2 border-b px-5 py-3'>
            <span className='text-primary font-mono text-xs font-semibold'>
              {example.method}
            </span>
            <code className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>
              {example.endpoint}
            </code>
            <CopyButton
              value={example.code}
              aria-label='复制代码'
              className='size-7'
            />
          </div>
          <pre className='h-80 overflow-auto bg-[#101c30] p-5 font-mono text-xs leading-7 text-blue-100 sm:text-[13px]'>
            <code>{example.code}</code>
          </pre>
        </TabsContent>
      ))}
      <p className='text-muted-foreground px-5 py-4 text-xs leading-5'>
        示例中的地址与任务 ID 请替换为你的实际环境；完整错误码见 API 手册。
      </p>
    </Tabs>
  )
}
