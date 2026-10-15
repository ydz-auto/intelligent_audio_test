/**
 * 双页签（规范 §3.3：测试报告 type=task 固定 / 历史报告全类型；Tabs default 胶囊形态）。
 * 受控组件：value/onChange 由页面 URL tab 驱动（页签切换只切 URL，不回写筛选栏）。
 */
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface ReportTabsProps {
  value: 'test' | 'history'
  onChange: (value: 'test' | 'history') => void
}

export function ReportTabs({ value, onChange }: ReportTabsProps) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as 'test' | 'history')}>
      <TabsList className='w-full sm:w-auto'>
        <TabsTrigger value='test' className='flex-1 sm:flex-none sm:px-4'>
          测试报告
        </TabsTrigger>
        <TabsTrigger value='history' className='flex-1 sm:flex-none sm:px-4'>
          历史报告
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
