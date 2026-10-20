/**
 * API 卡（interfaces/features/test-execution/components；10_测试执行.md §3.6.1 混跑口径）。
 * INT-1061 裁定（负责人 2026-10-20 反馈「设备和 API 的卡片应该长得差不多」）：开始测试
 * 同屏混选场景下 API 目标与设备卡同一套卡片形态——头行状态点+名称+状态 Badge、规格行
 * （端点/算法/最大并发）、API 类型徽章（device_type：http_api=Server「HTTP API」/
 * websocket_api=RadioTower「Realtime WS」）、整卡选中态 ring-2；离线禁选 + Tooltip；
 * 连接测试 ghost 钮（api_config:test 显隐）+ 编辑/删除行菜单（api_config:update/delete）。
 * 纯 API 流程表格（§3.6.2）保留于 api-table.tsx，本件仅服务同屏混选。
 */
import { MoreHorizontal, PlugZap, RadioTower, Server } from 'lucide-react'

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
import { cn } from '@/lib/utils'
import type { ApiConfig } from '@/domain/models/apiConfig'

const API_TYPE_ICON = {
  http_api: Server,
  websocket_api: RadioTower,
} as const

const API_TYPE_LABEL = {
  http_api: 'HTTP API',
  websocket_api: 'Realtime WS',
} as const

interface ApiCardProps {
  api: ApiConfig
  selected: boolean
  readOnly?: boolean
  canTest: boolean
  canEdit: boolean
  canDelete: boolean
  testing: boolean
  onToggle: (id: number) => void
  onTestConnection: (api: ApiConfig) => void
  onEdit: (api: ApiConfig) => void
  onDelete: (api: ApiConfig) => void
}

export function ApiCard({
  api,
  selected,
  readOnly = false,
  canTest,
  canEdit,
  canDelete,
  testing,
  onToggle,
  onTestConnection,
  onEdit,
  onDelete,
}: ApiCardProps) {
  const online = api.status === 'online'
  // device_type 两值徽章（协议筛选同口径：websocket_api=WS，其余 HTTP）
  const isWs = api.deviceType === 'websocket_api'
  const TypeIcon = isWs ? API_TYPE_ICON.websocket_api : API_TYPE_ICON.http_api
  const typeLabel = isWs ? API_TYPE_LABEL.websocket_api : API_TYPE_LABEL.http_api
  const endpoint = api.apiUrl ?? api.endpoints[0]?.endpoint ?? null

  return (
    <div
      className={cn(
        'flex flex-col gap-2 rounded-xl border p-4 transition-colors',
        selected && 'border-primary ring-primary/20 ring-2',
        !selected && 'border-border hover:bg-muted/30',
        !online && 'opacity-70'
      )}
    >
      {/* 头行 */}
      <div className='flex items-center gap-2'>
        <span
          aria-hidden='true'
          className={cn(
            'size-2 shrink-0 rounded-full',
            online ? 'bg-success' : 'bg-muted'
          )}
        />
        <span className='min-w-0 flex-1 truncate text-sm font-medium'>{api.name}</span>
        <Badge variant='outline' className='shrink-0 text-[11px]'>
          {online ? '在线' : '离线'}
        </Badge>
      </div>

      {/* 规格行（API 维度：端点/算法/最大并发） */}
      <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs'>
        <dt className='text-muted-foreground'>端点</dt>
        <dd className='truncate font-mono' title={endpoint ?? ''}>
          {endpoint ?? '—'}
        </dd>
        <dt className='text-muted-foreground'>算法</dt>
        <dd>
          {api.algorithmType ? (
            <Badge variant='secondary' className='text-[11px]'>
              {api.algorithmType}
            </Badge>
          ) : (
            '—'
          )}
        </dd>
        <dt className='text-muted-foreground'>最大并发</dt>
        <dd className='tabular-nums'>{api.maxConcurrent}</dd>
      </dl>

      {/* API 类型徽章（混跑标识） */}
      <div className='flex items-center gap-1.5'>
        <TypeIcon aria-hidden='true' className='text-muted-foreground size-3.5' />
        <Badge variant='secondary' className='text-[11px]'>
          {typeLabel}
        </Badge>
      </div>

      {/* 操作行 */}
      <div className='mt-auto flex items-center gap-2'>
        {!readOnly && (
          <Tooltip>
            <TooltipTrigger
              render={
                <span className='flex items-center gap-1.5 text-sm'>
                  <Checkbox
                    checked={selected}
                    disabled={!online}
                    aria-label={`选择 API ${api.name}`}
                    className='size-4'
                    onCheckedChange={() => onToggle(api.id)}
                  />
                  <span className={cn('text-xs', !online && 'text-muted-foreground')}>选择</span>
                </span>
              }
            />
            <TooltipContent side='bottom'>
              {online ? '选择该 API 执行测试' : '离线不可选'}
            </TooltipContent>
          </Tooltip>
        )}
        {!readOnly && (
          <div className='ml-auto flex items-center gap-0.5'>
            {canTest && (
              <Button
                variant='ghost'
                size='icon-sm'
                aria-label={`连接测试 ${api.name}`}
                disabled={testing}
                onClick={() => onTestConnection(api)}
              >
                <PlugZap
                  aria-hidden='true'
                  className={cn('size-3.5', testing && 'animate-pulse')}
                />
              </Button>
            )}
            {(canEdit || canDelete) && (
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
        )}
        {readOnly && (
          <span className='text-muted-foreground text-xs'>
            {selected ? '已选择' : '未选择'}
          </span>
        )}
      </div>
    </div>
  )
}
