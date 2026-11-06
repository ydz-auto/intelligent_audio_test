/**
 * 设备操作参数小弹窗（16_设备域.md §3.4.1：install/uninstall，P3-31 补口）。
 * 安装应用：file_path/package_name 输入；卸载应用：package_name 输入。
 * RHF+zod（schema 见 lib/device-operate-schema.ts）；主钮提交中「执行中...」。
 */
import { PackageOpen, Upload } from 'lucide-react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'

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
  installAppSchema,
  uninstallAppSchema,
  type InstallAppForm,
  type UninstallAppForm,
} from '@/features/devices/lib/device-operate-schema'
import type { TestDevice } from '@/domain/models/testDevice'

export type DeviceOperateKind = 'install-app' | 'uninstall-app'

export interface DeviceOperateDialogProps {
  open: boolean
  kind: DeviceOperateKind | null
  device: TestDevice | null
  onOpenChange: (open: boolean) => void
  onConfirm: (kind: DeviceOperateKind, filePath: string, packageName: string) => void
}

export function DeviceOperateDialog(props: DeviceOperateDialogProps) {
  const isInstall = props.kind === 'install-app'

  const installForm = useForm<InstallAppForm>({
    resolver: zodResolver(installAppSchema),
    defaultValues: { filePath: '', packageName: '' },
  })
  const uninstallForm = useForm<UninstallAppForm>({
    resolver: zodResolver(uninstallAppSchema),
    defaultValues: { packageName: '' },
  })

  // INT-1480 P3-1：关窗不清空 → 重开残留上次输入。useForm 只认挂载时的 defaultValues，
  // 而本组件在 open=false 时 return null 但不卸载，故每次打开（含 Esc/遮罩/取消钮关闭后重开）显式 reset。
  useEffect(() => {
    if (!props.open) return
    installForm.reset({ filePath: '', packageName: '' })
    uninstallForm.reset({ packageName: '' })
  }, [props.open, props.kind, installForm, uninstallForm])

  if (!props.open || !props.kind) return null

  const deviceName = props.device?.name ?? ''
  const title = isInstall ? '安装应用' : '卸载应用'

  const handleInstallSubmit = (values: InstallAppForm) => {
    props.onConfirm('install-app', values.filePath.trim(), values.packageName.trim())
  }

  const handleUninstallSubmit = (values: UninstallAppForm) => {
    props.onConfirm('uninstall-app', '', values.packageName.trim())
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            对设备「{deviceName}」执行{isInstall ? '安装应用' : '卸载应用'}操作。
          </DialogDescription>
        </DialogHeader>

        {isInstall ? (
          <form onSubmit={installForm.handleSubmit(handleInstallSubmit)} className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='op-file-path'>应用安装包路径 *</Label>
              <Input
                id='op-file-path'
                placeholder='如：/sdcard/app.apk'
                aria-invalid={Boolean(installForm.formState.errors.filePath)}
                {...installForm.register('filePath')}
              />
              {installForm.formState.errors.filePath && (
                <p className='text-destructive text-xs'>{installForm.formState.errors.filePath.message}</p>
              )}
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='op-package'>应用包名 *</Label>
              <Input
                id='op-package'
                placeholder='如：com.example.app'
                aria-invalid={Boolean(installForm.formState.errors.packageName)}
                {...installForm.register('packageName')}
              />
              {installForm.formState.errors.packageName && (
                <p className='text-destructive text-xs'>{installForm.formState.errors.packageName.message}</p>
              )}
            </div>
            <DialogFooter>
              <Button variant='outline' type='button' onClick={() => props.onOpenChange(false)}>
                取消
              </Button>
              <Button type='submit' className='gap-1.5'>
                <Upload aria-hidden='true' className='size-3.5' />
                执行安装
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <form onSubmit={uninstallForm.handleSubmit(handleUninstallSubmit)} className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='op-uninstall-package'>应用包名 *</Label>
              <Input
                id='op-uninstall-package'
                placeholder='如：com.example.app'
                aria-invalid={Boolean(uninstallForm.formState.errors.packageName)}
                {...uninstallForm.register('packageName')}
              />
              {uninstallForm.formState.errors.packageName && (
                <p className='text-destructive text-xs'>{uninstallForm.formState.errors.packageName.message}</p>
              )}
            </div>
            <DialogFooter>
              <Button variant='outline' type='button' onClick={() => props.onOpenChange(false)}>
                取消
              </Button>
              <Button type='submit' variant='destructive' className='gap-1.5'>
                <PackageOpen aria-hidden='true' className='size-3.5' />
                执行卸载
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
