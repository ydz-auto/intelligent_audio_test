/**
 * 被测 API 表格（interfaces/features/test-execution/components；10_测试执行.md §3.6.2）。
 * 列=☑选择（表头全选，离线行禁用）/执行模式/名称/端点/算法/状态/最大并发/操作
 * （连接测试+编辑/删除行菜单，api_config:test/update/delete 权限显隐）；离线行视觉禁用 + Tooltip。
 * INT-1061 裁定（2026-10-20）：开始测试同屏混选改走 api-card.tsx（与设备卡同形态）；
 * 本件保留服务 §3.6.2 纯 API 流程备用（React 侧现无独立纯 API 流程，INT-486 合并口径）。
 * INT-1060 返工 / INT-1119（2026-10-21）：执行模式列——仅**选中**行显示「并行｜串行」
 * 紧凑 SegmentedControl（默认并行）；未选行显示「—」；readOnly 观察态展示模式 Badge，无控件。
 */
import { MoreHorizontal, PlugZap } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  ExecutionModeBadge,
  ExecutionModeControl,
} from '@/features/test-execution/components/execution-mode-control'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { ExecutionMode } from '@/domain/models/testExecution'

interface ApiTableProps {
  apis: ApiConfig[]
  selectedIds: number[]
  readOnly?: boolean
  canTest: boolean
  canEdit: boolean
  canDelete: boolean
  testingIds: Set<number>
  /** 每 API 当前执行模式（受控值经 useTargetModes；缺省并行） */
  modes?: Record<number, ExecutionMode>
  onModeChange?: (apiId: number, mode: ExecutionMode) => void
  onToggle: (id: number) => void
  onToggleAll: () => void
  onTestConnection: (api: ApiConfig) => void
  onEdit: (api: ApiConfig) => void
  onDelete: (api: ApiConfig) => void
}

export function ApiTable({
  apis,
  selectedIds,
  readOnly = false,
  canTest,
  canEdit,
  canDelete,
  testingIds,
  modes,
  onModeChange,
  onToggle,
  onToggleAll,
  onTestConnection,
  onEdit,
  onDelete,
}: ApiTableProps) {
  const onlineRows = apis.filter((a) => a.status === 'online')
  const allVisibleSelected = onlineRows.length > 0 && onlineRows.every((a) => selectedIds.includes(a.id))

  return (
    <div className='overflow-hidden rounded-lg border'>
      <table className='w-full text-left text-sm'>
        <thead className='bg-muted/50 border-b'>
          <tr className='text-muted-foreground text-xs'>
            <th className='w-10 px-4 py-2.5'>
              {!readOnly && (
                <Checkbox
                  checked={allVisibleSelected}
                  aria-label='全选在线 API'
                  className='size-4'
                  onCheckedChange={onToggleAll}
                />
              )}
            </th>
            <th className='w-28 px-2 py-2.5 font-medium'>执行模式</th>
            <th className='px-2 py-2.5 font-medium'>API 名称</th>
            <th className='px-2 py-2.5 font-medium'>端点</th>
            <th className='px-2 py-2.5 font-medium'>算法</th>
            <th className='px-2 py-2.5 font-medium'>状态</th>
            <th className='px-2 py-2.5 font-medium'>最大并发</th>
            <th className='px-4 py-2.5 text-end font-medium'>操作</th>
          </tr>
        </thead>
        <tbody>
          {apis.map((api) => {
            const online = api.status === 'online'
            const selected = selectedIds.includes(api.id)
            const mode = modes?.[api.id] ?? 'parallel'
            return (
              <tr
                key={api.id}
                className={cn(
                  'border-b last:border-0 hover:bg-muted/30',
                  !online && 'opacity-60',
                  selected && 'bg-primary/5'
                )}
              >
                <td className='px-4 py-2.5'>
                  {!readOnly ? (
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <Checkbox
                            checked={selected}
                            disabled={!online}
                            aria-label={`选择 ${api.name}`}
                            className='size-4'
                            onCheckedChange={() => onToggle(api.id)}
                          />
                        }
                      />
                      <TooltipContent side='bottom'>
                        {online ? '选择该 API 执行测试' : 'API 离线，无法执行测试'}
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <span className='text-primary flex justify-center text-xs'>✓</span>
                  )}
                </td>
                <td className='px-2 py-2.5'>
                  {selected ? (
                    readOnly ? (
                      <ExecutionModeBadge mode={mode} />
                    ) : (
                      onModeChange && (
                        <ExecutionModeControl
                          compact
                          value={mode}
                          onChange={(next) => onModeChange(api.id, next)}
                          ariaLabel={`${api.name} 执行模式`}
                        />
                      )
                    )
                  ) : (
                    <span className='text-muted-foreground text-xs'>—</span>
                  )}
                </td>
                <td className='px-2 py-2.5'>
                  <span className='block font-medium'>{api.name}</span>
                  {api.description && (
                    <span className='text-muted-foreground block max-w-56 truncate text-xs'>
                      {api.description}
                    </span>
                  )}
                </td>
                <td className='px-2 py-2.5'>
                  <span className='text-muted-foreground block max-w-52 truncate font-mono text-xs' title={api.apiUrl ?? ''}>
                    {api.apiUrl ?? api.endpoints[0]?.endpoint ?? '—'}
                  </span>
                </td>
                <td className='px-2 py-2.5'>
                  <Badge variant='secondary' className='text-[11px]'>
                    {api.algorithmType ?? '—'}
                  </Badge>
                </td>
                <td className='px-2 py-2.5'>
                  <StatusBadge
                    label={online ? '在线' : '离线'}
                    variant={online ? 'success' : 'neutral'}
                  />
                </td>
                <td className='px-2 py-2.5 text-xs tabular-nums'>{api.maxConcurrent}</td>
                <td className='px-4 py-2.5'>
                  <div className='flex items-center justify-end gap-0.5'>
                    {canTest && (
                      <Button
                        variant='ghost'
                        size='icon-sm'
                        aria-label={`连接测试 ${api.name}`}
                        disabled={testingIds.has(api.id)}
                        onClick={() => onTestConnection(api)}
                      >
                        <PlugZap
                          aria-hidden='true'
                          className={cn('size-3.5', testingIds.has(api.id) && 'animate-pulse')}
                        />
                      </Button>
                    )}
                    {(canEdit || canDelete) && !readOnly && (
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={<Button variant='ghost' size='icon-sm' aria-label='更多操作' />}
                        >
                          <MoreHorizontal aria-hidden='true' className='size-3.5' />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align='end'>
                          {canEdit && (
                            <DropdownMenuItem onClick={() => onEdit(api)}>编辑</DropdownMenuItem>
                          )}
                          {canDelete && (
                            <DropdownMenuItem
                              className='text-destructive focus:text-destructive'
                              onClick={() => onDelete(api)}
                            >
                              删除
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
