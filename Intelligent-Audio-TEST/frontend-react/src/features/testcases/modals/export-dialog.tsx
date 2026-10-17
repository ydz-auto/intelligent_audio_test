/**
 * 导出用例弹窗（11_用例域.md §5.7.2，Dialog sm:max-w-md）。
 * 导出范围 RadioGroup「按当前筛选条件导出（导出全部筛选结果）/仅导出已选 {n} 个用例」
 * + 格式 Select（JSON / Excel）+ 主钮「开始导出」（演示态走 toast）。
 * 注：页头「导入用例」按负责人 2026-10-17 口径收敛为**单入口——只走音频导入页生成**
 * （照 V9.7.10 TestCaseManager「导入用例」按钮跳 /AudioImport 语义），原「导入用例文件」
 * 文件导入弹窗（§5.7.1）不再从用例管理页暴露；本弹窗仅保留导出。
 */
import { FileSpreadsheet } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export function ExportDialog({
  open,
  onOpenChange,
  selectedCount,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedCount?: number
}) {
  const [format, setFormat] = useState('json')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>导出用例</DialogTitle>
          <DialogDescription>
            按当前筛选条件或已选用例导出，JSON / Excel 两种格式
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <fieldset className='space-y-2'>
            <legend className='text-sm font-medium'>导出范围</legend>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
              <input type='radio' name='export-range' defaultChecked />
              按当前筛选条件导出（导出全部筛选结果）
            </label>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
              <input type='radio' name='export-range' />
              仅导出已选 {selectedCount ?? 0} 个用例
            </label>
          </fieldset>
          <div className='flex items-center gap-2'>
            <span className='text-muted-foreground text-sm'>格式</span>
            <Select value={format} onValueChange={(v) => setFormat(v ?? 'json')}>
              <SelectTrigger size='sm' className='h-8 w-40'>
                <SelectValue>{format === 'json' ? 'JSON' : 'Excel'}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='json'>JSON</SelectItem>
                <SelectItem value='xlsx'>Excel</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              toast.success(
                `已开始导出（演示：testcases_2026-10-16.${format === 'json' ? 'json' : 'xlsx'}）`
              )
              onOpenChange(false)
            }}
          >
            <FileSpreadsheet aria-hidden='true' className='size-4' />
            开始导出
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
