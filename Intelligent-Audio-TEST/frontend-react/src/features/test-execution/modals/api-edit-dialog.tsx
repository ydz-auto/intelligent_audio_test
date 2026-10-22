/**
 * 新增/编辑 API 弹窗（§5.3；interfaces/features/test-execution/modals；Dialog sm:max-w-lg）。
 * RHF + zod：名称 / Master URL（可选，非空 URL 校验）/ 关联算法（Select，默认带全局算法）/ 最大并发 /
 * 描述 / 密钥（password + 显隐 Eye）/ 其他配置（Textarea JSON，aria-invalid 红描边 +
 * 「JSON 格式不正确」）；主钮「保存」（进行中「保存中…」）；成功 toast「API 已保存」+
 * 列表失效重拉（api_config:create/update）。
 */
import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { ApiConfig } from '@/domain/models/apiConfig'
import { cn } from '@/lib/utils'

const apiFormSchema = z.object({
  name: z.string().min(1, '请输入必填项'),
  apiKey: z.string().optional(),
  /** Master 入口 URL（可选；api_endpoints 为主，空值提交侧归一 null；非空仍做 URL 校验） */
  apiUrl: z.union([z.string().url('请输入合法的 URL（https://…）'), z.literal('')]).optional(),
  algorithmType: z.string().min(1, '请输入必填项'),
  maxProcess: z.number().int().min(1).max(128),
  description: z.string().optional(),
  otherConfig: z.string().optional(),
})

type ApiForm = z.infer<typeof apiFormSchema>

interface ApiEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 传入 = 编辑；undefined = 新增 */
  api?: ApiConfig
}

export function ApiEditDialog({ open, onOpenChange, api }: ApiEditDialogProps) {
  const { save } = useApisCrud()
  const globalAlgorithmId = useAlgorithmStore((s) => s.algorithmId)
  const { data: algorithmOptions } = useTestAlgorithmOptions()
  const algorithmList = algorithmOptions ?? []
  const [showKey, setShowKey] = useState(false)

  const form = useForm<ApiForm>({
    resolver: zodResolver(apiFormSchema),
    values: {
      name: api?.name ?? '',
      apiKey: '',
      apiUrl: api?.apiUrl ?? '',
      algorithmType:
        api?.algorithmType ??
        algorithmList.find((a) => a.id === globalAlgorithmId)?.name ??
        '',
      maxProcess: api?.defaultMaxProcess ?? 5,
      description: api?.description ?? '',
      otherConfig: '',
    },
  })

  const handleSave = async (values: ApiForm) => {
    // 其他配置 JSON 校验（现 configJson 口径加校验态）
    if (values.otherConfig && values.otherConfig.trim()) {
      try {
        JSON.parse(values.otherConfig)
      } catch {
        form.setError('otherConfig', { message: 'JSON 格式不正确' })
        return
      }
    }
    await save({
      id: api?.id,
      name: values.name,
      // INT-1223/1229：Master URL 可选，空值归一 null（防 update 覆盖既有 api_url）
      apiUrl: values.apiUrl || null,
      algorithmType: values.algorithmType,
      defaultMaxProcess: values.maxProcess,
      description: values.description || null,
    })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{api ? '编辑 API' : '新增 API'}</DialogTitle>
          <DialogDescription>
            {api ? '修改被测 API 配置，保存后列表自动刷新' : '新增被测 API，保存后列表自动刷新'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(handleSave)} className='space-y-3'>
          <div className='space-y-1.5'>
            <Label htmlFor='api-name'>API 名称 *</Label>
            <Input
              id='api-name'
              placeholder='请输入 API 名称'
              aria-invalid={Boolean(form.formState.errors.name)}
              {...form.register('name')}
            />
            {form.formState.errors.name && (
              <p className='text-destructive text-xs'>{form.formState.errors.name.message}</p>
            )}
          </div>

          <div className='space-y-1.5'>
            <Label htmlFor='api-key'>API 密钥</Label>
            <div className='relative'>
              <Input
                id='api-key'
                type={showKey ? 'text' : 'password'}
                placeholder='可选，用于鉴权调用'
                className='pr-9'
                {...form.register('apiKey')}
              />
              <button
                type='button'
                aria-label={showKey ? '隐藏密钥' : '显示密钥'}
                className='text-muted-foreground hover:text-foreground absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5'
                onClick={() => setShowKey((v) => !v)}
              >
                {showKey ? <EyeOff aria-hidden='true' className='size-4' /> : <Eye aria-hidden='true' className='size-4' />}
              </button>
            </div>
          </div>

          <div className='space-y-1.5'>
            <Label htmlFor='api-url'>Master URL（可选）</Label>
            <Input
              id='api-url'
              placeholder='https://…'
              aria-invalid={Boolean(form.formState.errors.apiUrl)}
              {...form.register('apiUrl')}
            />
            {form.formState.errors.apiUrl && (
              <p className='text-destructive text-xs'>{form.formState.errors.apiUrl.message}</p>
            )}
          </div>

          <div className='space-y-1.5'>
            <Label>关联算法 *</Label>
            <Select
              value={form.watch('algorithmType')}
              onValueChange={(value) => form.setValue('algorithmType', value ?? '')}
            >
              <SelectTrigger className={cn('w-full justify-between', !form.watch('algorithmType') && 'text-muted-foreground')}>
                <SelectValue placeholder='请选择算法' />
              </SelectTrigger>
              <SelectContent>
                {algorithmList.map((algorithm) => (
                  <SelectItem key={algorithm.id} value={algorithm.name}>
                    {algorithm.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.algorithmType && (
              <p className='text-destructive text-xs'>{form.formState.errors.algorithmType.message}</p>
            )}
          </div>

          <div className='space-y-1.5'>
            <Label htmlFor='max-process'>最大并发</Label>
            <Input
              id='max-process'
              type='number'
              min={1}
              max={128}
              {...form.register('maxProcess', { valueAsNumber: true })}
            />
          </div>

          <div className='space-y-1.5'>
            <Label htmlFor='api-desc'>描述</Label>
            <Textarea id='api-desc' rows={2} placeholder='API 用途说明（可选）' {...form.register('description')} />
          </div>

          <div className='space-y-1.5'>
            <Label htmlFor='other-config'>其他配置</Label>
            <Textarea
              id='other-config'
              rows={4}
              placeholder='JSON 格式，如 {"audioConfig": {"sampleRate": 16000}}'
              className='font-mono text-xs'
              aria-invalid={Boolean(form.formState.errors.otherConfig)}
              {...form.register('otherConfig')}
            />
            {form.formState.errors.otherConfig && (
              <p className='text-destructive text-xs'>{form.formState.errors.otherConfig.message}</p>
            )}
          </div>

          <DialogFooter>
            <Button variant='outline' type='button' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type='submit'>{form.formState.isSubmitting ? '保存中…' : '保存'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
