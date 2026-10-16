/**
 * 音频类型徽章（§5.3 列；StatusBadge 对位——dry=干声 success/noise=噪声 info/
 * prompt=提示词音频 warning/mixed=混合音频 neutral，§7 状态徽章口径）。
 */
import { Badge } from '@/components/ui/badge'
import type { AudioType } from '@/domain/models/audio'

const AUDIO_TYPE_META: Record<
  AudioType,
  { label: string; variant: 'success' | 'info' | 'warning' | 'neutral' }
> = {
  dry: { label: '干声', variant: 'success' },
  noise: { label: '噪声', variant: 'info' },
  prompt: { label: '提示词音频', variant: 'warning' },
  mixed: { label: '混合音频', variant: 'neutral' },
}

export function AudioTypeBadge({ type }: { type: AudioType | null }) {
  if (!type) return <span className='text-muted-foreground'>—</span>
  const meta = AUDIO_TYPE_META[type]
  return (
    <Badge variant='outline' className='gap-1 rounded-md px-1.5 font-normal'>
      <span aria-hidden='true' className={cnToneDot(meta.variant)} />
      {meta.label}
    </Badge>
  )
}

function cnToneDot(variant: 'success' | 'info' | 'warning' | 'neutral') {
  switch (variant) {
    case 'success':
      return 'bg-[var(--success)] size-1.5 rounded-full'
    case 'info':
      return 'bg-[var(--info)] size-1.5 rounded-full'
    case 'warning':
      return 'bg-[var(--warning)] size-1.5 rounded-full'
    default:
      return 'bg-muted-foreground/60 size-1.5 rounded-full'
  }
}
