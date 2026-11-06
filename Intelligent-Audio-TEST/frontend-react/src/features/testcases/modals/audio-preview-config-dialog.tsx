/**
 * 音频试听配置弹窗（11_用例域.md §5.2，Dialog sm:max-w-md）。
 * 播放模式 RadioGroup「浏览器播放/实验室播放」+ 偏移量 Input（number 秒，默认 0）+ 主钮「开始试听」。
 * 试听对象二选一（INT-1534 返工并线）：
 * 1) 用例行「预览音频」：未带 audioItem 时按用例试听——「开始试听」发真实
 *    POST /testcases/{id}/preview（offset + preview_type + playback_mode），成功后带响应进播放器；
 *    失败 toast「音频试听失败: {err}」+ 弹窗内错误条，留在配置态可重试。
 * 2) 音频列表卡「试听」/全局噪声「试听」（INT-1424）：带 audioItem 时进播放器，
 *    由播放器自己取 GET /audios/{id}/stream（浏览器）或 POST /audios/{id}/preview（实验室）。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { TriangleAlert, X } from 'lucide-react'
import { toast } from 'sonner'

import { Alert } from '@/components/ui/alert'
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
import { useLaboratories, usePlaybackSpeakerGroups } from '@/application/devices/use-devices'
import {
  AudioPlayerPanel,
  type AudioPlayerPanelProps,
} from '@/features/testcases/modals/audio-player-dialog'
import type {
  PreviewPlaybackMode,
  TestCaseListItem,
  TestCasePreview,
} from '@/domain/models/testCase'
import { ApiError } from '@/infrastructure/api/api-error'
import { previewTestCase } from '@/infrastructure/api/testcases-api'

/** 试听对象（音频列表卡/全局噪声传入） */
export interface PreviewAudioItem {
  id: number | string
  name?: string | null
  spl?: number | null
  /** 音频时长（秒；音频库 AudioAsset.duration，实验室播放无浏览器流时作总时长兜底） */
  duration?: number | null
  /** 播放设备展示标签（实验室播放=用例配置的逻辑音箱） */
  deviceLabels?: string[]
  /** 逻辑音箱组 id（用例只关联逻辑音箱；实验室播放时按所选实验室解析成实体设备） */
  speakerGroupIds?: string[]
  /** 播放设备记录 id（历史兼容：上传/导入试听仍可直接指定实体设备） */
  deviceIds?: string[]
}

export function AudioPreviewConfigDialog({
  open,
  onOpenChange,
  caseItem,
  audioItem,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem: TestCaseListItem | null
  /** 试听对象（可选；有值时走音频库/全局噪声试听源，忽略用例预览） */
  audioItem?: PreviewAudioItem | null
}) {
  const [mode, setMode] = useState<PreviewPlaybackMode>('frontend')
  const [offset, setOffset] = useState('0')
  /** 试听编排阶段：config=播放模式/偏移量配置；playing=音频播放器（§5.2） */
  const [stage, setStage] = useState<'config' | 'playing'>('config')
  const [preview, setPreview] = useState<TestCasePreview | null>(null)
  const [startOffset, setStartOffset] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 请求代次：关闭/重置后丢弃在途响应，避免把 stage 又推回播放器（INT-1534 P3-1） */
  const requestTokenRef = useRef(0)
  /** 实验室试听必须先选实验室：逻辑音箱按「实验室」解析成该实验室的实体音箱 */
  const [labId, setLabId] = useState('')
  const [resolvedDeviceIds, setResolvedDeviceIds] = useState<string[]>([])
  const labsQuery = useLaboratories()
  const speakerGroupsQuery = usePlaybackSpeakerGroups()
  const labs = useMemo(() => labsQuery.data ?? [], [labsQuery.data])
  const speakerGroups = useMemo(
    () => speakerGroupsQuery.data ?? [],
    [speakerGroupsQuery.data]
  )
  const labItems = useMemo(
    () => labs.map((lab) => ({ value: String(lab.id), label: lab.name })),
    [labs]
  )

  const isCasePreview = audioItem == null

  const reset = () => {
    requestTokenRef.current += 1
    setStage('config')
    setPreview(null)
    setStartOffset(0)
    setPending(false)
    setError(null)
    setOffset('0')
    setMode('frontend')
    setLabId('')
    setResolvedDeviceIds([])
  }

  // 外部关闭（父组件把 open 置 false / 换用例）时同样复位：在途请求的响应必须丢弃，
  // 否则下次打开会停在上一个用例的播放器（INT-1534 P3-1）
  useEffect(() => {
    if (!open) reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  /** 关闭弹窗统一入口（取消钮也走这里，保证在途请求被作废） */
  const close = () => {
    reset()
    onOpenChange(false)
  }

  /** 逻辑音箱 → 所选实验室的实体播放设备 id；解析失败返回中文原因 */
  const resolveSpeakerDevices = (groupIds: string[], lab: number): string[] | string => {
    const deviceIds: string[] = []
    for (const raw of groupIds) {
      const group = speakerGroups.find((item) => String(item.id) === raw)
      if (!group) return `未找到逻辑音箱 ${raw}`
      const item = group.items.find((it) => it.labId === lab)
      if (!item) return `逻辑音箱「${group.name}」未配置该实验室的播放设备`
      deviceIds.push(String(item.playbackDeviceId))
    }
    return deviceIds
  }

  /** 开始试听：用例源发真实 preview 请求；音频库源直接进播放器（播放器自行取流/放音）。
   *  实验室播放必须先选实验室：逻辑音箱按实验室解析成实体音箱后再发给后端
   *  （两个源都必须先把偏移量落到 startOffset，INT-1534 P2 回归修复）。 */
  const handleStart = async () => {
    const seconds = Number(offset === '' ? 0 : offset)
    if (!Number.isFinite(seconds) || seconds < 0) {
      setError('偏移量需为不小于 0 的秒数')
      return
    }
    const lab = Number(labId)
    if (mode === 'backend' && (!labId || !Number.isFinite(lab))) {
      setError('实验室播放请先选择实验室')
      return
    }
    setError(null)
    if (audioItem) {
      let deviceIds = audioItem.deviceIds ?? []
      if (mode === 'backend' && (audioItem.speakerGroupIds?.length ?? 0) > 0) {
        const resolved = resolveSpeakerDevices(audioItem.speakerGroupIds ?? [], lab)
        if (typeof resolved === 'string') {
          setError(resolved)
          return
        }
        deviceIds = resolved
      }
      setResolvedDeviceIds(deviceIds)
      setStartOffset(seconds)
      setStage('playing')
      return
    }
    if (!caseItem || pending) return
    const token = requestTokenRef.current + 1
    requestTokenRef.current = token
    setPending(true)
    setError(null)
    try {
      const result = await previewTestCase(caseItem.id, {
        offset: seconds,
        previewType: mode,
        playbackMode: mode,
        labId: mode === 'backend' ? lab : null,
      })
      if (token !== requestTokenRef.current) return
      setPreview(result)
      setStartOffset(seconds)
      setStage('playing')
    } catch (err) {
      if (token !== requestTokenRef.current) return
      const message =
        err instanceof ApiError ? err.userMessage : '音频试听失败，请重试'
      setError(message)
      toast.error(`音频试听失败: ${message}`)
    } finally {
      if (token === requestTokenRef.current) setPending(false)
    }
  }

  const playerProps: AudioPlayerPanelProps | null = audioItem
    ? {
        mode,
        audioId: audioItem.id,
        audioName: audioItem.name ?? null,
        deviceLabels: audioItem.deviceLabels ?? [],
        deviceIds: resolvedDeviceIds,
        spl: audioItem.spl ?? 65,
        offset: startOffset,
        durationHint: audioItem.duration ?? null,
        onBack: () => setStage('config'),
      }
    : preview && caseItem
      ? {
          mode,
          preview,
          caseItem,
          startOffset,
          onBack: () => setStage('config'),
        }
      : null

  const titleTarget = audioItem?.name ?? caseItem?.name ?? '音频'

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent className={stage === 'playing' ? 'sm:max-w-lg' : 'sm:max-w-md'}>
        <DialogHeader>
          <DialogTitle>
            {stage === 'playing'
              ? `测试用例预览｜${titleTarget} 音频`
              : '音频试听配置'}
          </DialogTitle>
          <DialogDescription>
            {stage === 'playing'
              ? isCasePreview
                ? mode === 'backend'
                  ? '实验室扬声器试听中'
                  : '浏览器播放试听中'
                : '浏览器播放或实验室扬声器试听中'
              : audioItem?.name
                ? `音频「${audioItem.name}」`
                : caseItem
                  ? `用例「${caseItem.name}」`
                  : '预览所选用例的音频'}
          </DialogDescription>
        </DialogHeader>

        {stage === 'playing' && playerProps ? (
          <AudioPlayerPanel {...playerProps} />
        ) : (
          <div className='space-y-4'>
            {error && (
              <Alert variant='destructive'>
                <TriangleAlert aria-hidden='true' className='size-4 shrink-0' />
                <span className='min-w-0 flex-1'>{error}</span>
                <button
                  type='button'
                  aria-label='关闭错误提示'
                  className='text-current'
                  onClick={() => setError(null)}
                >
                  <X aria-hidden='true' className='size-4' />
                </button>
              </Alert>
            )}
            <div className='space-y-1.5'>
              <span className='text-sm font-medium'>播放模式</span>
              <div className='flex flex-col gap-1.5'>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'frontend'}
                    onChange={() => setMode('frontend')}
                  />
                  <span>
                    浏览器播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过浏览器前端直接播放
                    </span>
                  </span>
                </label>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'backend'}
                    onChange={() => setMode('backend')}
                  />
                  <span>
                    实验室播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过所选实验室的实体音箱播放（逻辑音箱按实验室解析）
                    </span>
                  </span>
                </label>
              </div>
            </div>
            {mode === 'backend' && (
              <div className='space-y-1.5'>
                <span className='text-sm font-medium'>实验室 *</span>
                <Select
                  value={labId}
                  onValueChange={(value) => setLabId(value ?? '')}
                  items={labItems}
                >
                  <SelectTrigger size='sm' className='h-8 w-full'>
                    <SelectValue placeholder='请选择实验室' />
                  </SelectTrigger>
                  <SelectContent>
                    {labItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className='flex items-center gap-2'>
              <span className='text-sm font-medium'>偏移量（秒）</span>
              <Input
                type='number'
                min={0}
                value={offset}
                onChange={(e) => setOffset(e.target.value)}
                className='h-8 w-32'
                aria-label='偏移量秒数'
              />
            </div>
          </div>
        )}

        {stage !== 'playing' && (
          <DialogFooter>
            <Button variant='outline' onClick={close}>
              取消
            </Button>
            <Button
              onClick={handleStart}
              disabled={pending || (isCasePreview && !caseItem)}
            >
              {pending ? '正在启动试听…' : '开始试听'}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
