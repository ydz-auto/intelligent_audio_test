/**
 * 分享报告 Dialog（15_报告域.md §4.12；报告管理功能设计文档.md:254-272 实测）。
 * 分享方式=生成分享链接/邮件分享/导出后分享；分享权限=访问权限（仅登录/指定人/公开）× 有效期 × 访问密码；
 * 分享统计=访问次数/访问时间；链接管理和撤销。状态由 application/use-report-share 承载（mock）。
 */
import { Copy, ExternalLink, Mail, Share2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { toast } from 'sonner'
import type {
  ReportShareState,
  ShareAccess,
  ShareExpiry,
  ShareMethod,
} from '@/application/report-view/use-report-share'

const SHARE_METHODS: { value: ShareMethod; label: string }[] = [
  { value: 'link', label: '生成分享链接' },
  { value: 'email', label: '邮件分享' },
  { value: 'export', label: '导出后分享' },
]

const ACCESS_OPTIONS: { value: ShareAccess; label: string }[] = [
  { value: 'login', label: '仅登录' },
  { value: 'specific', label: '指定人' },
  { value: 'public', label: '公开' },
]

const EXPIRY_OPTIONS: { value: ShareExpiry; label: string }[] = [
  { value: 'none', label: '永久' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: 'custom', label: '自定义' },
]

interface ReportShareDialogProps {
  reportName: string
  state: ReportShareState
  onOpenChange: (open: boolean) => void
  onMethodChange: (method: ShareMethod) => void
  onAccessChange: (access: ShareAccess) => void
  onExpiryChange: (expiry: ShareExpiry) => void
  onPasswordChange: (password: string) => void
  onRecipientsChange: (recipients: string) => void
  onEmailToChange: (emailTo: string) => void
  onGenerate: () => void
  onRevoke: () => void
  onCopy: () => void
  onRecordVisit: () => void
}

export function ReportShareDialog({
  reportName,
  state,
  onOpenChange,
  onMethodChange,
  onAccessChange,
  onExpiryChange,
  onPasswordChange,
  onRecipientsChange,
  onEmailToChange,
  onGenerate,
  onRevoke,
  onCopy,
  onRecordVisit,
}: ReportShareDialogProps) {
  return (
    <Dialog open={state.open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>分享报告</DialogTitle>
          <DialogDescription>
            「{reportName}」——生成分享链接 / 邮件分享 / 导出后分享，支持权限、有效期与访问密码。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 分享方式 */}
          <div role='group' aria-label='分享方式' className='flex flex-wrap gap-1.5'>
            {SHARE_METHODS.map((method) => (
              <button
                key={method.value}
                type='button'
                className={
                  state.method === method.value
                    ? 'bg-primary text-primary-foreground h-9 rounded-xl px-3 text-sm font-medium transition-colors'
                    : 'hover:bg-muted text-muted-foreground h-9 rounded-xl px-3 text-sm font-medium transition-colors'
                }
                onClick={() => onMethodChange(method.value)}
              >
                {method.label}
              </button>
            ))}
          </div>

          {/* 权限 × 有效期 × 密码 */}
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='flex flex-col gap-1.5'>
              <Label className='text-xs'>访问权限</Label>
              <Select
                value={state.access}
                onValueChange={(v) => onAccessChange((v ?? 'login') as ShareAccess)}
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align='start'>
                  {ACCESS_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='flex flex-col gap-1.5'>
              <Label className='text-xs'>有效期</Label>
              <Select
                value={state.expiry}
                onValueChange={(v) => onExpiryChange((v ?? 'none') as ShareExpiry)}
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align='start'>
                  {EXPIRY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {state.access === 'specific' && (
            <div className='flex flex-col gap-1.5'>
              <Label className='text-xs'>指定访问人</Label>
              <Input
                value={state.recipients}
                onChange={(e) => onRecipientsChange(e.target.value)}
                placeholder='输入用户名或邮箱，多个用逗号分隔'
                className='h-9'
              />
            </div>
          )}

          <div className='flex flex-col gap-1.5'>
            <Label className='text-xs'>访问密码</Label>
            <Input
              value={state.password}
              onChange={(e) => onPasswordChange(e.target.value)}
              placeholder='留空则不设访问密码'
              className='h-9'
            />
          </div>

          {/* 分享链接 */}
          {state.method === 'link' && (
            <div className='bg-muted/40 flex items-center gap-2 rounded-lg border p-2'>
              <Input
                readOnly
                value={state.shareUrl ?? '点击下方「生成分享链接」创建…'}
                className='h-9 flex-1 border-0 bg-transparent font-mono text-xs'
              />
              {state.shareUrl && (
                <Button variant='outline' size='sm' onClick={onCopy}>
                  <Copy data-icon='inline-start' />
                  复制
                </Button>
              )}
              {!state.shareUrl && (
                <Button size='sm' onClick={onGenerate}>
                  <ExternalLink data-icon='inline-start' />
                  生成分享链接
                </Button>
              )}
            </div>
          )}

          {state.method === 'email' && (
            <div className='flex flex-col gap-1.5'>
              <Label className='text-xs'>收件人</Label>
              <Input
                value={state.emailTo}
                onChange={(e) => onEmailToChange(e.target.value)}
                placeholder='name@example.com'
                className='h-9'
              />
              <Button size='sm' variant='outline' onClick={onGenerate}>
                <Mail data-icon='inline-start' />
                发送邮件分享
              </Button>
            </div>
          )}

          {state.method === 'export' && (
            <p className='text-muted-foreground text-sm leading-6'>
              导出后可分享：导出的报告文件（CSV/Excel/PDF/HTML）分享权限由导出文件载体决定。
            </p>
          )}

          {/* 分享统计 */}
          {state.shareUrl && (
            <div className='bg-card flex items-center justify-between rounded-lg border px-3 py-2.5'>
              <span className='text-muted-foreground text-xs'>分享统计</span>
              <span className='flex items-center gap-4 text-sm'>
                <span className='font-mono tabular-nums'>访问 {state.visits} 次</span>
                <span className='font-mono text-muted-foreground tabular-nums'>
                  最近 {state.lastVisitedAt ? new Date(state.lastVisitedAt).toLocaleString() : '—'}
                </span>
                <Button variant='ghost' size='sm' onClick={onRecordVisit}>
                  模拟访问
                </Button>
              </span>
            </div>
          )}
        </div>

        <DialogFooter className='flex items-center justify-between'>
          {state.shareUrl && (
            <Button variant='destructive' size='sm' onClick={onRevoke}>
              撤销链接
            </Button>
          )}
          <div className='flex gap-2'>
            <Button variant='ghost' size='sm' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              size='sm'
              onClick={() => {
                onOpenChange(false)
                toast.success('分享设置已保存')
              }}
            >
              <Share2 data-icon='inline-start' />
              保存
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
