/**
 * Access Token 明文展示对话框（features/profile/components/access-token，INT-1153）。
 * 创建成功后只显示一次明文（对齐 new-api access-token-dialog），复制后即关闭；
 * 明文不落任何缓存/Query 状态。
 */
import { CopyButton } from '@/components/copy-button'
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
import { Label } from '@/components/ui/label'

import {
  ACCESS_TOKEN_CLOSE,
  ACCESS_TOKEN_COPIED,
  ACCESS_TOKEN_COPY,
  ACCESS_TOKEN_FIELD,
  ACCESS_TOKEN_REVEAL_DESCRIPTION,
  ACCESS_TOKEN_REVEAL_TITLE,
} from './constants'

type AccessTokenRevealDialogProps = {
  token: string
  onClose: () => void
}

export function AccessTokenRevealDialog(props: AccessTokenRevealDialogProps) {
  return (
    <Dialog open onOpenChange={(open) => { if (!open) props.onClose() }}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{ACCESS_TOKEN_REVEAL_TITLE}</DialogTitle>
          <DialogDescription>{ACCESS_TOKEN_REVEAL_DESCRIPTION}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-2'>
          <Label htmlFor='generated-access-token'>{ACCESS_TOKEN_FIELD}</Label>
          <div className='flex gap-2'>
            <Input
              id='generated-access-token'
              value={props.token}
              readOnly
              autoComplete='off'
              className='font-mono text-xs'
            />
            <CopyButton
              value={props.token}
              variant='outline'
              tooltip={ACCESS_TOKEN_COPY}
              successTooltip={ACCESS_TOKEN_COPIED}
              aria-label={ACCESS_TOKEN_COPY}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={props.onClose}>{ACCESS_TOKEN_CLOSE}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
