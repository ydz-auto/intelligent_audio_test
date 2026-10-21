/**
 * 设备卡（interfaces/features/test-execution/components；10_测试执行.md §3.6.1）。
 * 混跑口径：device_type 三值徽章（physical=Smartphone「真机」/http_api=Server「HTTP API」/
 * websocket_api=RadioTower「Realtime WS」）；离线禁选 + Tooltip；连接测试 ghost 钮
 * （device:control 显隐，tester 默认无）。
 * INT-1119（2026-10-21）：仅**被选中**卡显示「并行｜串行」逐卡模式 SegmentedControl
 * （默认并行，纯设备/混选均可用）；readOnly 观察态展示模式 Badge，无控件。
 */
import { RadioTower, Server, Smartphone, PlugZap } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  ExecutionModeBadge,
  ExecutionModeControl,
} from '@/features/test-execution/components/execution-mode-control'
import { cn } from '@/lib/utils'
import type { Device, DeviceType } from '@/domain/models/device'
import type { ExecutionMode } from '@/domain/models/testExecution'

const DEVICE_TYPE_ICON: Record<DeviceType, typeof Smartphone> = {
  physical: Smartphone,
  http_api: Server,
  websocket_api: RadioTower,
}

const DEVICE_TYPE_LABEL: Record<DeviceType, string> = {
  physical: '真机',
  http_api: 'HTTP API',
  websocket_api: 'Realtime WS',
}

interface DeviceCardProps {
  device: Device
  selected: boolean
  readOnly?: boolean
  canControl: boolean
  testing: boolean
  /** 当前执行模式（受控值经 useTargetModes；缺省并行） */
  mode?: ExecutionMode
  onModeChange?: (mode: ExecutionMode) => void
  onToggle: (id: number) => void
  onTestConnection: (id: number) => void
}

export function DeviceCard({
  device,
  selected,
  readOnly = false,
  canControl,
  testing,
  mode = 'parallel',
  onModeChange,
  onToggle,
  onTestConnection,
}: DeviceCardProps) {
  const online = device.status === 'online'
  const TypeIcon = device.type ? DEVICE_TYPE_ICON[device.type] : Smartphone
  const typeLabel = device.type ? DEVICE_TYPE_LABEL[device.type] : '未知'

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
        <span className='min-w-0 flex-1 truncate text-sm font-medium'>{device.name}</span>
        <Badge variant='outline' className='shrink-0 text-[11px]'>
          {online ? '在线' : '离线'}
        </Badge>
      </div>

      {/* 规格行 */}
      <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs'>
        <dt className='text-muted-foreground'>型号</dt>
        <dd className='truncate'>{device.model ?? '—'}</dd>
        <dt className='text-muted-foreground'>序列号</dt>
        <dd className='truncate font-mono'>{device.serialNumber ?? '—'}</dd>
        <dt className='text-muted-foreground'>系统</dt>
        <dd>
          {device.system ? (
            <Badge variant='outline' className='text-[11px]'>
              {device.system}
            </Badge>
          ) : (
            '—'
          )}
        </dd>
      </dl>

      {/* 设备类型徽章（混跑标识） */}
      <div className='flex items-center gap-1.5'>
        <TypeIcon aria-hidden='true' className='text-muted-foreground size-3.5' />
        <Badge variant='secondary' className='text-[11px]'>
          {typeLabel}
        </Badge>
      </div>

      {/* 操作行 */}
      <div className='mt-auto flex flex-wrap items-center gap-2'>
        {!readOnly && (
          <>
            <Tooltip>
              <TooltipTrigger
                render={
                  <span className='flex items-center gap-1.5 text-sm'>
                    <Checkbox
                      checked={selected}
                      disabled={!online}
                      aria-label={`选择设备 ${device.name}`}
                      className='size-4'
                      onCheckedChange={() => onToggle(device.id)}
                    />
                    <span className={cn('text-xs', !online && 'text-muted-foreground')}>选择</span>
                  </span>
                }
              />
              <TooltipContent side='bottom'>
                {online ? '选择该设备执行测试' : '离线不可选'}
              </TooltipContent>
            </Tooltip>
            {/* 逐卡执行模式（INT-1119：仅被选中卡显示；默认并行） */}
            {selected && onModeChange && (
              <ExecutionModeControl
                value={mode}
                onChange={onModeChange}
                ariaLabel={`${device.name} 执行模式`}
              />
            )}
          </>
        )}
        {!readOnly && canControl && (
          <Button
            variant='ghost'
            size='sm'
            className='ml-auto h-7 gap-1 text-xs'
            disabled={testing}
            onClick={() => onTestConnection(device.id)}
          >
            <PlugZap aria-hidden='true' className={cn('size-3.5', testing && 'animate-pulse')} />
            {testing ? '测试中…' : '连接测试'}
          </Button>
        )}
        {readOnly && (
          <span className='text-muted-foreground flex items-center gap-2 text-xs'>
            {selected ? (
              <ExecutionModeBadge mode={mode} />
            ) : (
              '未选择'
            )}
          </span>
        )}
      </div>
    </div>
  )
}
