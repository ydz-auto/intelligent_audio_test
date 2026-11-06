/**
 * 收藏 / 回收站工具条（规范 §3.8，对位现状 FavoriteTrashBar）：
 * 「仅看收藏」Switch（favorite=true）+「回收站」Toggle（deleted=true）。
 */
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'

interface ReportFavoriteTrashBarProps {
  favoriteOnly: boolean
  trashMode: boolean
  favoriteCount: number
  onFavoriteOnlyChange: (value: boolean) => void
  onTrashModeChange: (value: boolean) => void
}

export function ReportFavoriteTrashBar({
  favoriteOnly,
  trashMode,
  favoriteCount,
  onFavoriteOnlyChange,
  onTrashModeChange,
}: ReportFavoriteTrashBarProps) {
  return (
    <div className='flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2'>
      <label className='text-muted-foreground flex items-center gap-2 text-sm'>
        <Switch
          checked={favoriteOnly}
          onCheckedChange={onFavoriteOnlyChange}
          aria-label='仅看收藏'
        />
        仅看收藏
        <Badge variant='secondary' className='font-mono tabular-nums'>
          {favoriteCount}
        </Badge>
      </label>
      <label className='text-muted-foreground flex items-center gap-2 text-sm'>
        <Switch
          checked={trashMode}
          onCheckedChange={onTrashModeChange}
          aria-label='回收站模式'
        />
        回收站
      </label>
    </div>
  )
}
