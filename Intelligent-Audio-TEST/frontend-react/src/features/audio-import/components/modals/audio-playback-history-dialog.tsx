/**
 * 音频播放历史弹窗（§6.24；Dialog sm:max-w-2xl）。
 * StaticDataTable 列表（播放时间/使用的测试用例/播放设备/结果/时长，音频导入功能设计文档.md:196-200）。
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { AudioAsset } from '@/domain/models/audio'
import { formatDateTime } from '@/features/audio-import/lib/format'

export type AudioPlaybackHistoryDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

const MOCK_PLAYBACK_HISTORY = [
  { id: 1, at: '2026-10-15T09:20:00Z', testCase: '客厅_中文_唤醒测试_用例01', device: '干声测试音频接口 A', result: 'success', duration: '00:42' },
  { id: 2, at: '2026-10-14T16:05:00Z', testCase: '客厅_中文_命令集_用例02', device: '蓝牙音箱', result: 'success', duration: '00:42' },
  { id: 3, at: '2026-10-12T11:40:00Z', testCase: '客厅_中文_命令集_用例03', device: '干声测试音频接口 A', result: 'failed', duration: '00:38' },
  { id: 4, at: '2026-10-10T14:12:00Z', testCase: '客厅_中文_命令集_用例04', device: '噪声测试音频接口 B', result: 'success', duration: '00:42' },
]

export function AudioPlaybackHistoryDialog(props: AudioPlaybackHistoryDialogProps) {
  const audio = props.audio

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>播放历史</DialogTitle>
          <DialogDescription>{audio ? `「${audio.name}」的播放记录` : '播放记录'}</DialogDescription>
        </DialogHeader>

        <div className='overflow-x-auto'>
          <table className='w-full min-w-[520px] text-[13px]'>
            <thead>
              <tr className='bg-[var(--table-header)] text-xs'>
                <th className='px-3 py-2 text-left font-medium'>播放时间</th>
                <th className='px-3 py-2 text-left font-medium'>使用的测试用例</th>
                <th className='px-3 py-2 text-left font-medium'>播放设备</th>
                <th className='px-3 py-2 text-left font-medium'>结果</th>
                <th className='px-3 py-2 text-right font-medium'>时长</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_PLAYBACK_HISTORY.map((row) => (
                <tr key={row.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                  <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                    {formatDateTime(row.at)}
                  </td>
                  <td className='px-3 py-2'>{row.testCase}</td>
                  <td className='px-3 py-2'>{row.device}</td>
                  <td className='px-3 py-2'>
                    <Badge
                      variant='outline'
                      className={
                        row.result === 'success'
                          ? 'gap-1 rounded-md px-1.5 font-normal text-[var(--success)]'
                          : 'gap-1 rounded-md px-1.5 font-normal text-[var(--destructive)]'
                      }
                    >
                      <span
                        aria-hidden='true'
                        className={
                          row.result === 'success'
                            ? 'bg-[var(--success)] size-1.5 rounded-full'
                            : 'bg-[var(--destructive)] size-1.5 rounded-full'
                        }
                      />
                      {row.result === 'success' ? '成功' : '失败'}
                    </Badge>
                  </td>
                  <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                    {row.duration}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
