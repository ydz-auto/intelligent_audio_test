/**
 * 新增/编辑 API 弹窗（§5.3；interfaces/features/test-execution/modals；Dialog sm:max-w-lg）。
 * RHF + zod：名称 / 关联算法（Select，默认带全局算法）/ 最大并发 /
 * 描述 / 密钥（password + 显隐 Eye）/ 其他配置（Textarea JSON，aria-invalid 红描边 +
 * 「JSON 格式不正确」）/ 端点列表（唯一端点入口——INT-1223 移除 Master URL 后补齐端点编辑器，
 * 保证从开始测试页可新建含端点的 API；复用 device-mutate-drawer 端点编辑器形态）；
 * 主钮「保存」（进行中「保存中…」）；成功 toast「API 已保存」+ 列表失效重拉（api_config:create/update）。
 */
import { Eye, EyeOff, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
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
  algorithmType: z.string().min(1, '请输入必填项'),
  maxProcess: z.number().int().min(1).max(128),
  description: z.string().optional(),
  otherConfig: z.string().optional(),
})

type ApiForm = z.infer<typeof apiFormSchema>

/** 端点编辑行（INT-1223：复用 device-mutate-drawer 端点编辑器形态；端点四整数校验项齐全——INT-1362 补优先级/音频时长） */
interface EndpointFormRow {
  key: string
  endpoint: string
  name: string
  priority: string
  maxProcess: string
  maxTimeout: string
  maxAudioDuration: string
}

const ENDPOINT_EMPTY: EndpointFormRow = {
  key: '',
  endpoint: '',
  name: '',
  priority: '1',
  maxProcess: '1',
  maxTimeout: '30',
  maxAudioDuration: '60',
}

function endpointKey(): string {
  return Math.random().toString(36).slice(2, 9)
}

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
  const [endpoints, setEndpoints] = useState<EndpointFormRow[]>([])

  const form = useForm<ApiForm>({
    resolver: zodResolver(apiFormSchema),
    values: {
      name: api?.name ?? '',
      apiKey: '',
      algorithmType:
        api?.algorithmType ??
        algorithmList.find((a) => a.id === globalAlgorithmId)?.name ??
        '',
      maxProcess: api?.defaultMaxProcess ?? 5,
      description: api?.description ?? '',
      otherConfig: '',
    },
  })

  // 端点列表（唯一端点入口；编辑回显，关闭清空）
  useEffect(() => {
    if (open && api) {
      setEndpoints(
        (api.endpoints ?? []).map((ep) => ({
          key: endpointKey(),
          endpoint: ep.endpoint,
          name: ep.name ?? '',
          priority: String(ep.priority ?? 1),
          maxProcess: String(ep.maxProcess ?? 1),
          maxTimeout: String(ep.maxTimeout ?? 30),
          maxAudioDuration: String(ep.maxAudioDuration ?? 60),
        }))
      )
    } else if (!open) {
      setEndpoints([])
    }
  }, [open, api])

  const updateEndpoint = (key: string, patch: Partial<EndpointFormRow>) => {
    setEndpoints((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const addEndpoint = () => {
    setEndpoints((prev) => [...prev, { ...ENDPOINT_EMPTY, key: endpointKey() }])
  }

  const removeEndpoint = (key: string) => {
    setEndpoints((prev) => prev.filter((row) => row.key !== key))
  }

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
      algorithmType: values.algorithmType,
      defaultMaxProcess: values.maxProcess,
      description: values.description || null,
      endpoints: endpoints
        .filter((row) => row.endpoint.trim())
        .map((row) => ({
          id: null,
          endpoint: row.endpoint.trim(),
          name: row.name.trim() || null,
          priority: Number(row.priority) || 1,
          maxProcess: Number(row.maxProcess) || 1,
          maxTimeout: Number(row.maxTimeout) || 30,
          maxAudioDuration: Number(row.maxAudioDuration) || 60,
          status: 'online',
          healthScore: null,
          description: null,
        })),
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

          {/* 端点列表（INT-1223：Master URL 移除后唯一端点入口——保证从开始测试页可新建含端点的 API） */}
          <div className='space-y-1.5'>
            <div className='flex items-center justify-between'>
              <Label>端点列表</Label>
              <Button
                type='button'
                variant='outline'
                size='sm'
                className='h-7 gap-1 text-xs'
                onClick={addEndpoint}
              >
                <Plus aria-hidden='true' className='size-3.5' />
                添加端点
              </Button>
            </div>
            {endpoints.length === 0 ? (
              <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
                暂无端点，点击「添加端点」配置（优先级/最大进程/超时/音频时长）
              </p>
            ) : (
              <div className='flex flex-col gap-2'>
                {endpoints.map((row) => (
                  <div key={row.key} className='border-border/60 flex flex-col gap-1.5 rounded-lg border p-2'>
                    <div className='flex items-center gap-1.5'>
                      <Input
                        value={row.endpoint}
                        onChange={(e) => updateEndpoint(row.key, { endpoint: e.target.value })}
                        placeholder='https://…'
                        className='h-7 flex-1 font-mono text-xs'
                        aria-label='端点 URL'
                      />
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-6 text-destructive'
                        aria-label='删除端点'
                        onClick={() => removeEndpoint(row.key)}
                      >
                        <X aria-hidden='true' className='size-3.5' />
                      </Button>
                    </div>
                    <div className='grid grid-cols-5 gap-1.5'>
                      <Input
                        value={row.name}
                        onChange={(e) => updateEndpoint(row.key, { name: e.target.value })}
                        placeholder='名称'
                        className='h-7 text-xs'
                      />
                      <Input
                        value={row.priority}
                        type='number'
                        min={1}
                        max={10}
                        onChange={(e) => updateEndpoint(row.key, { priority: e.target.value })}
                        placeholder='优先级'
                        className='h-7 text-xs'
                      />
                      <Input
                        value={row.maxProcess}
                        type='number'
                        min={1}
                        max={100}
                        onChange={(e) => updateEndpoint(row.key, { maxProcess: e.target.value })}
                        placeholder='最大进程'
                        className='h-7 text-xs'
                      />
                      <Input
                        value={row.maxTimeout}
                        type='number'
                        min={1}
                        max={300}
                        onChange={(e) => updateEndpoint(row.key, { maxTimeout: e.target.value })}
                        placeholder='超时(s)'
                        className='h-7 text-xs'
                      />
                      <Input
                        value={row.maxAudioDuration}
                        type='number'
                        min={1}
                        onChange={(e) => updateEndpoint(row.key, { maxAudioDuration: e.target.value })}
                        placeholder='音频时长(s)'
                        className='h-7 text-xs'
                      />
                    </div>
                  </div>
                ))}
              </div>
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
