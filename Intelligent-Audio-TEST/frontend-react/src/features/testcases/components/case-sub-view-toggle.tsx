/**
 * 子视图切换控件（11_用例域.md §3.5/§3.6，Tabs 胶囊 size='sm' 复用基座 tabs.tsx）。
 * 分组卡内「平铺｜按标签」、标签卡内「平铺｜按用例分组」；默认态=平铺；
 * 切换状态 per-card 会话内存保留（useSessionMap），不进 URL（与展开态口径一致）。
 * 控件常显（不随展开态隐藏）；移动端（≤640px）由组头操作 DropdownMenu 收编「显示方式」。
 */
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export type SubViewValue = 'flat' | 'byTag' | 'byGroup'

export interface SubViewOption {
  key: SubViewValue
  label: string
}

/** 分组卡子视图选项（§3.5：平铺 / 按标签） */
export const GROUP_SUB_VIEW_OPTIONS: SubViewOption[] = [
  { key: 'flat', label: '平铺' },
  { key: 'byTag', label: '按标签' },
]

/** 标签卡子视图选项（§3.6：平铺 / 按用例分组） */
export const TAG_SUB_VIEW_OPTIONS: SubViewOption[] = [
  { key: 'flat', label: '平铺' },
  { key: 'byGroup', label: '按用例分组' },
]

export function CaseSubViewToggle({
  value,
  onValueChange,
  options,
}: {
  value: SubViewValue
  onValueChange: (value: SubViewValue) => void
  options: SubViewOption[]
}) {
  return (
    <Tabs
      value={value}
      onValueChange={(v) => onValueChange(v as SubViewValue)}
      aria-label='显示方式'
    >
      <TabsList className='h-7 gap-0.5 p-0.5'>
        {options.map((o) => (
          <TabsTrigger key={o.key} value={o.key} className='px-2 text-xs'>
            {o.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
