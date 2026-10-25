/**
 * 设备行操作菜单（16_设备域.md §3.4.1/§3.5/§3.6；DataTableRowActionMenu 对位）。
 * 按页签 + 状态 + 权限显隐：
 * - 测试设备：详情/编辑/健康检查/测试·停止测试（占用态显「停止测试」destructive + 离线禁用
 *   Tooltip「设备离线」）/连接/断开/重启/关机/安装·卸载应用（iOS 禁用 Tooltip「iOS 设备不支持该操作」；
 *   编辑仅受 device:update 权限控制、不受离线禁用——编辑元数据不依赖设备在线，INT-1217 P1）
 *   安装/卸载走参数小弹窗 P3-31）/删除
 * - 播放设备：详情/编辑/关联声压映射/播放测试/停止/重启播放设备/重置配置/静音·取消静音/
 *   播放测试结果分析/设备诊断·修复·优化/删除
 * - 测试 API：详情/编辑/健康检查（api_config:read，P2-7）/停止测试/删除（离线端点行禁选）
 * 交互调用方：连接/断开/重启/关机 → onControl(action)（真实端点 /test-devices/{id}/{action}）；
 * 装/卸 → 参数弹窗。
 * P2-4：后端无端点的动作（播放设备重启/重置配置/静音/取消静音、播放测试结果分析、设备诊断）
 * 一律禁用 + Tooltip「后端未提供该操作」，不伪造成功（真实端点见 INT-1573）。
 * P3-24 返修：iOS 判定走 normalizeDeviceSystem 归一（小写 harmony/android 不再恒不命中）。
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
import { isIosSystem } from '@/features/devices/lib/device-system'
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
  /** 健康检查权限（P2-7 返修：API 页签=api_config:read，测试页签=device:control） */
  canHealth: boolean
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
  onStop: () => void
  /** 安装/卸载参数小弹窗（§3.4.1：file_path/package_name 输入，P3-31 补口） */
  onInstallApp: () => void
  onUninstallApp: () => void
}

export function DeviceRowActions(props: DeviceRowActionsProps) {
  const { kind, device, canControl, canRead, canHealth } = props
  const isTest = kind === 'test'
  const isPlayback = kind === 'playback'
  const isApi = kind === 'api'

  const status = device.status
  const isOffline = status === 'offline'
  const isConnecting = status === 'connecting'
  const isDisconnecting = status === 'disconnecting'
  // P3-24：iOS 判定归一（'iOS'/'ios' 均命中）
  const isIos = isTest && 'system' in device && isIosSystem(device.system)

  /** 测试/停止测试：占用态显「停止测试」destructive；offline 态「测试」禁用 + Tooltip「设备离线」 */
  const testingOccupied = isTest && (device as TestDevice).occupied

  const offlineTooltip = '设备离线，无法执行操作'
  /** P2-4：后端未提供端点的动作说明（禁用态 Tooltip） */
  const unsupportedTooltip = '后端未提供该操作（待 INT-1573）'

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
          // INT-1217：编辑设备元数据不依赖设备在线（V9.7.10 基线 editDevice 无状态限制），离线不禁用；
          // 仅「测试/连接/健康检查/重启」等实时操作按离线态禁用。
          <DropdownMenuItem onClick={props.onEdit}>
            编辑
          </DropdownMenuItem>
        )}

        {isTest && canHealth && (
          <DropdownMenuItem
            disabled={isOffline}
            title={isOffline ? offlineTooltip : undefined}
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
            <DropdownMenuItem disabled={isOffline} title={isOffline ? offlineTooltip : undefined} onClick={props.onPlayTest}>
              播放测试
            </DropdownMenuItem>
            <DropdownMenuItem disabled={isOffline} title={isOffline ? offlineTooltip : undefined} onClick={props.onStop}>
              停止
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {/* P2-4：后端无 restart/reset-config/mute/unmute 端点（INT-1573）→ 禁用 + 说明，不假成功 */}
            {controlItem('restart', '重启播放设备', {
              disabled: true,
              title: unsupportedTooltip,
            })}
            {controlItem('reset-config', '重置播放设备配置', {
              disabled: true,
              title: unsupportedTooltip,
            })}
            {controlItem('mute', '静音', {
              disabled: true,
              title: unsupportedTooltip,
            })}
            {controlItem('unmute', '取消静音', {
              disabled: true,
              title: unsupportedTooltip,
            })}
            <DropdownMenuSeparator />
          </>
        )}
        {isPlayback && canRead && (
          <DropdownMenuItem disabled title={unsupportedTooltip}>
            播放测试结果分析
          </DropdownMenuItem>
        )}
        {isPlayback && props.canPlaybackControl && (
          <DropdownMenuItem disabled title={unsupportedTooltip}>
            设备诊断·修复·优化
          </DropdownMenuItem>
        )}

        {isApi && canHealth && (
          <DropdownMenuItem
            disabled={isOffline}
            title={isOffline ? offlineTooltip : undefined}
            onClick={props.onHealth}
          >
            健康检查
          </DropdownMenuItem>
        )}
        {isApi && canControl && (
          <DropdownMenuItem disabled={isOffline} title={isOffline ? offlineTooltip : undefined} onClick={props.onStopTest}>
            停止测试
          </DropdownMenuItem>
        )}

        {isTest && canControl && (
          <>
            <DropdownMenuSeparator />
            {controlItem('connect', '连接', {
              disabled: isConnecting || isIos || isOffline,
              title: isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('disconnect', '断开', {
              disabled: isDisconnecting || isIos || isOffline,
              title: isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('reboot', '重启', {
              disabled: isIos || isOffline,
              title: isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            {controlItem('shutdown', '关机', {
              disabled: isIos || isOffline,
              title: isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined,
            })}
            <DropdownMenuItem
              disabled={isIos || isOffline}
              title={isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined}
              onClick={props.onInstallApp}
            >
              安装应用
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={isIos || isOffline}
              title={isOffline ? offlineTooltip : isIos ? 'iOS 设备不支持该操作' : undefined}
              onClick={props.onUninstallApp}
            >
              卸载应用
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}

        {props.canDelete && (
          /* P2-3：删除属元数据操作，不受离线状态限制（V9.7.10 无在线前置，INT-1217 编辑同口径） */
          <DropdownMenuItem
            variant='destructive'
            onClick={props.onDelete}
          >
            删除
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
