/**
 * 设备参数配置弹窗（设备管理页 → 行操作「参数配置」）。
 *
 * 语义（真·设备级独立覆盖）：
 * - 读：`GET /algorithm/params?param_type=device&device_id=Y` 返回该设备的三层
 *   解析结果（算法级默认 → 绑定策略 → 本设备覆盖），逐行带 `resolved_from`；
 * - 写：新增 / 编辑 / 删除都落**设备级覆盖行**（带 device_id）：编辑算法级或策略行
 *   等价于新增本设备覆盖；
 * - 删除设备覆盖行即回落到上一层（策略 → 算法级声明）。
 * - 设备级**映射**由同目录 `device-mappings-section` 维护（同样是设备行覆盖算法级行）。
 * - **参数策略**：设备可绑定 scope=device 的策略（`device_param_bindings`），
 *   解析顺序 = 本设备覆盖 > 设备绑定策略 > 算法类型级默认；三层均在表内可见，
 *   因此已绑定策略时仍可「另存为新策略」（整份含策略层生效值）。
 *
 * 降级：缺 `algorithm:param_manage` → 参数区与映射区都只读；未选算法 → 空态提示。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  deviceMappingsQueryKey,
} from '@/application/devices/use-device-scope-mappings'
import {
  buildDeviceScopeProfileInput,
  deviceProfileQueryKeys,
  useDeviceParamProfileOptions,
} from '@/application/devices/use-device-param-profile'
import type { AlgorithmApiParam } from '@/domain/models/apiConfig'
import {
  bindDeviceProfile,
  cloneProfile,
  createProfile,
} from '@/infrastructure/api/param-profile-api'
import { ParamHistoryDialog } from '@/features/algorithm-config/param-history/param-history-dialog'
import { DeviceMappingsSection } from './device-mappings-section'
import {
  createDeviceScopeParam,
  deleteDeviceScopeParam,
  fetchDeviceScopeParams,
  updateDeviceScopeParam,
  type DeviceParamWriteInput,
} from '@/infrastructure/api/device-param-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

/** 设备参数类型（与 AlgorithmDeviceParam.param_type 同值域） */
const PARAM_TYPE_OPTIONS = [
  { value: 'text', label: '文本' },
  { value: 'audio_stream', label: '音频流' },
  { value: 'audio_file', label: '音频文件' },
  { value: 'text_file', label: '文本文件' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' },
  { value: 'json', label: 'JSON' },
] as const

const DIRECTION_OPTIONS = [
  { value: 'input', label: '输入' },
  { value: 'output', label: '输出' },
] as const

const PARAM_TYPE_LABEL: Record<string, string> = Object.fromEntries(
  PARAM_TYPE_OPTIONS.map((item) => [item.value, item.label])
)

/**
 * toast 用的失败文案：优先服务端可读 message；后端异常兜底会把 psycopg2 / 唯一
 * 索引原文（数百字符）透出，这类技术性文案回落成本页可读提示（INT-2341）。
 */
function readableError(error: unknown, fallback: string): string {
  const candidate = error as { userMessage?: unknown; message?: unknown } | null
  const message =
    typeof candidate?.userMessage === 'string' && candidate.userMessage
      ? candidate.userMessage
      : typeof candidate?.message === 'string'
        ? candidate.message
        : ''
  if (!message) return fallback
  if (
    message.length > 160 ||
    /psycopg2|Traceback|duplicate key|violates .*constraint/i.test(message)
  ) {
    return fallback
  }
  return message
}

interface DeviceParamsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  device: { id: number; name: string }
  /** 设备关联的算法类型（为空时用弹窗内下拉选择） */
  defaultAlgorithmType: string | null
}

interface ParamFormState {
  paramCode: string
  paramName: string
  paramType: string
  direction: 'input' | 'output'
  required: boolean
  defaultValue: string
  helpText: string
  /** 编辑设备级行时的 id；null = 新建 */
  paramId: number | null
}

const EMPTY_FORM: ParamFormState = {
  paramCode: '',
  paramName: '',
  paramType: 'text',
  direction: 'input',
  required: false,
  defaultValue: '',
  helpText: '',
  paramId: null,
}

/** 合并键：参数代码 + 方向（与后端唯一索引同口径） */
function rowKey(row: AlgorithmApiParam): string {
  return `${row.paramCode}|${row.direction}`
}

/** 设备作用域的三层来源 */
type ParamLayer = 'algorithm' | 'profile' | 'device'

const LAYER_BADGE: Record<
  ParamLayer,
  { label: string; variant: 'default' | 'secondary' | 'outline' }
> = {
  algorithm: { label: '算法级', variant: 'secondary' },
  profile: { label: '策略', variant: 'outline' },
  device: { label: '本设备', variant: 'default' },
}

export function DeviceParamsDialog({
  open,
  onOpenChange,
  device,
  defaultAlgorithmType,
}: DeviceParamsDialogProps) {
  const queryClient = useQueryClient()
  const { data: algorithmList = [] } = useTestAlgorithmOptions()
  const { hasPermission } = usePermissions()
  const canEdit = hasPermission('algorithm:param_manage')

  const [algorithmType, setAlgorithmType] = useState(defaultAlgorithmType ?? '')
  const [form, setForm] = useState<ParamFormState | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  useEffect(() => {
    if (open) setAlgorithmType(defaultAlgorithmType ?? '')
  }, [open, defaultAlgorithmType])

  const paramsQuery = useQuery({
    queryKey: ['devices', 'device-params', algorithmType, device.id],
    queryFn: () => fetchDeviceScopeParams(algorithmType, device.id),
    enabled: open && Boolean(algorithmType),
    staleTime: 0,
    retry: false,
  })

  /** 三层解析结果（后端已按 算法级默认 → 绑定策略 → 本设备覆盖 合并） */
  const effectiveRows = useMemo(() => paramsQuery.data ?? [], [paramsQuery.data])

  /** 行来源层：优先用后端 `resolvedFrom`，旧快照缺该键时按 deviceId 推断 */
  const layerOf = (row: AlgorithmApiParam): ParamLayer => {
    if (row.resolvedFrom === 'profile') return 'profile'
    if (row.resolvedFrom === 'device') return 'device'
    if (row.resolvedFrom === 'algorithm') return 'algorithm'
    return row.deviceId === device.id ? 'device' : 'algorithm'
  }

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['devices', 'device-params', algorithmType, device.id],
    })
  }

  /* ───────────────── 参数策略（绑定 / 另存 / 克隆） ───────────────── */

  const profileOptions = useDeviceParamProfileOptions(algorithmType, open, device.id)
  const [boundProfileId, setBoundProfileId] = useState<number | null>(null)
  const [nameDialog, setNameDialog] = useState<'create' | 'clone' | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')

  // 服务端回读值变化时才同步，避免覆盖刚完成的本地绑定结果
  useEffect(() => {
    setBoundProfileId(profileOptions.boundProfileId)
  }, [profileOptions.boundProfileId])

  /** 已绑定策略名（提示文案用；列表未加载到时回落 id） */
  const boundProfileName = useMemo(() => {
    if (boundProfileId == null) return null
    return (
      profileOptions.profiles.find((profile) => profile.id === boundProfileId)?.name ??
      `#${boundProfileId}`
    )
  }, [profileOptions.profiles, boundProfileId])

  /** 策略变化会影响参数与两桶映射的解析结果，全部失效 */
  const invalidateScope = () => {
    invalidate()
    void queryClient.invalidateQueries({
      queryKey: deviceMappingsQueryKey(algorithmType, device.id, 'case'),
    })
    void queryClient.invalidateQueries({
      queryKey: deviceMappingsQueryKey(algorithmType, device.id, 'evaluation'),
    })
    void queryClient.invalidateQueries({
      queryKey: deviceProfileQueryKeys.profiles(algorithmType),
    })
  }

  const bindMutation = useMutation({
    mutationFn: (profileId: number | null) => bindDeviceProfile(device.id, profileId),
    onSuccess: (result) => {
      setBoundProfileId(result.profileId)
      toast.success(result.profileId == null ? '已解绑策略' : '策略绑定已保存')
      invalidateScope()
    },
    onError: (error) =>
      toast.error(`绑定失败：${readableError(error, '请稍后重试')}`),
  })

  const createMutation = useMutation({
    mutationFn: async (input: { name: string; description: string | null }) => {
      const payload = await buildDeviceScopeProfileInput({
        algorithmType,
        deviceId: device.id,
        name: input.name,
        description: input.description,
      })
      return createProfile(payload)
    },
    onSuccess: (profile) => {
      toast.success('新策略已创建')
      setNameDialog(null)
      bindMutation.mutate(profile.id)
    },
    onError: (error) =>
      toast.error(`另存失败：${readableError(error, '保存参数策略失败，请稍后重试')}`),
  })

  const cloneMutation = useMutation({
    mutationFn: (input: { name: string; description: string | null }) => {
      if (boundProfileId == null) throw new Error('当前未绑定策略')
      return cloneProfile(boundProfileId, input)
    },
    onSuccess: (profile) => {
      toast.success('策略已克隆')
      setNameDialog(null)
      bindMutation.mutate(profile.id)
    },
    onError: (error) =>
      toast.error(`克隆失败：${readableError(error, '请稍后重试')}`),
  })

  const names = profileOptions.profiles.map((profile) => ({
    value: String(profile.id),
    label: profile.name,
  }))
  const UNBOUND = 'unbound'
  const profileItems = [{ value: UNBOUND, label: '未绑定（仅本设备覆盖）' }, ...names]

  const openNameDialog = (mode: 'create' | 'clone') => {
    setDraftName('')
    setDraftDescription('')
    setNameDialog(mode)
  }

  const submitNameDialog = () => {
    const name = draftName.trim()
    if (!name) {
      toast.error('请填写策略名称')
      return
    }
    const payload = { name, description: draftDescription.trim() || null }
    if (nameDialog === 'create') createMutation.mutate(payload)
    else if (nameDialog === 'clone') cloneMutation.mutate(payload)
  }

  const nameDialogPending = createMutation.isPending || cloneMutation.isPending

  const saveMutation = useMutation({
    mutationFn: async (state: ParamFormState) => {
      const payload: DeviceParamWriteInput = {
        algorithmType,
        deviceId: device.id,
        paramCode: state.paramCode.trim(),
        paramName: state.paramName.trim() || null,
        paramType: state.paramType,
        direction: state.direction,
        required: state.required,
        defaultValue: state.defaultValue.trim() || null,
        helpText: state.helpText.trim() || null,
        uiOrder: 0,
      }
      if (state.paramId != null) await updateDeviceScopeParam(state.paramId, payload)
      else await createDeviceScopeParam(payload)
    },
    onSuccess: () => {
      toast.success('设备参数已保存')
      setForm(null)
      invalidate()
    },
    onError: (error) =>
      toast.error(`保存失败：${readableError(error, '请稍后重试')}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (paramId: number) => deleteDeviceScopeParam(paramId),
    onSuccess: () => {
      toast.success('设备覆盖已删除，回落到算法级声明')
      invalidate()
    },
    onError: (error) =>
      toast.error(`删除失败：${readableError(error, '请稍后重试')}`),
  })

  const openOverride = (row: AlgorithmApiParam | null) => {
    setForm(
      row
        ? {
            paramCode: row.paramCode,
            paramName: row.paramName ?? '',
            paramType: row.paramType,
            direction: row.direction,
            required: row.required,
            defaultValue: row.defaultValue ?? '',
            helpText: row.helpText ?? '',
            // 只有本设备覆盖行可直接更新；算法级 / 策略行编辑 = 新增本设备覆盖
            paramId: layerOf(row) === 'device' ? row.id : null,
          }
        : { ...EMPTY_FORM }
    )
  }

  const submitForm = () => {
    if (!form) return
    if (!form.paramCode.trim()) {
      toast.error('参数代码必填')
      return
    }
    saveMutation.mutate(form)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* 与算法编辑弹窗同宽：两节映射表 7 列，3xl 太窄 */}
      <DialogContent className='sm:max-w-[min(1400px,92vw)]'>
        <DialogHeader>
          <DialogTitle>设备参数配置 · {device.name}</DialogTitle>
          <DialogDescription>
            设备级参数覆盖同算法类型下的默认声明；删除覆盖即回落到算法级声明。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <div className='flex flex-wrap items-center gap-2'>
            <Label className='text-xs'>关联算法</Label>
            <Select
              value={algorithmType}
              items={algorithmList.map((item) => ({ value: item.id, label: item.name }))}
              onValueChange={(value) => setAlgorithmType(value ?? '')}
            >
              <SelectTrigger className='w-56 justify-between' aria-label='关联算法'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {algorithmList.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='ml-auto h-7 gap-1 text-xs'
              disabled={!canEdit || !algorithmType}
              onClick={() => openOverride(null)}
            >
              <Plus aria-hidden='true' className='size-3.5' />
              新增设备参数
            </Button>
          </div>

          {algorithmType && (
            <div className='space-y-1.5'>
              <Label>参数策略</Label>
              <div className='flex flex-wrap items-center gap-2'>
                <Select
                  value={boundProfileId == null ? UNBOUND : String(boundProfileId)}
                  items={profileItems}
                  onValueChange={(value) => {
                    if (!value) return
                    bindMutation.mutate(value === UNBOUND ? null : Number(value))
                  }}
                  disabled={!canEdit || bindMutation.isPending}
                >
                  <SelectTrigger className='w-56 justify-between' aria-label='参数策略'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {profileItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='h-7 text-xs'
                  disabled={!canEdit || createMutation.isPending}
                  onClick={() => openNameDialog('create')}
                >
                  另存为新策略
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='h-7 text-xs'
                  disabled={!canEdit || boundProfileId == null || cloneMutation.isPending}
                  onClick={() => openNameDialog('clone')}
                >
                  克隆当前策略
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='h-7 gap-1 text-xs'
                  disabled={!algorithmType}
                  onClick={() => setHistoryOpen(true)}
                >
                  <History aria-hidden='true' className='size-3.5' />
                  历史
                </Button>
              </div>
              <p className='text-muted-foreground text-xs'>
                解析顺序：本设备覆盖 &gt; 设备绑定策略 &gt; 算法类型级默认。
                「另存为新策略」把当前三层生效值保存成 scope=device 的策略，供其他设备套用。
              </p>
              {profileOptions.isError && (
                <p className='text-destructive text-xs'>参数策略读取失败，稍后重试。</p>
              )}
            </div>
          )}

          {!algorithmType && (
            <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
              请先选择关联算法，再配置该设备的参数。
            </p>
          )}

          {!canEdit && (
            <p className='text-destructive text-xs'>
              当前账号缺少 algorithm:param_manage 权限，本弹窗只读。
            </p>
          )}

          {algorithmType && paramsQuery.isError && (
            <p className='text-destructive text-xs'>设备参数读取失败，请稍后重试。</p>
          )}

          {algorithmType && (
            <div className='border-border/60 overflow-x-auto rounded-lg border'>
              <p className='text-muted-foreground border-b px-3 py-2 text-xs'>
                本表 = 算法类型级默认 → 绑定策略 → 本设备覆盖（三层生效值）
                {boundProfileId != null ? `；当前策略「${boundProfileName}」` : ''}
              </p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='text-xs'>参数代码</TableHead>
                    <TableHead className='text-xs'>名称</TableHead>
                    <TableHead className='text-xs'>类型</TableHead>
                    <TableHead className='text-xs'>方向</TableHead>
                    <TableHead className='text-xs'>来源</TableHead>
                    <TableHead className='text-xs'>默认值</TableHead>
                    <TableHead className='w-24 text-xs'>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paramsQuery.isLoading ? (
                    <TableRow>
                      <TableCell colSpan={7} className='text-muted-foreground text-center text-xs'>
                        正在读取设备参数…
                      </TableCell>
                    </TableRow>
                  ) : effectiveRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className='text-muted-foreground text-center text-xs'>
                        该算法还没有设备参数声明；可直接新增本设备的参数。
                      </TableCell>
                    </TableRow>
                  ) : (
                    effectiveRows.map((row) => {
                      const layer = layerOf(row)
                      return (
                        <TableRow key={`${layer}-${rowKey(row)}`}>
                          <TableCell className='font-mono text-xs'>{row.paramCode}</TableCell>
                          <TableCell className='text-xs'>{row.paramName ?? '—'}</TableCell>
                          <TableCell className='text-xs'>
                            {PARAM_TYPE_LABEL[row.paramType] ?? row.paramType}
                          </TableCell>
                          <TableCell className='text-xs'>
                            {row.direction === 'output' ? '输出' : '输入'}
                          </TableCell>
                          <TableCell>
                            <Badge variant={LAYER_BADGE[layer].variant}>
                              {LAYER_BADGE[layer].label}
                            </Badge>
                          </TableCell>
                          <TableCell className='text-xs'>{row.defaultValue ?? '—'}</TableCell>
                          <TableCell>
                            <div className='flex items-center gap-1'>
                              <Button
                                type='button'
                                variant='ghost'
                                size='sm'
                                className='h-7 text-xs'
                                disabled={!canEdit}
                                onClick={() => openOverride(row)}
                              >
                                {layer === 'device' ? '编辑' : '覆盖'}
                              </Button>
                              {layer === 'device' && (
                                <Button
                                  type='button'
                                  variant='ghost'
                                  size='icon-sm'
                                  className='text-destructive size-6'
                                  aria-label='删除设备覆盖'
                                  disabled={!canEdit}
                                  onClick={() => deleteMutation.mutate(row.id)}
                                >
                                  <Trash2 aria-hidden='true' className='size-3.5' />
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          )}

          <DeviceMappingsSection
            open={open}
            algorithmType={algorithmType}
            deviceId={device.id}
          />
        </div>

        <DialogFooter>
          <Button type='button' variant='outline' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>

      {/* 覆盖 / 新增表单 */}
      <Dialog open={form != null} onOpenChange={(next) => !next && setForm(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>
              {form?.paramId != null ? '编辑设备参数' : '新增设备参数（本设备覆盖）'}
            </DialogTitle>
            <DialogDescription>
              保存后仅对「{device.name}」生效，同名同方向的算法级声明会被覆盖。
            </DialogDescription>
          </DialogHeader>
          {form && (
            <div className='space-y-3'>
              <div className='space-y-1.5'>
                <Label htmlFor='device-param-code'>参数代码 *</Label>
                <Input
                  id='device-param-code'
                  className='font-mono text-xs'
                  value={form.paramCode}
                  onChange={(e) => setForm({ ...form, paramCode: e.target.value })}
                />
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='device-param-name'>参数名称</Label>
                <Input
                  id='device-param-name'
                  className='text-xs'
                  value={form.paramName}
                  onChange={(e) => setForm({ ...form, paramName: e.target.value })}
                />
              </div>
              <div className='grid grid-cols-2 gap-2'>
                <div className='space-y-1.5'>
                  <Label className='text-xs'>参数类型</Label>
                  <Select
                    value={form.paramType}
                    items={[...PARAM_TYPE_OPTIONS]}
                    onValueChange={(value) => setForm({ ...form, paramType: value ?? 'text' })}
                  >
                    <SelectTrigger className='w-full justify-between' aria-label='参数类型'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PARAM_TYPE_OPTIONS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className='space-y-1.5'>
                  <Label className='text-xs'>方向</Label>
                  <Select
                    value={form.direction}
                    items={[...DIRECTION_OPTIONS]}
                    onValueChange={(value) =>
                      setForm({ ...form, direction: value === 'output' ? 'output' : 'input' })
                    }
                  >
                    <SelectTrigger className='w-full justify-between' aria-label='方向'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {DIRECTION_OPTIONS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='device-param-default'>默认值</Label>
                <Input
                  id='device-param-default'
                  className='font-mono text-xs'
                  value={form.defaultValue}
                  onChange={(e) => setForm({ ...form, defaultValue: e.target.value })}
                />
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='device-param-help'>帮助文本</Label>
                <Input
                  id='device-param-help'
                  className='text-xs'
                  value={form.helpText}
                  onChange={(e) => setForm({ ...form, helpText: e.target.value })}
                />
              </div>
              <label className='flex items-center gap-2 text-xs'>
                <Checkbox
                  checked={form.required}
                  onCheckedChange={(checked) => setForm({ ...form, required: Boolean(checked) })}
                />
                必填
              </label>
            </div>
          )}
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setForm(null)}>
              取消
            </Button>
            <Button type='button' disabled={saveMutation.isPending} onClick={submitForm}>
              {saveMutation.isPending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 策略命名（另存 / 克隆） */}
      <Dialog open={nameDialog != null} onOpenChange={(next) => !next && setNameDialog(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>
              {nameDialog === 'clone' ? '克隆当前策略' : '另存为设备策略'}
            </DialogTitle>
            <DialogDescription>
              {nameDialog === 'clone'
                ? '从当前绑定策略复制一份新策略，保存后本设备改绑到新策略。'
                : '把本设备当前三层生效值（算法级默认 → 绑定策略 → 本设备覆盖）保存成 scope=device 的策略，保存后本设备绑定到该策略。'}
            </DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='device-profile-name'>策略名称 *</Label>
              <Input
                id='device-profile-name'
                className='text-xs'
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='device-profile-desc'>描述</Label>
              <Input
                id='device-profile-desc'
                className='text-xs'
                value={draftDescription}
                onChange={(e) => setDraftDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setNameDialog(null)}>
              取消
            </Button>
            <Button type='button' disabled={nameDialogPending} onClick={submitNameDialog}>
              {nameDialogPending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ParamHistoryDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        scope='device'
        scopeId={device.id}
        algorithmType={algorithmType}
        canRestore={canEdit}
        onRestored={invalidateScope}
      />
    </Dialog>
  )
}
