/**
 * 设备映射区（设备「参数配置」弹窗内嵌；设备级映射编辑）。
 *
 * 语义（与设备参数同构的设备级覆盖）：
 * - 读：`GET /algorithm/mappings?...&source_type=evaluation&device_id=Y`
 *   返回算法级打底 + 本设备覆盖行；本区按 `device_id` 合并（同键覆盖）；
 * - 写：新增 / 编辑 / 删除都落**设备级行**（带 device_id），算法级行只读；
 * - 删除设备级行即回落到算法级映射。
 *
 * 两类映射：用例参数 → 设备输入（source=case，direction=input）、
 * 设备输出 → 评估参数（source=device，需选评估维度）。
 *
 * 降级：写操作需 `algorithm:definition_manage`，缺失时只读。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import type { ParamMapping } from '@/domain/models/algorithmConfig'
import { fetchEvaluationDimensions } from '@/infrastructure/api/evaluation-api'
import {
  createDeviceScopeMapping,
  deleteDeviceScopeMapping,
  fetchDeviceScopeMappings,
  updateDeviceScopeMapping,
  type DeviceMappingSource,
  type DeviceMappingWriteInput,
} from '@/infrastructure/api/device-param-api'
import { Badge } from '@/components/ui/badge'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const SOURCE_OPTIONS: Array<{ value: DeviceMappingSource; label: string }> = [
  { value: 'case', label: '用例参数 → 设备输入' },
  { value: 'device', label: '设备输出 → 评估参数' },
]

const SOURCE_LABEL: Record<string, string> = Object.fromEntries(
  SOURCE_OPTIONS.map((item) => [item.value, item.label])
)

const TRANSFORM_OPTIONS = [
  { value: 'none', label: '不转换' },
  { value: 'uppercase', label: '转大写' },
  { value: 'lowercase', label: '转小写' },
  { value: 'json_parse', label: 'JSON 解析' },
  { value: 'rttm_to_obj', label: 'RTTM 解析' },
  { value: 'stm_to_obj', label: 'STM 解析' },
] as const

const TRANSFORM_LABEL: Record<string, string> = Object.fromEntries(
  TRANSFORM_OPTIONS.map((item) => [item.value, item.label])
)

interface MappingFormState {
  source: DeviceMappingSource
  sourceParam: string
  dimensionId: number | null
  targetParam: string
  transformType: string
  /** 编辑设备级行时的 id；null = 新建 */
  mappingId: number | null
}

const EMPTY_FORM: MappingFormState = {
  source: 'device',
  sourceParam: '',
  dimensionId: null,
  targetParam: '',
  transformType: 'none',
  mappingId: null,
}

/** 合并键：来源 + 源参数 + 目标维度（与后端唯一键同口径） */
function rowKey(row: ParamMapping): string {
  return `${row.source}|${row.sourceParam}|${row.dimensionId ?? ''}`
}

/** 该行是否属于本设备 */
function isScoped(row: ParamMapping, deviceId: number): boolean {
  return row.deviceId === deviceId
}

interface DeviceMappingsSectionProps {
  open: boolean
  algorithmType: string
  deviceId: number
}

export function DeviceMappingsSection({
  open,
  algorithmType,
  deviceId,
}: DeviceMappingsSectionProps) {
  const queryClient = useQueryClient()
  const { hasPermission } = usePermissions()
  const canEdit = hasPermission('algorithm:definition_manage')
  const [form, setForm] = useState<MappingFormState | null>(null)

  const mappingsQuery = useQuery({
    queryKey: ['devices', 'device-mappings', algorithmType, deviceId],
    queryFn: () => fetchDeviceScopeMappings(algorithmType, deviceId),
    enabled: open && Boolean(algorithmType) && deviceId > 0,
    staleTime: 0,
    retry: false,
  })

  const dimensionsQuery = useQuery({
    queryKey: ['evaluation', 'dimensions'],
    queryFn: fetchEvaluationDimensions,
    enabled: open,
    staleTime: 60_000,
    retry: false,
  })

  const rows = useMemo(() => mappingsQuery.data ?? [], [mappingsQuery.data])

  /** 生效行：算法级打底，本设备覆盖行按 rowKey 覆盖 */
  const effectiveRows = useMemo(() => {
    const map = new Map<string, ParamMapping & { scoped: boolean }>()
    for (const row of rows) {
      if (!isScoped(row, deviceId)) map.set(rowKey(row), { ...row, scoped: false })
    }
    for (const row of rows) {
      if (isScoped(row, deviceId)) map.set(rowKey(row), { ...row, scoped: true })
    }
    return [...map.values()].sort(
      (a, b) =>
        (a.source ?? '').localeCompare(b.source ?? '') ||
        a.sourceParam.localeCompare(b.sourceParam)
    )
  }, [rows, deviceId])

  const dimensions = useMemo(() => dimensionsQuery.data ?? [], [dimensionsQuery.data])

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['devices', 'device-mappings', algorithmType, deviceId],
    })
  }

  const saveMutation = useMutation({
    mutationFn: async (state: MappingFormState) => {
      const payload: DeviceMappingWriteInput = {
        algorithmType,
        deviceId,
        source: state.source,
        sourceParam: state.sourceParam.trim(),
        sourceDirection: state.source === 'case' ? 'input' : 'output',
        dimensionId: state.source === 'device' ? state.dimensionId : null,
        targetParam: state.targetParam.trim(),
        transformType: state.transformType,
      }
      if (state.mappingId != null) {
        await updateDeviceScopeMapping(state.mappingId, payload)
      } else {
        await createDeviceScopeMapping(payload)
      }
    },
    onSuccess: () => {
      toast.success('设备映射已保存')
      setForm(null)
      invalidate()
    },
    onError: (error) =>
      toast.error(`保存失败：${error instanceof Error ? error.message : String(error)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (mappingId: number) => deleteDeviceScopeMapping(mappingId),
    onSuccess: () => {
      toast.success('设备映射已删除，回落到算法级映射')
      invalidate()
    },
    onError: (error) =>
      toast.error(`删除失败：${error instanceof Error ? error.message : String(error)}`),
  })

  const openForm = (row: (ParamMapping & { scoped: boolean }) | null) => {
    if (!row) {
      setForm({ ...EMPTY_FORM })
      return
    }
    setForm({
      source: row.source === 'case' ? 'case' : 'device',
      sourceParam: row.sourceParam,
      dimensionId: row.dimensionId,
      targetParam: row.targetParam,
      transformType: row.transformType,
      mappingId: row.scoped ? row.id : null,
    })
  }

  const submitForm = () => {
    if (!form) return
    if (!form.sourceParam.trim()) {
      toast.error('源参数代码必填')
      return
    }
    if (form.source === 'device' && form.dimensionId == null) {
      toast.error('设备输出映射必须选择评估维度')
      return
    }
    if (!form.targetParam.trim()) {
      toast.error('目标参数代码必填')
      return
    }
    saveMutation.mutate(form)
  }

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='min-w-0'>
          <p className='text-sm font-medium'>设备映射</p>
          <p className='text-muted-foreground text-xs'>
            设备级映射覆盖同键的算法级映射；删除覆盖即回落到算法级。
          </p>
        </div>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='ml-auto h-7 gap-1 text-xs'
          disabled={!canEdit || !algorithmType}
          onClick={() => openForm(null)}
        >
          <Plus aria-hidden='true' className='size-3.5' />
          新增设备映射
        </Button>
      </div>

      {!canEdit && (
        <p className='text-destructive text-xs'>
          当前账号缺少 algorithm:definition_manage 权限，设备映射只读。
        </p>
      )}

      {mappingsQuery.isError && (
        <p className='text-destructive text-xs'>设备映射读取失败，请稍后重试。</p>
      )}

      <div className='border-border/60 overflow-x-auto rounded-lg border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='text-xs'>映射类型</TableHead>
              <TableHead className='text-xs'>源参数</TableHead>
              <TableHead className='text-xs'>目标</TableHead>
              <TableHead className='text-xs'>转换</TableHead>
              <TableHead className='text-xs'>来源</TableHead>
              <TableHead className='w-24 text-xs'>操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mappingsQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className='text-muted-foreground text-center text-xs'>
                  正在读取设备映射…
                </TableCell>
              </TableRow>
            ) : effectiveRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className='text-muted-foreground text-center text-xs'>
                  该算法还没有设备相关映射；可直接新增本设备的映射。
                </TableCell>
              </TableRow>
            ) : (
              effectiveRows.map((row) => (
                <TableRow key={`${row.deviceId ?? 'algo'}-${rowKey(row)}`}>
                  <TableCell className='text-xs'>
                    {SOURCE_LABEL[row.source ?? ''] ?? row.source ?? '—'}
                  </TableCell>
                  <TableCell className='font-mono text-xs'>{row.sourceParam}</TableCell>
                  <TableCell className='text-xs'>
                    {row.dimensionId != null
                      ? `${row.dimensionName ?? `维度#${row.dimensionId}`} / ${row.targetParam}`
                      : row.targetParam || '—'}
                  </TableCell>
                  <TableCell className='text-xs'>
                    {TRANSFORM_LABEL[row.transformType] ?? row.transformType}
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.scoped ? 'default' : 'secondary'}>
                      {row.scoped ? '本设备' : '算法级'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className='flex items-center gap-1'>
                      <Button
                        type='button'
                        variant='ghost'
                        size='sm'
                        className='h-7 text-xs'
                        disabled={!canEdit}
                        onClick={() => openForm(row)}
                      >
                        {row.scoped ? '编辑' : '覆盖'}
                      </Button>
                      {row.scoped && (
                        <Button
                          type='button'
                          variant='ghost'
                          size='icon-sm'
                          className='text-destructive size-6'
                          aria-label='删除设备映射'
                          disabled={!canEdit}
                          onClick={() => deleteMutation.mutate(row.id)}
                        >
                          <Trash2 aria-hidden='true' className='size-3.5' />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* 覆盖 / 新增表单 */}
      <Dialog open={form != null} onOpenChange={(next) => !next && setForm(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>
              {form?.mappingId != null ? '编辑设备映射' : '新增设备映射（本设备覆盖）'}
            </DialogTitle>
            <DialogDescription>
              保存后仅对本设备生效，同键的算法级映射会被覆盖。
            </DialogDescription>
          </DialogHeader>
          {form && (
            <div className='space-y-3'>
              <div className='space-y-1.5'>
                <Label className='text-xs'>映射类型</Label>
                <Select
                  value={form.source}
                  items={[...SOURCE_OPTIONS]}
                  onValueChange={(value) =>
                    setForm({
                      ...form,
                      source: value === 'case' ? 'case' : 'device',
                      dimensionId: value === 'case' ? null : form.dimensionId,
                    })
                  }
                >
                  <SelectTrigger className='w-full justify-between' aria-label='映射类型'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='device-mapping-source'>源参数代码 *</Label>
                <Input
                  id='device-mapping-source'
                  className='font-mono text-xs'
                  value={form.sourceParam}
                  onChange={(e) => setForm({ ...form, sourceParam: e.target.value })}
                />
              </div>
              {form.source === 'device' && (
                <div className='space-y-1.5'>
                  <Label className='text-xs'>目标评估维度 *</Label>
                  <Select
                    value={form.dimensionId != null ? String(form.dimensionId) : ''}
                    items={dimensions.map((item) => ({
                      value: String(item.id),
                      label: item.name,
                    }))}
                    onValueChange={(value) =>
                      setForm({ ...form, dimensionId: value ? Number(value) : null })
                    }
                  >
                    <SelectTrigger className='w-full justify-between' aria-label='目标评估维度'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {dimensions.map((item) => (
                        <SelectItem key={String(item.id)} value={String(item.id)}>
                          {item.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className='space-y-1.5'>
                <Label htmlFor='device-mapping-target'>目标参数代码 *</Label>
                <Input
                  id='device-mapping-target'
                  className='font-mono text-xs'
                  value={form.targetParam}
                  onChange={(e) => setForm({ ...form, targetParam: e.target.value })}
                />
              </div>
              <div className='space-y-1.5'>
                <Label className='text-xs'>转换类型</Label>
                <Select
                  value={form.transformType}
                  items={[...TRANSFORM_OPTIONS]}
                  onValueChange={(value) => setForm({ ...form, transformType: value ?? 'none' })}
                >
                  <SelectTrigger className='w-full justify-between' aria-label='转换类型'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRANSFORM_OPTIONS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
    </div>
  )
}
