/**
 * 新增/编辑 API 弹窗（§5.3；interfaces/features/test-execution/modals；Dialog sm:max-w-lg）。
 * RHF + zod：名称 / 关联算法（Select，默认带全局算法）/ 最大并发 /
 * 描述 / 其他配置（Textarea JSON，aria-invalid 红描边 +
 * 「JSON 格式不正确」）/ 端点列表（唯一端点入口——INT-1223 移除 Master URL 后补齐端点编辑器，
 * 保证从开始测试页可新建含端点的 API；复用 device-mutate-drawer 端点编辑器形态）；
 * 主钮「保存」（进行中「保存中…」）；成功 toast「API 已保存」+ 列表失效重拉（api_config:create/update）。
 */
import { Plus, X } from 'lucide-react'
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
  algorithmType: z.string().min(1, '请输入必填项'),
  maxProcess: z.number().int().min(1).max(128),
  description: z.string().optional(),
  otherConfig: z.string().optional(),
  // INT-1433：设备类型可选（http_api/websocket_api）或 auto 按端点协议派生（缺省 http_api）
  deviceType: z.enum(['auto', 'http_api', 'websocket_api']),
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
  /** INT-1437 密钥池：textarea 草稿（瞬态，保存时 adapter 拆行转 api_keys） */
  apiKeysText: string
  /** 密钥池摘要（编辑回显「已配置 N 个密钥 / 尾号…」，完整密钥不回显） */
  apiKeysSummary: { count: number; tails: string[] } | null
}

const ENDPOINT_EMPTY: EndpointFormRow = {
  key: '',
  endpoint: '',
  name: '',
  priority: '1',
  maxProcess: '1',
  maxTimeout: '30',
  maxAudioDuration: '60',
  apiKeysText: '',
  apiKeysSummary: null,
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
  const [endpoints, setEndpoints] = useState<EndpointFormRow[]>([])
  // INT-1433：设备类型派生提示（auto 态展示实际将路由到的类型）
  const firstEndpoint = endpoints.find((e) => e.endpoint.trim())?.endpoint.trim() ?? ''

  const form = useForm<ApiForm>({
    resolver: zodResolver(apiFormSchema),
    values: {
      name: api?.name ?? '',
      algorithmType:
        api?.algorithmType ??
        algorithmList.find((a) => a.id === globalAlgorithmId)?.name ??
        '',
      maxProcess: api?.defaultMaxProcess ?? 5,
      description: api?.description ?? '',
      otherConfig: '',
      deviceType:
        api?.deviceType === 'http_api' || api?.deviceType === 'websocket_api'
          ? api.deviceType
          : 'auto',
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
          apiKeysText: '',
          apiKeysSummary: ep.apiKeysSummary ?? null,
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
      // INT-1433：auto = 不落显式 deviceType（建任务时按端点协议派生）
      deviceType: values.deviceType === 'auto' ? null : values.deviceType,
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
          apiKeysSummary: row.apiKeysSummary,
          // INT-1437 密钥池：textarea 草稿瞬态透传，adapter 拆行转 api_keys 落库
          apiKeysText: row.apiKeysText,
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

          {/* 设备类型（INT-1433：可选 http_api/websocket_api，或 auto 按端点协议派生，缺省 http_api；
              Realtime WS（websocket_api）是建任务路由到 Realtime 执行器的前置） */}
          <div className='space-y-1.5'>
            <Label>设备类型</Label>
            <Select
              value={form.watch('deviceType')}
              onValueChange={(value) =>
                form.setValue('deviceType', (value ?? 'auto') as ApiForm['deviceType'])
              }
            >
              <SelectTrigger className='w-full justify-between'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='auto'>自动（按端点协议派生）</SelectItem>
                <SelectItem value='http_api'>HTTP API</SelectItem>
                <SelectItem value='websocket_api'>Realtime WS</SelectItem>
              </SelectContent>
            </Select>
            {form.watch('deviceType') === 'auto' && (
              <p className='text-muted-foreground text-xs'>
                {firstEndpoint
                  ? `将按端点协议派生为：${
                      /^wss?:\/\//i.test(firstEndpoint) ? 'Realtime WS' : 'HTTP API'
                    }`
                  : '未配置端点时缺省为 HTTP API'}
              </p>
            )}
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
                    {/* INT-1437 密钥池：端点行内多行 textarea（每行一个 key，整段粘贴自动拆行）；
                        编辑回显只显示摘要（count + 尾号），完整密钥不出现 */}
                    <div className='space-y-1'>
                      <Label className='text-xs'>密钥池（多密钥轮换）</Label>
                      {row.apiKeysSummary && row.apiKeysSummary.count > 0 && (
                        <p className='text-muted-foreground text-xs'>
                          已配置 {row.apiKeysSummary.count} 个密钥
                          {row.apiKeysSummary.tails.length > 0 && (
                            <>（尾号：{row.apiKeysSummary.tails.join('、')}）</>
                          )}
                          ，如需修改请重新输入完整密钥列表。
                        </p>
                      )}
                      <Textarea
                        rows={2}
                        value={row.apiKeysText}
                        onChange={(e) => updateEndpoint(row.key, { apiKeysText: e.target.value })}
                        placeholder='每行一个密钥，可整段粘贴自动拆行；留空则保留已配置密钥'
                        className='h-12 font-mono text-xs'
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
