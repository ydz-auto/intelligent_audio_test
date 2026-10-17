/**
 * 导入/导出用例弹窗（11_用例域.md §5.7.1-5.7.3，INT-381 补入）：
 * 导入（Dialog sm:max-w-2xl 三段式：选文件 Dropzone → 预览/校验 → 执行导入结果统计）；
 * 导出（Dialog sm:max-w-md：导出范围 RadioGroup + 格式 Select）。
 * 可视稿演示态：文件选择为占位区，预览表格展示 mock 待导入行；执行走 toast。
 */
import { FileUp, UploadCloud } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useEvaluationDimensions } from '@/application/evaluation/use-dimensions'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DimensionPicker } from '@/features/testcases/modals/round-config/dimension-picker'

const IMPORT_PREVIEW_ROWS = [
  { name: '智能音箱-播放音乐-中文-客厅', group: '智能音箱功能测试', algorithm: '通用识别引擎', rounds: '2 轮' },
  { name: '手机-语音助手-唤醒', group: '手机助手场景', algorithm: '流式识别引擎', rounds: '2 轮' },
  { name: '会议-英文转写-多人', group: '会议转写测试', algorithm: '多维评估集成', rounds: '1 轮' },
]

export function ImportExportDialog({
  open,
  onOpenChange,
  mode,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'import' | 'export'
}) {
  const [format, setFormat] = useState('json')
  /** 导入后评估维度选择（参考 V9.7.10 DimensionCloud 主/子层级；mock 演示） */
  const [importDimIds, setImportDimIds] = useState<number[]>([])
  const allDimsQuery = useEvaluationDimensions()
  const allDimensions = allDimsQuery.data ?? []

  const handleImportDimToggle = (ids: number[], checked: boolean) => {
    setImportDimIds((prev) =>
      checked
        ? [...new Set([...prev, ...ids])]
        : prev.filter((id) => !ids.includes(id))
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={mode === 'import' ? 'sm:max-w-2xl' : 'sm:max-w-md'}>
        <DialogHeader>
          <DialogTitle>{mode === 'import' ? '导入用例' : '导出用例'}</DialogTitle>
          <DialogDescription>
            {mode === 'import'
              ? '支持 JSON、Excel 文件，导入后自动更新同名用例'
              : '按当前筛选条件或已选用例导出，JSON / Excel 两种格式'}
          </DialogDescription>
        </DialogHeader>

        {mode === 'import' ? (
          <div className='space-y-4'>
            {/* ① 选文件 */}
            <div className='border-dashed flex cursor-pointer flex-col items-center gap-2 rounded-lg border p-6 text-center'>
              <UploadCloud aria-hidden='true' className='text-muted-foreground size-6' />
              <p className='text-sm font-medium'>点击选择或拖拽文件到此处</p>
              <p className='text-muted-foreground text-xs'>支持 JSON、Excel 文件</p>
              <Input type='file' accept='.json,.xlsx' className='hidden' aria-label='选择导入文件' />
            </div>
            <div className='flex items-center gap-2'>
              <span className='text-muted-foreground text-sm'>导入到分组</span>
              <Select defaultValue=''>
                <SelectTrigger size='sm' className='h-8 w-56'>
                  <SelectValue placeholder='不分组' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value=''>不分组</SelectItem>
                  <SelectItem value='g1'>智能音箱功能测试</SelectItem>
                  <SelectItem value='g2'>车载语音交互</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* ② 导入预览/校验 */}
            <div className='rounded-lg border'>
              <div className='bg-muted/40 border-b px-3 py-1.5 text-xs font-medium'>
                导入预览（校验通过 {IMPORT_PREVIEW_ROWS.length} 条）
              </div>
              <div className='overflow-x-auto'>
                <table className='w-full text-xs'>
                  <thead>
                    <tr className='bg-[var(--table-header)] text-start text-xs'>
                      <th className='px-3 py-1.5 text-left font-medium'>用例名称</th>
                      <th className='px-3 py-1.5 text-left font-medium'>分组</th>
                      <th className='px-3 py-1.5 text-left font-medium'>算法类型</th>
                      <th className='px-3 py-1.5 text-left font-medium'>轮次</th>
                    </tr>
                  </thead>
                  <tbody>
                    {IMPORT_PREVIEW_ROWS.map((row) => (
                      <tr key={row.name} className='border-border/60 border-b'>
                        <td className='px-3 py-1.5 font-medium'>{row.name}</td>
                        <td className='px-3 py-1.5'>{row.group}</td>
                        <td className='px-3 py-1.5'>{row.algorithm}</td>
                        <td className='px-3 py-1.5 tabular-nums'>{row.rounds}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ③ 导入后评估维度（参考 V9.7.10 DimensionCloud 主/子层级） */}
            <div className='space-y-2'>
              <span className='text-sm font-medium'>
                导入后评估维度（可选）
              </span>
              <div className='max-h-64 overflow-y-auto rounded-lg border p-2'>
                <DimensionPicker
                  dimensions={allDimensions}
                  selected={importDimIds}
                  onToggle={handleImportDimToggle}
                />
              </div>
              <p className='text-muted-foreground/70 text-xs'>
                不选表示导入用例沿用文件内评估维度配置
              </p>
            </div>
          </div>
        ) : (
          <div className='space-y-4'>
            <fieldset className='space-y-2'>
              <legend className='text-sm font-medium'>导出范围</legend>
              <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
                <input type='radio' name='export-range' defaultChecked />
                按当前筛选条件导出（导出全部筛选结果）
              </label>
              <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
                <input type='radio' name='export-range' />
                仅导出已选用例
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
        )}

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              toast.success(
                mode === 'import'
                  ? '导入完成：新增 3 条 · 更新 0 条'
                  : '已开始导出（演示：testcases_2026-10-16.json）'
              )
              onOpenChange(false)
            }}
          >
            {mode === 'import' ? (
              <>
                <FileUp aria-hidden='true' className='size-4' />
                开始导入
              </>
            ) : (
              '开始导出'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
