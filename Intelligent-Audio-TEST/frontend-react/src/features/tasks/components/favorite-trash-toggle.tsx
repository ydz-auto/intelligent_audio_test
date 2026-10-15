/**
 * 收藏 / 回收站工具条（09_任务域.md §3.4，日常页签内）：
 * 「只看收藏」toggle（Star 图标，favorite=true）｜「回收站」toggle（Trash2 图标）。
 * 互斥联动：进回收站清空收藏态与勾选集（INT-215/320 实测口径）。
 */
import { Star, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/lib/utils'

export interface FavoriteTrashState {
  favorite: boolean
  trash: boolean
}

export function FavoriteTrashToggle({
  value,
  onChange,
}: {
  value: FavoriteTrashState
  onChange: (next: FavoriteTrashState) => void
}) {
  const [hover, setHover] = useState<'favorite' | 'trash' | null>(null)

  const toggleFavorite = () => {
    if (value.trash) return // 回收站态收藏钮置灰
    onChange({ favorite: !value.favorite, trash: false })
  }

  const toggleTrash = () => {
    onChange({ favorite: false, trash: !value.trash }) // 进回收站清空收藏态
  }

  return (
    <div
      className='bg-muted/60 inline-flex h-7 items-center rounded-lg border p-0.5'
      onMouseLeave={() => setHover(null)}
    >
      <button
        type='button'
        aria-pressed={value.favorite}
        disabled={value.trash}
        title='只看收藏'
        onClick={toggleFavorite}
        onMouseEnter={() => setHover('favorite')}
        className={cn(
          'inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors disabled:pointer-events-none disabled:opacity-40',
          value.favorite
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        )}
      >
        <Star
          aria-hidden='true'
          className={cn('size-3.5', hover === 'favorite' && 'fill-current')}
        />
        只看收藏
      </button>
      <button
        type='button'
        aria-pressed={value.trash}
        title='回收站'
        onClick={toggleTrash}
        onMouseEnter={() => setHover('trash')}
        className={cn(
          'inline-flex h-6 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors',
          value.trash
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        )}
      >
        <Trash2
          aria-hidden='true'
          className={cn('size-3.5', hover === 'trash' && 'text-destructive')}
        />
        回收站
      </button>
    </div>
  )
}
