/**
 * 报告查看右导航 scrollspy（本平台阅读版式特色，规范 §4.1）：
 * 锚点列表 + 阅读进度条（h-px bg-primary/40 随滚动填充），点击平滑滚动对应分节。
 * 样式换 newAPI 语义 token：bg-muted/20 + text-xs 锚点 + 激活 text-primary font-medium。
 * 滚动侦测由页面层（ReportViewPage）驱动，本组件纯展示。
 */
import { cn } from '@/lib/utils'

export interface ReadingNavSection {
  id: string
  label: string
}

interface ReportReadingNavProps {
  sections: ReadingNavSection[]
  activeId: string
  progress: number
  onNavigate: (id: string) => void
}

export function ReportReadingNav({
  sections,
  activeId,
  progress,
  onNavigate,
}: ReportReadingNavProps) {
  return (
    <nav aria-label='本页目录' className='hidden lg:block sticky top-20'>
      <div>
        <div className='bg-muted/20 h-px overflow-hidden rounded-full'>
          <div
            className='bg-primary/40 h-full transition-all duration-150'
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        <p className='text-muted-foreground mb-2 mt-3 text-xs font-medium'>本页目录</p>
        <ul className='space-y-1'>
          {sections.map((section) => (
            <li key={section.id}>
              <button
                type='button'
                onClick={() => onNavigate(section.id)}
                aria-current={activeId === section.id ? 'location' : undefined}
                className={cn(
                  'text-muted-foreground hover:text-foreground rounded-md px-2 py-1 text-xs transition-colors',
                  activeId === section.id && 'text-primary font-medium'
                )}
              >
                {section.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}
