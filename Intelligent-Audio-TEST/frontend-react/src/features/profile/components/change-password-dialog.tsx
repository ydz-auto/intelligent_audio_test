/**
 * 修改密码对话框（13_个人中心.md §3.5.1/§6，对位 newAPI change-password-dialog.tsx）：
 * Dialog + RHF/zod 三字段（当前/新/确认），新密码下限 6 位对齐平台
 * AUTH_PASSWORD_MIN_LENGTH（默认 6，§4.3-1），上限 128 沿用 newAPI 策略。
 * ⚠️ 后端自助改密端点未落（§4.3-1），入口隐藏、本组件仅保留待接入——
 * 提交走 passwordApi 桩，未落端点前调用即抛「待后端立项」错误提示，不出现假成功。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'

import { PasswordInput } from '@/components/password-input'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { changeMyPassword } from '@/infrastructure/api/passwordApi'

import {
  CHANGE_PASSWORD_DIALOG_FIELD_CONFIRM,
  CHANGE_PASSWORD_DIALOG_FIELD_CURRENT,
  CHANGE_PASSWORD_DIALOG_FIELD_NEW,
  CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CONFIRM,
  CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CURRENT,
  CHANGE_PASSWORD_DIALOG_PLACEHOLDER_NEW,
  CHANGE_PASSWORD_DIALOG_TITLE,
  CHANGE_PASSWORD_MIN_LENGTH_MESSAGE,
  CHANGE_PASSWORD_MISMATCH_MESSAGE,
  CHANGE_PASSWORD_SAME_MESSAGE,
  CHANGE_PASSWORD_CANCEL,
  CHANGE_PASSWORD_SAVE,
  CHANGE_PASSWORD_SAVING,
  CHANGE_PASSWORD_SUCCESS_TOAST,
} from '../constants'

const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, '请输入当前密码'),
    newPassword: z.string().min(6, CHANGE_PASSWORD_MIN_LENGTH_MESSAGE),
    confirmPassword: z.string().min(1, '请再次输入新密码'),
  })
  .refine((values) => values.newPassword === values.confirmPassword, {
    message: CHANGE_PASSWORD_MISMATCH_MESSAGE,
    path: ['confirmPassword'],
  })
  .refine((values) => values.newPassword !== values.currentPassword, {
    message: CHANGE_PASSWORD_SAME_MESSAGE,
    path: ['newPassword'],
  })

type ChangePasswordForm = z.infer<typeof changePasswordSchema>

export function ChangePasswordDialog({
  open,
  onOpenChange,
  username,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  username: string
}) {
  const form = useForm<ChangePasswordForm>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
  })

  async function onSubmit(values: ChangePasswordForm) {
    try {
      await changeMyPassword(values.currentPassword, values.newPassword)
      toast.success(CHANGE_PASSWORD_SUCCESS_TOAST)
      onOpenChange(false)
      form.reset()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '密码修改失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{CHANGE_PASSWORD_DIALOG_TITLE}</DialogTitle>
          <DialogDescription>为账号 {username} 更新登录密码</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className='grid gap-4'
          noValidate
        >
          <div className='grid gap-2'>
            <Label htmlFor='profile-current-password'>
              {CHANGE_PASSWORD_DIALOG_FIELD_CURRENT}
            </Label>
            <PasswordInput
              id='profile-current-password'
              placeholder={CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CURRENT}
              autoComplete='current-password'
              {...form.register('currentPassword')}
            />
            {form.formState.errors.currentPassword && (
              <p className='text-destructive text-sm'>
                {form.formState.errors.currentPassword.message}
              </p>
            )}
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='profile-new-password'>
              {CHANGE_PASSWORD_DIALOG_FIELD_NEW}
            </Label>
            <PasswordInput
              id='profile-new-password'
              placeholder={CHANGE_PASSWORD_DIALOG_PLACEHOLDER_NEW}
              autoComplete='new-password'
              {...form.register('newPassword')}
            />
            {form.formState.errors.newPassword && (
              <p className='text-destructive text-sm'>
                {form.formState.errors.newPassword.message}
              </p>
            )}
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='profile-confirm-password'>
              {CHANGE_PASSWORD_DIALOG_FIELD_CONFIRM}
            </Label>
            <PasswordInput
              id='profile-confirm-password'
              placeholder={CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CONFIRM}
              autoComplete='new-password'
              {...form.register('confirmPassword')}
            />
            {form.formState.errors.confirmPassword && (
              <p className='text-destructive text-sm'>
                {form.formState.errors.confirmPassword.message}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              type='button'
              variant='outline'
              disabled={form.formState.isSubmitting}
              onClick={() => onOpenChange(false)}
            >
              {CHANGE_PASSWORD_CANCEL}
            </Button>
            <Button type='submit' disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? (
                <>
                  <Loader2 className='animate-spin' aria-hidden='true' />
                  {CHANGE_PASSWORD_SAVING}
                </>
              ) : (
                CHANGE_PASSWORD_SAVE
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
