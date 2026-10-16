/**
 * 设备行操作菜单（16_设备域.md §3.4.1/§3.5/§3.6；DataTableRowActionMenu 对位）。
 * 按页签 + 状态 + 权限显隐：
 * - 测试设备：详情/编辑/健康检查/测试·停止测试（占用态显「停止测试」destructive + 离线禁用
 *   Tooltip「设备离线」）/连接/断开/重启/关机/安装·卸载应用（iOS 禁用 Tooltip「iOS 设备不支持该操作」）/删除
 * - 播放设备：详情/编辑/关联声压映射/播放测试/停止/重启播放设备/重置配置/静音·取消静音/
 *   播放测试结果分析/设备诊断·修复·优化/删除（离线行 DISABLED_ROW）
 * - 测试 API：详情/编辑/健康检查/停止测试/删除（离线端点行 DISABLED_ROW + 禁选）
 * 交互调用方：连接/断开/重启/关机/装/卸 → onControl(action)（mock 幂等 toast）。
 */
import { MoreHorizontal } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'

export interface DeviceRowActionsProps {
  kind: DevicesTabKey
  device: TestDevice | PlaybackDevice | ApiDevice
  canRead: boolean
  canUpdate: boolean
  canDelete: boolean
  canControl: boolean
  canPlaybackControl: boolean
  onDetail: () => void
  onEdit: () => void
  onHealth: () => void
  onTest: () => void
  onStopTest: () => void
  onControl: (action: string) => void
  onDelete: () => void
  onAssociateSpl: () => void
  onPlayTest: () => void
  onResultAnalysis: () => void
  onDiagnose: () => void
}

export function DeviceRowActions(props: DeviceRowActionsProps) {
  const { kind, device, canControl, canRead } = props
  const isTest = kind === 'test'
  const isPlayback = kind === 'playback'
  const isApi = kind === 'api'

  const status = device.status
  const isOffline = status === 'offline'
  const isConnecting = status === 'connecting'
  const isDisconnecting = status === 'disconnecting'
  const isIos = isTest && 'system' in device && device.system === 'iOS'

  /** 测试/停止测试：占用态显「停止测试」destructive；offline 态「测试」禁用 + Tooltip「设备离线」 */
  const testingOccupied = isTest && (device as TestDevice).occupied

  const controlItem = (
    action: string,
    label: string,
    opts?: { disabled?: boolean; title?: string; variant?: 'default' | 'destructive' }
  ) => (
    <DropdownMenuItem
      variant={opts?.variant}
      disabled={opts?.disabled}
      title={opts?.title}
      onClick={() => props.onControl(action)}
    >
      {label}
    </DropdownMenuItem>
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant='ghost' size='icon-sm' aria-label={`操作 ${device.name}`} />}
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        {canRead && (
          <DropdownMenuItem onClick={props.onDetail}>详情</DropdownMenuItem>
        )}
        {props.canUpdate && (
          <DropdownMenuItem onClick={props.onEdit}>编辑</DropdownMenuItem>
        )}

        {isTest && canControl && (
          <DropdownMenuItem
            disabled={isOffline}
            title={isOffline ? '设备离线，无法执行操作' : undefined}
            onClick={props.onHealth}
          >
            健康检查
          </DropdownMenuItem>
        )}

        {isTest && canControl && (
          <>
            {testingOccupied ? (
              <DropdownMenuItem variant='destructive' onClick={props.onStopTest}>
                停止测试
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
                disabled={isOffline}
                title={isOffline ? '设备离线，无法执行操作' : undefined}
                onClick={props.onTest}
              >
                测试
              </DropdownMenuItem>
            )}
          </>
        )}

        {isPlayback && props.canPlaybackControl && (
          <>
            <DropdownMenuItem onClick={props.onAssociateSpl}>关联声压映射</DropdownMenuItem>
            <DropdownMenuItem disabled={isOffline} onClick={props.onPlayTest}>
              播放测试
            </DropdownMenuItem>
            <DropdownMenuItem disabled={isOffline} onClick={props.onStopTest}>
              停止
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {controlItem('restart', '重启播放设备')}
            {controlItem('reset-config', '重置播放设备配置')}
            {controlItem('mute', '静音')}
            {controlItem('unmute', '取消静音')}
            <DropdownMenuSeparator />
          </>
        )}
        {isPlayback && canRead && (
          <DropdownMenuItem onClick={props.onResultAnalysis}>
            播放测试结果分析
          </DropdownMenuItem>
        )}
        {isPlayback && props.canPlaybackControl && (
          <DropdownMenuItem onClick={props.onDiagnose}>设备诊断·修复·优化</DropdownMenuItem>
        )}

        {isApi && canControl && (
          <DropdownMenuItem onClick={props.onHealth}>健康检查</DropdownMenuItem>
        )}
        {isApi && canControl && (
          <DropdownMenuItem disabled={isOffline} onClick={props.onStopTest}>
            停止测试
          </DropdownMenuItem>
        )}

        {isTest && canControl && (
          <>
            <DropdownMenuSeparator />
            {controlItem('connect', '连接', {
              disabled: isConnecting || isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('disconnect', '断开', {
              disabled: isDisconnecting || isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('reboot', '重启', {
              disabled: isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('shutdown', '关机', {
              disabled: isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('install-app', '安装应用', {
              disabled: isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('uninstall-app', '卸载应用', {
              disabled: isIos,
              title: isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            <DropdownMenuSeparator />
          </>
        )}

        {props.canDelete && (
          <DropdownMenuItem variant='destructive' onClick={props.onDelete}>
            删除
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
