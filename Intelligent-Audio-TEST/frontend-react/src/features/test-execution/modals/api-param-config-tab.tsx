/**
 * API 编辑弹窗「参数配置」页签（Presentation；T4.2）。
 *
 * 语义：API 实例作用域 + 可复用参数策略。
 * - 已绑定策略下拉：数据源 = 本 algorithm_type 下 scope=api 的策略；
 *   切换即 `PUT /algorithm/api-scope/{api_id}/binding`（未绑定 = 解绑）；
 * - 另存为新策略：`POST /algorithm/param-profiles`（以当前行整份创建），成功后绑定新 id；
 * - 克隆当前策略：`POST /algorithm/param-profiles/{id}/clone`，成功后绑定新 id；
 * - 输出字段 / 映射可增删改，保存 = `PUT /algorithm/api-scope/{api_id}/overrides`
 *   （body：algorithm_type / api_params / mappings；只覆盖本 API，不碰策略行）。
 *
 * 降级：
 * - 缺 `algorithm:read`（403）→ 页签「无权查看」；
 * - 新建 API（无 id）→ 提示「保存后可用」，不发请求；
 * - 未选择算法类型 → 下拉与保存禁用并提示。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  paramConfigQueryKeys,
  useApiParamConfig,
  useParamProfileOptions,
} from '@/application/test-execution/useApiParamConfig'
import type { AlgorithmApiMapping, AlgorithmApiParam } from '@/domain/models/apiConfig'
import {
  PARAM_TRANSFORM_TYPE_LABEL,
  PARAM_TRANSFORM_TYPES,
  PARAM_TYPE_LABEL,
  PARAM_TYPES,
  type ParamProfile,
  type ParamProfileInput,
  type ParamProfileMappingDraft,
  type ParamProfileParamDraft,
  type ParamTransformType,
  type ParamType,
} from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  bindApiProfile,
  cloneProfile,
  createProfile,
  saveApiScopeOverrides,
} from '@/infrastructure/api/param-profile-api'
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
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'

/** base-ui Select 不接受空串，未绑定用哨兵值 */
const UNBOUND = '__unbound__'

const PARAM_TYPE_OPTIONS = PARAM_TYPES.map((value) => ({
  value,
  label: PARAM_TYPE_LABEL[value],
}))

const TRANSFORM_TYPE_OPTIONS = PARAM_TRANSFORM_TYPES.map((value) => ({
  value,
  label: PARAM_TRANSFORM_TYPE_LABEL[value],
}))

interface EditableParamRow {
  key: number
  paramCode: string
  paramName: string
  paramType: ParamType
  uiOrder: string
  fieldPath: string
}

interface EditableMappingRow {
  key: number
  sourceParam: string
  targetParam: string
  dimensionId: string
  transformType: ParamTransformType
}

function paramRowOf(param: AlgorithmApiParam, key: number): EditableParamRow {
  return {
    key,
    paramCode: param.paramCode,
    paramName: param.paramName ?? '',
    paramType: PARAM_TYPES.includes(param.paramType as ParamType)
      ? (param.paramType as ParamType)
      : 'text',
    uiOrder: String(param.uiOrder ?? 0),
    fieldPath: param.fieldPath ?? '',
  }
}

function mappingRowOf(mapping: AlgorithmApiMapping, key: number): EditableMappingRow {
  return {
    key,
    sourceParam: mapping.sourceParam,
    targetParam: mapping.targetParam,
    dimensionId: mapping.dimensionId == null ? '' : String(mapping.dimensionId),
    transformType: PARAM_TRANSFORM_TYPES.includes(mapping.transformType as ParamTransformType)
      ? (mapping.transformType as ParamTransformType)
      : 'none',
  }
}

function draftParamsOf(rows: EditableParamRow[]): ParamProfileParamDraft[] {
  return rows
    .filter((row) => row.paramCode.trim())
    .map((row) => ({
      paramCode: row.paramCode.trim(),
      paramName: row.paramName.trim() || null,
      paramType: row.paramType,
      direction: 'output',
      required: false,
      defaultValue: null,
      helpText: null,
      uiOrder: Number(row.uiOrder) || 0,
      hidden: false,
      fieldPath: row.fieldPath.trim() || null,
    }))
}

function draftMappingsOf(rows: EditableMappingRow[]): ParamProfileMappingDraft[] {
  return rows
    .filter((row) => row.sourceParam.trim() && row.targetParam.trim())
    .map((row) => ({
      source: 'api',
      sourceDirection: 'output',
      sourceParam: row.sourceParam.trim(),
      targetParam: row.targetParam.trim(),
      dimensionId: row.dimensionId.trim() === '' ? null : Number(row.dimensionId),
      transformType: row.transformType,
    }))
}

/** 后端 message 优先（ApiError.userMessage 已按服务端文案收敛） */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  return error instanceof Error && error.message ? error.message : '操作失败，请重试'
}

interface ApiParamConfigTabProps {
  /** API 实例 id；新建 API（未保存）为 null */
  apiId: number | null
  /** 关联算法类型（apis.algorithm_type） */
  algorithmType: string
  /** `algorithm:param_manage` */
  canEdit: boolean
}

export function ApiParamConfigTab({
  apiId,
  algorithmType,
  canEdit,
}: ApiParamConfigTabProps) {
  const queryClient = useQueryClient()
  // 新建 API（无 id）/ 未选算法 → 一律不发请求（提示见下方降级块）
  const hasApiScope = apiId != null && Boolean(algorithmType)
  const config = useApiParamConfig(apiId, algorithmType, hasApiScope)
  const profiles = useParamProfileOptions(algorithmType, hasApiScope, apiId)

  const [outputRows, setOutputRows] = useState<EditableParamRow[]>([])
  const [mappingRows, setMappingRows] = useState<EditableMappingRow[]>([])
  const [boundProfileId, setBoundProfileId] = useState<number | null>(null)
  const [nameDialog, setNameDialog] = useState<'create' | 'clone' | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')
  const rowKeyRef = useRef(0)
  const appliedSignatureRef = useRef('')
  /** 上次已同步的服务端绑定值（null 与「未初始化」区分） */
  const lastServerBoundRef = useRef<number | null | undefined>(undefined)

  const editable = canEdit && Boolean(algorithmType) && apiId != null

  // 策略列表回读出本 API 的绑定 → 下拉回显；服务端值变化才同步，避免覆盖本地绑定结果
  const boundProfileIdFromServer = profiles.boundProfileId
  useEffect(() => {
    if (lastServerBoundRef.current === boundProfileIdFromServer) return
    lastServerBoundRef.current = boundProfileIdFromServer
    setBoundProfileId(boundProfileIdFromServer)
  }, [boundProfileIdFromServer])

  // 读侧数据到达 / 保存后重新拉取 → 同步到可编辑行；用户正在编辑时不覆盖
  const signature = useMemo(
    () =>
      JSON.stringify({
        params: config.outputParams.map((row) => [row.paramCode, row.paramType, row.uiOrder]),
        mappings: config.mappings.map((row) => [
          row.sourceParam,
          row.targetParam,
          row.dimensionId,
          row.transformType,
        ]),
      }),
    [config.outputParams, config.mappings]
  )

  useEffect(() => {
    if (config.state !== 'ready') return
    if (signature === appliedSignatureRef.current) return
    appliedSignatureRef.current = signature
    setOutputRows(
      config.outputParams.map((param) => paramRowOf(param, rowKeyRef.current++))
    )
    setMappingRows(
      config.mappings.map((mapping) => mappingRowOf(mapping, rowKeyRef.current++))
    )
  }, [config.state, config.outputParams, config.mappings, signature])

  // 维度名只做输入框下方提示（读侧补全），不随行草稿保存
  const dimensionNameById = useMemo(() => {
    const nameById = new Map<number, string>()
    for (const mapping of config.mappings) {
      if (mapping.dimensionId != null && mapping.dimensionName) {
        nameById.set(mapping.dimensionId, mapping.dimensionName)
      }
    }
    return nameById
  }, [config.mappings])

  const invalidateScope = () => {
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.scopeParams(algorithmType, apiId),
    })
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.scopeMappings(algorithmType, apiId),
    })
  }

  const invalidateProfiles = () => {
    void queryClient.invalidateQueries({
      queryKey: paramConfigQueryKeys.profiles(algorithmType),
    })
  }

  const bindMutation = useMutation({
    mutationFn: (profileId: number | null) => {
      if (apiId == null) throw new Error('API 尚未保存')
      return bindApiProfile(apiId, profileId)
    },
    onSuccess: (result) => {
      setBoundProfileId(result.profileId)
      toast.success(result.profileId == null ? '已解绑策略' : '策略绑定已保存')
      invalidateScope()
      // 失效策略列表：下次重开弹窗按服务端回读，保证绑定后回读一致
      invalidateProfiles()
    },
    onError: (error) => {
      toast.error(errorMessage(error))
    },
  })

  const createMutation = useMutation({
    mutationFn: (input: { name: string; description: string | null }) => {
      const payload: ParamProfileInput = {
        scope: 'api',
        algorithmType,
        name: input.name,
        description: input.description,
        status: 'online',
        params: draftParamsOf(outputRows),
        mappings: draftMappingsOf(mappingRows),
      }
      return createProfile(payload)
    },
    onSuccess: (profile) => {
      toast.success('新策略已创建')
      setNameDialog(null)
      invalidateProfiles()
      bindMutation.mutate(profile.id)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const cloneMutation = useMutation({
    mutationFn: (input: { name: string; description: string | null }) => {
      if (boundProfileId == null) throw new Error('当前未绑定策略')
      return cloneProfile(boundProfileId, input)
    },
    onSuccess: (profile) => {
      toast.success('策略已克隆')
      setNameDialog(null)
      invalidateProfiles()
      bindMutation.mutate(profile.id)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (apiId == null) throw new Error('API 尚未保存')
      return saveApiScopeOverrides(apiId, {
        algorithmType,
        params: draftParamsOf(outputRows),
        mappings: draftMappingsOf(mappingRows),
      })
    },
    onSuccess: (result) => {
      toast.success(
        `参数配置已保存（新增 ${result.paramsCreated + result.mappingsCreated}，` +
          `更新 ${result.paramsUpdated + result.mappingsUpdated}，` +
          `删除 ${result.paramsDeleted + result.mappingsDeleted}）`
      )
      invalidateScope()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateOutputRow = (key: number, patch: Partial<EditableParamRow>) => {
    setOutputRows((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const updateMappingRow = (key: number, patch: Partial<EditableMappingRow>) => {
    setMappingRows((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const openNameDialog = (mode: 'create' | 'clone') => {
    setDraftName('')
    setDraftDescription('')
    setNameDialog(mode)
  }

  const nameDialogPending = createMutation.isPending || cloneMutation.isPending
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

  if (config.state === 'forbidden') {
    return (
      <Empty className='border-border/60 border'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <Badge variant='secondary'>403</Badge>
          </EmptyMedia>
          <EmptyTitle>无权查看参数配置</EmptyTitle>
          <EmptyDescription>
            当前账号缺少 algorithm:read 权限，本页签不可用；不影响其它页签保存。
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const profilesForSelect: Array<{ value: string; label: string }> = [
    { value: UNBOUND, label: '未绑定' },
    ...(profiles.profiles as ParamProfile[]).map((profile) => ({
      value: String(profile.id),
      label: profile.name,
    })),
  ]

  return (
    <div className='space-y-3'>
      {!algorithmType && (
        <div className='bg-muted/40 rounded-lg border p-2.5 text-xs'>
          <p className='text-foreground font-medium'>未选择关联算法</p>
          <p className='text-muted-foreground'>
            请先在「基础」页签选择关联算法：策略下拉与保存按钮将保持禁用。
          </p>
        </div>
      )}

      {algorithmType && apiId == null && (
        <div className='bg-muted/40 rounded-lg border p-2.5 text-xs'>
          <p className='text-foreground font-medium'>新建 API：保存后可用</p>
          <p className='text-muted-foreground'>
            参数配置属于 API 实例作用域，需先保存 API 拿到 id；本页签不会发出任何请求。
          </p>
        </div>
      )}

      {!canEdit && (
        <p className='text-destructive text-xs'>当前账号缺少 algorithm:param_manage 权限，本页签只读。</p>
      )}

      {config.state === 'error' && (
        <p className='text-destructive text-xs'>参数配置读取失败，稍后可重新打开弹窗再试。</p>
      )}

      {/* 策略绑定 */}
      <div className='space-y-1.5'>
        <Label>参数策略</Label>
        <div className='flex flex-wrap items-center gap-2'>
          <Select
            value={boundProfileId == null ? UNBOUND : String(boundProfileId)}
            items={profilesForSelect}
            onValueChange={(value) => {
              if (!value) return
              bindMutation.mutate(value === UNBOUND ? null : Number(value))
            }}
            disabled={!editable || bindMutation.isPending}
          >
            <SelectTrigger className='w-56 justify-between' aria-label='参数策略'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {profilesForSelect.map((item) => (
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
            disabled={!editable || createMutation.isPending}
            onClick={() => openNameDialog('create')}
          >
            另存为新策略
          </Button>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 text-xs'
            disabled={!editable || boundProfileId == null || cloneMutation.isPending}
            onClick={() => openNameDialog('clone')}
          >
            克隆当前策略
          </Button>
        </div>
        <p className='text-muted-foreground text-xs'>
          策略提供默认字段与映射；本页的增删改写入 API 实例覆盖行（覆盖优先于策略）。
          切换下拉即保存绑定，选「未绑定」表示只使用本实例的覆盖行。
        </p>
      </div>

      {/* 输出字段（可编辑） */}
      <div className='space-y-1.5'>
        <div className='flex items-center justify-between'>
          <Label>输出字段</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!editable}
            onClick={() =>
              setOutputRows((rows) => [
                ...rows,
                {
                  key: rowKeyRef.current++,
                  paramCode: '',
                  paramName: '',
                  paramType: 'text',
                  uiOrder: String(rows.length + 1),
                  fieldPath: '',
                },
              ])
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新增输出字段
          </Button>
        </div>
        {config.state === 'loading' ? (
          <div className='text-muted-foreground flex items-center justify-center gap-2 py-6 text-xs'>
            <Spinner className='size-4' />
            正在读取参数配置…
          </div>
        ) : outputRows.length === 0 ? (
          <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
            当前策略与本实例均无输出字段声明；可新增行后保存。
          </p>
        ) : (
          <div className='border-border/60 overflow-x-auto rounded-lg border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-xs'>参数代码</TableHead>
                  <TableHead className='text-xs'>参数名称</TableHead>
                  <TableHead className='text-xs'>类型</TableHead>
                  <TableHead className='text-xs'>方向</TableHead>
                  <TableHead className='text-xs'>排序</TableHead>
                  <TableHead className='text-xs'>响应路径</TableHead>
                  <TableHead className='w-10 text-xs'>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {outputRows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell>
                      <Input
                        value={row.paramCode}
                        disabled={!editable}
                        aria-label='参数代码'
                        className='h-7 w-28 font-mono text-xs'
                        onChange={(e) => updateOutputRow(row.key, { paramCode: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.paramName}
                        disabled={!editable}
                        aria-label='参数名称'
                        className='h-7 w-28 text-xs'
                        onChange={(e) => updateOutputRow(row.key, { paramName: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.paramType}
                        items={PARAM_TYPE_OPTIONS}
                        onValueChange={(value) =>
                          updateOutputRow(row.key, { paramType: value as ParamType })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-28' aria-label='参数类型'>
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
                    </TableCell>
                    <TableCell>
                      <Badge variant='secondary'>输出</Badge>
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.uiOrder}
                        disabled={!editable}
                        type='number'
                        aria-label='排序'
                        className='h-7 w-16 text-xs'
                        onChange={(e) => updateOutputRow(row.key, { uiOrder: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.fieldPath}
                        disabled={!editable}
                        aria-label='响应路径'
                        placeholder='data.items[0].text'
                        className='h-7 w-40 font-mono text-xs'
                        onChange={(e) => updateOutputRow(row.key, { fieldPath: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-6 text-destructive'
                        aria-label='删除输出字段'
                        disabled={!editable}
                        onClick={() =>
                          setOutputRows((rows) => rows.filter((item) => item.key !== row.key))
                        }
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* 映射（可编辑） */}
      <div className='space-y-1.5'>
        <div className='flex items-center justify-between'>
          <Label>参数映射</Label>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1 text-xs'
            disabled={!editable}
            onClick={() =>
              setMappingRows((rows) => [
                ...rows,
                {
                  key: rowKeyRef.current++,
                  sourceParam: '',
                  targetParam: '',
                  dimensionId: '',
                  transformType: 'none',
                },
              ])
            }
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新增映射
          </Button>
        </div>
        {config.state === 'loading' ? null : mappingRows.length === 0 ? (
          <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed p-3 text-center text-xs'>
            当前策略与本实例均无 API 输出映射；可新增行后保存。
          </p>
        ) : (
          <div className='border-border/60 overflow-x-auto rounded-lg border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='text-xs'>来源</TableHead>
                  <TableHead className='text-xs'>源参数</TableHead>
                  <TableHead className='text-xs'>目标维度</TableHead>
                  <TableHead className='text-xs'>目标参数</TableHead>
                  <TableHead className='text-xs'>转换</TableHead>
                  <TableHead className='w-10 text-xs'>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mappingRows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell>
                      <Badge variant='secondary'>api</Badge>
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.sourceParam}
                        disabled={!editable}
                        aria-label='源参数'
                        className='h-7 w-28 font-mono text-xs'
                        onChange={(e) =>
                          updateMappingRow(row.key, { sourceParam: e.target.value })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.dimensionId}
                        disabled={!editable}
                        type='number'
                        aria-label='目标维度'
                        className='h-7 w-20 text-xs'
                        onChange={(e) =>
                          updateMappingRow(row.key, { dimensionId: e.target.value })
                        }
                      />
                      {row.dimensionId.trim() !== '' && dimensionNameById.get(Number(row.dimensionId)) && (
                        <p className='text-muted-foreground mt-0.5 text-[10px]'>
                          {dimensionNameById.get(Number(row.dimensionId))}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.targetParam}
                        disabled={!editable}
                        aria-label='目标参数'
                        className='h-7 w-28 font-mono text-xs'
                        onChange={(e) =>
                          updateMappingRow(row.key, { targetParam: e.target.value })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.transformType}
                        items={TRANSFORM_TYPE_OPTIONS}
                        onValueChange={(value) =>
                          updateMappingRow(row.key, {
                            transformType: value as ParamTransformType,
                          })
                        }
                        disabled={!editable}
                      >
                        <SelectTrigger size='sm' className='w-32' aria-label='转换类型'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TRANSFORM_TYPE_OPTIONS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Button
                        type='button'
                        variant='ghost'
                        size='icon-sm'
                        className='size-6 text-destructive'
                        aria-label='删除映射'
                        disabled={!editable}
                        onClick={() =>
                          setMappingRows((rows) => rows.filter((item) => item.key !== row.key))
                        }
                      >
                        <Trash2 aria-hidden='true' className='size-3.5' />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className='flex items-center justify-end gap-2'>
        <Button
          type='button'
          size='sm'
          disabled={!editable || saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? '保存中…' : '保存参数配置'}
        </Button>
      </div>

      {/* 另存 / 克隆：名称 + 描述 */}
      <Dialog open={nameDialog != null} onOpenChange={(open) => !open && setNameDialog(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>{nameDialog === 'clone' ? '克隆当前策略' : '另存为新策略'}</DialogTitle>
            <DialogDescription>
              {nameDialog === 'clone'
                ? '复制当前绑定策略的字段与映射，生成新策略并绑定到本 API。'
                : '以本页当前字段与映射创建新策略，并绑定到本 API。'}
            </DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='param-profile-name'>策略名称 *</Label>
              <Input
                id='param-profile-name'
                value={draftName}
                maxLength={100}
                placeholder='请输入策略名称'
                onChange={(e) => setDraftName(e.target.value)}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='param-profile-description'>描述</Label>
              <Textarea
                id='param-profile-description'
                rows={2}
                value={draftDescription}
                placeholder='可选：说明字段来源 / 适用场景'
                onChange={(e) => setDraftDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setNameDialog(null)}>
              取消
            </Button>
            <Button type='button' disabled={nameDialogPending} onClick={submitNameDialog}>
              {nameDialogPending ? '保存中…' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
