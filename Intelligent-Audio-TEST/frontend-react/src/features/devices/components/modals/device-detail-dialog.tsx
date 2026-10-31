/**
 * 设备详情弹窗（16_设备域.md §6.2 只读抽屉；Dialog sm:max-w-3xl）。
 * 按页签展示设备字段分区：基本信息（名称/型号/序列号/系统/状态/所属实验室/最后在线）+ 连接信息
 * （连接方式/IP/端口）+ 应用与算法（应用名/版本/支持算法/驱动/是否需要提示词）+ 时间信息。
 * 「测试中」占用态叠加展示（INT-487）；所属实验室列 Badge/未绑定。
 */
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import type { DevicesTabKey } from '@/features/devices/constants'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { DeviceDetailState } from '@/features/devices/types'
import { DeviceStatusBadge } from '@/features/devices/components/device-status-badge'
import { connectionTypeLabel } from '@/features/devices/lib/connection-type'

export interface DeviceDetailDialogProps {
  state: DeviceDetailState
  onOpenChange: (open: boolean) => void
  onEdit: (kind: DevicesTabKey, device: TestDevice | PlaybackDevice | ApiDevice) => void
  /** P3-14 返修：详情内「编辑」按 canUpdate 权限门控（行菜单已按码显隐） */
  canUpdate: boolean
  /** 支持算法 value→中文名映射（GET /algorithm/options；缺省回退原始 value，INT-1215 无裸枚举） */
  algorithmNameMap?: Record<string, string>
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className='grid grid-cols-[96px_1fr] gap-2 text-sm'>
      <dt className='text-muted-foreground'>{label}</dt>
      <dd className='min-w-0 truncate'>{value ?? '—'}</dd>
    </div>
  )
}

export function DeviceDetailDialog(props: DeviceDetailDialogProps) {
  const { state } = props
  const device = state.device
  const kind = state.kind
  const testDevice = kind === 'test' ? (device as TestDevice | null) : null
  const playbackDevice = kind === 'playback' ? (device as PlaybackDevice | null) : null
  const apiDevice = kind === 'api' ? (device as ApiDevice | null) : null

  const title =
    kind === 'test' ? '测试设备详情' : kind === 'playback' ? '播放设备详情' : '测试 API 详情'

  return (
    <Dialog open={state.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {device?.name ?? ''} #{device?.id ?? ''}
          </DialogDescription>
        </DialogHeader>

        {device && (
          <div className='flex flex-col gap-4'>
            <div className='flex items-center gap-2'>
              <DeviceStatusBadge
                status={device.status as TestDevice['status']}
                occupied={'occupied' in device ? device.occupied : false}
              />
            </div>

            <section className='flex flex-col gap-1.5'>
              <h3 className='text-sm font-medium'>基本信息</h3>
              <Row label='名称' value={device.name} />
              <Row label='型号' value={testDevice?.model ?? playbackDevice?.model ?? apiDevice?.vendor} />
              {kind !== 'api' && (
                <Row label='序列号' value={testDevice?.serialNumber ?? playbackDevice?.deviceUniqueId} />
              )}
              {kind === 'test' && <Row label='系统' value={testDevice?.system ? `${testDevice.system} ${testDevice.systemVersion ?? ''}` : null} />}
              {kind === 'api' && <Row label='协议' value={apiDevice?.protocol} />}
              {kind === 'api' && <Row label='环境' value={apiDevice?.environment} />}
              <Row
                label='所属实验室'
                value={
                  testDevice?.labName || playbackDevice?.labName ? (
                    <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                      {testDevice?.labName ?? playbackDevice?.labName}
                    </Badge>
                  ) : (
                    <span className='text-muted-foreground'>未绑定</span>
                  )
                }
              />
              <Row label='描述' value={device.description} />
            </section>

            {kind === 'test' && testDevice && (
              <>
                <section className='flex flex-col gap-1.5'>
                  <h3 className='text-sm font-medium'>连接信息</h3>
                  <Row
                    label='连接方式'
                    value={
                      connectionTypeLabel(testDevice.connectionType) ? (
                        <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                          {connectionTypeLabel(testDevice.connectionType)}
                        </Badge>
                      ) : null
                    }
                  />
                  {testDevice.ip && <Row label='IP 地址' value={testDevice.ip} />}
                </section>
                <section className='flex flex-col gap-1.5'>
                  <h3 className='text-sm font-medium'>应用与算法</h3>
                  <Row label='应用' value={testDevice.appName ? `${testDevice.appName} · ${testDevice.appVersion ?? ''}` : null} />
                  <Row
                    label='支持算法'
                    value={
                      testDevice.supportedAlgorithms
                        ? testDevice.supportedAlgorithms
                            .map((a) => props.algorithmNameMap?.[a] ?? a)
                            .join('、')
                        : null
                    }
                  />
                  <Row label='驱动' value={testDevice.driverName} />
                  <Row label='提示词' value={testDevice.needsPromptAudio ? '需要' : '不需要'} />
                </section>
              </>
            )}

            {kind === 'playback' && playbackDevice && (
              <section className='flex flex-col gap-1.5'>
                <h3 className='text-sm font-medium'>播放参数</h3>
                <Row label='设备类型' value={playbackDevice.deviceType === 'dry' ? '干声设备' : '噪声设备'} />
                <Row label='采样率' value={playbackDevice.sampleRate ? `${playbackDevice.sampleRate} Hz` : null} />
                <Row label='通道索引' value={playbackDevice.channelIndex} />
                <Row label='支持的格式' value={playbackDevice.supportedFormats?.join('、')} />
                <Row label='声压映射' value={playbackDevice.currentSplMappingName ?? '未关联'} />
              </section>
            )}

            {kind === 'api' && apiDevice && (
              <section className='flex flex-col gap-1.5'>
                <h3 className='text-sm font-medium'>接口信息</h3>
                {/* INT-1223：Master URL 移除，端点只展示 api_endpoints（首个端点；多端点见列表/编辑抽屉） */}
                <Row label='端点' value={apiDevice.endpoints[0]?.endpoint} />
                <Row label='供应商' value={apiDevice.vendor} />
                <Row label='算法' value={apiDevice.algorithmType} />
                <Row label='总最大并发' value={apiDevice.defaultMaxProcess} />
                <Row label='健康分' value={apiDevice.healthScore} />
                <Row
                  label='RMS-SPL 映射'
                  value={
                    apiDevice.rmsSplMappingName ?? <span className='text-muted-foreground'>未关联</span>
                  }
                />
              </section>
            )}

            <section className='flex flex-col gap-1.5'>
              <h3 className='text-sm font-medium'>时间信息</h3>
              <Row
                label='最后在线'
                value={testDevice?.lastOnlineAt ? testDevice.lastOnlineAt.replace('T', ' ').slice(0, 16) : null}
              />
              <Row
                label='更新时间'
                value={device.updatedAt ? device.updatedAt.replace('T', ' ').slice(0, 16) : null}
              />
            </section>
          </div>
        )}

        <DialogFooter>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            关闭
          </Button>
          {device && props.canUpdate && (
            <Button
              onClick={() => {
                props.onOpenChange(false)
                props.onEdit(kind, device)
              }}
            >
              编辑
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
