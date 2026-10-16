/**
 * 步骤三：选择资源与执行参数（interfaces/features/test-execution/components；
 * 10_测试执行.md §3.6）。工具行 + 分叉（E2E 设备网格 / API 表格）+ 执行参数区
 * （测试配置/并发/网络/报告四类，照 playground-parameter-panel 参数卡形态）。
 * readOnly（§3.1.1）：设备/API 列表只读可见；扫描/新增/连接测试/编辑/删除隐藏；参数只读展示。
 * 多友商口径（负责人 2026-10-16 核心业务口径）：多被测主体同集同指标同时实测=本步
 * API 多选（api-table 行 ☑ + 表头全选）+ 并发自动合计（「并发任务数」由所选 API 并发上限求和）。
 */
import { Info, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useResourceSelection } from '@/application/test-execution/useResourceSelection'
import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { DeviceCard } from '@/features/test-execution/components/device-card'
import { ApiTable } from '@/features/test-execution/components/api-table'
import { ParamCard } from '@/features/test-execution/components/param-card'
import { SelectionSummary } from '@/features/test-execution/components/selection-summary'
import { NETWORK_OPTIONS, REPORT_INCLUDE_OPTIONS, REPORT_TEMPLATE_OPTIONS, RESOURCE_SYSTEM_OPTIONS, MOCK_RESOURCE_LABS } from '@/features/test-execution/constants'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { Device } from '@/domain/models/device'

interface StepResourcesProps {
  type: 'e2e' | 'api'
  resourceNoun: string
  voiceLlmAlert: string
  readOnly: boolean
  onOpenApiEdit: (api?: ApiConfig) => void
  onOpenApiHealth: (api: ApiConfig) => void
  onScanDevices: () => void
  onAddDevice: () => void
}

export function StepResources({
  type,
  resourceNoun,
  voiceLlmAlert,
  readOnly,
  onOpenApiEdit,
  onOpenApiHealth,
  onScanDevices,
  onAddDevice,
}: StepResourcesProps) {
  const { hasPermission } = usePermissions()
  const { current: currentAlgorithm, algorithmType } = useAlgorithmChannel()
  const resources = useResourceSelection(type, algorithmType)
  const apisCrud = useApisCrud()
  const params = useExecutionStore((s) => s.params)
  const setParams = useExecutionStore((s) => s.setParams)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'online' | 'offline'>('all')
  // INT-486 口径 2026-10-16：实验室/系统类型筛选（INT-487 设备-实验室绑定待接线）
  const [labFilter, setLabFilter] = useState('all')
  const [systemFilter, setSystemFilter] = useState<'all' | 'android' | 'harmony' | 'api'>('all')
  const [testingIds, setTestingIds] = useState<Set<number>>(new Set())

  const isApi = type === 'api'
  const canDeviceControl = hasPermission('device:control')
  const canDeviceCreate = hasPermission('device:create')
  const canApiCreate = hasPermission('api_config:create')
  const canApiTest = hasPermission('api_config:test')
  const canApiEdit = hasPermission('api_config:update')
  const canApiDelete = hasPermission('api_config:delete')

  /** 实验室成员（INT-487 绑定 mock；'all' 不筛） */
  const labDeviceIds = useMemo(() => {
    if (labFilter === 'all') return null
    return MOCK_RESOURCE_LABS.find((l) => l.id === labFilter)?.deviceIds ?? []
  }, [labFilter])
  const labApiIds = useMemo(() => {
    if (labFilter === 'all') return null
    return MOCK_RESOURCE_LABS.find((l) => l.id === labFilter)?.apiIds ?? []
  }, [labFilter])

  /** 关键词/状态/实验室/系统类型筛选（视觉稿演示；数据 mock 全量返回，前端过滤口径） */
  const visibleDevices = useMemo(() => {
    const q = keyword.trim().toLowerCase()
    return resources.devices.filter((d) => {
      if (statusFilter !== 'all' && (d.status ?? 'offline') !== statusFilter) return false
      if (labDeviceIds !== null && !labDeviceIds.includes(d.id)) return false
      if (systemFilter === 'android' || systemFilter === 'harmony') {
        if ((d.system ?? '').toLowerCase() !== systemFilter) return false
      } else if (systemFilter === 'api') {
        if (d.type !== 'http_api' && d.type !== 'websocket_api') return false
      }
      if (q) {
        const haystack = `${d.name} ${d.model ?? ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [resources.devices, keyword, statusFilter, labDeviceIds, systemFilter])

  const visibleApis = useMemo(() => {
    const q = keyword.trim().toLowerCase()
    return resources.apis.filter((a) => {
      if (statusFilter !== 'all' && (a.status ?? 'offline') !== statusFilter) return false
      if (labApiIds !== null && !labApiIds.includes(a.id)) return false
      // API 均为网关：系统类型仅「全部/API 网关」有效，物理系统筛选对 API 无命中
      if (systemFilter === 'android' || systemFilter === 'harmony') return false
      if (q) {
        const haystack = `${a.name} ${a.apiUrl ?? ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [resources.apis, keyword, statusFilter, labApiIds, systemFilter])

  /** API 并发自动求和（§3.6.3 并发数参数卡；现 apiTest.steps.ts:154-158 口径） */
  const apiConcurrencySum = useMemo(
    () =>
      resources.apis
        .filter((a) => resources.apiIds.includes(a.id))
        .reduce((sum, a) => sum + a.maxConcurrent, 0),
    [resources.apis, resources.apiIds]
  )

  const isVoiceLlm = algorithmType === 'tts_eval'

  const handleTestConnection = async (device: Device) => {
    setTestingIds((prev) => new Set(prev).add(device.id))
    // mock 连接测试（§5.4 设备归 INT-361；本页仅留入口动画）
    window.setTimeout(() => {
      setTestingIds((prev) => {
        const next = new Set(prev)
        next.delete(device.id)
        return next
      })
    }, 900)
  }

  const handleApiTest = async (api: ApiConfig) => {
    setTestingIds((prev) => new Set(prev).add(api.id))
    try {
      await onOpenApiHealth(api)
    } finally {
      setTestingIds((prev) => {
        const next = new Set(prev)
        next.delete(api.id)
        return next
      })
    }
  }

  const selectedDevices = resources.devices.filter((d) => resources.deviceIds.includes(d.id))
  const selectedApis = resources.apis.filter((a) => resources.apiIds.includes(a.id))

  return (
    <div className='flex flex-col gap-4'>
      {/* 工具行 */}
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant='secondary' className='gap-1 rounded-md px-2 py-1 text-xs'>
          <span className='text-muted-foreground'>算法：</span>
          <span className='font-medium'>{currentAlgorithm?.name ?? '未选择'}</span>
        </Badge>

        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
          />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder={isApi ? '搜索 API 名称或端点' : '搜索设备名称或型号'}
            className='h-8 w-[200px] ps-7 sm:w-[240px]'
          />
        </div>

        {/* 状态 facet */}
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as 'all' | 'online' | 'offline')}
        >
          <SelectTrigger className='h-8 w-28 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部状态</SelectItem>
            <SelectItem value='online'>在线</SelectItem>
            <SelectItem value='offline'>离线</SelectItem>
          </SelectContent>
        </Select>

        {/* 实验室 facet（INT-486 口径；INT-487 设备-实验室绑定待接线） */}
        <Select value={labFilter} onValueChange={(v) => setLabFilter(v ?? 'all')}>
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>全部实验室</SelectItem>
            {MOCK_RESOURCE_LABS.map((lab) => (
              <SelectItem key={lab.id} value={lab.id}>
                {lab.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 系统类型 facet（E2E 设备按 system/type；API 均为网关） */}
        {!isApi && (
          <Select
            value={systemFilter}
            onValueChange={(v) => setSystemFilter(v as 'all' | 'android' | 'harmony' | 'api')}
          >
            <SelectTrigger className='h-8 w-32 text-xs'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RESOURCE_SYSTEM_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {/* 右端操作（权限显隐；readOnly 隐藏） */}
        {!readOnly && (
          <div className='ml-auto flex items-center gap-2'>
            {!isApi && canDeviceControl && (
              <Button variant='outline' size='sm' onClick={onScanDevices}>
                扫描设备
              </Button>
            )}
            {!isApi && canDeviceCreate && (
              <Button variant='outline' size='sm' onClick={onAddDevice}>
                新增设备
              </Button>
            )}
            {isApi && canApiCreate && (
              <Button size='sm' onClick={() => onOpenApiEdit()}>
                新增 API
              </Button>
            )}
          </div>
        )}
      </div>

      {/* 过滤空态兜底（§3.3） */}
      {(isApi ? resources.apis.length === 0 : resources.devices.length === 0) &&
        !resources.isLoading && (
          <Empty className='min-h-[200px] border-dashed'>
            <EmptyHeader>
              <EmptyMedia variant='icon' />
              <EmptyTitle>
                当前算法（{currentAlgorithm?.name ?? '未选择'}）下没有可用{resourceNoun}
              </EmptyTitle>
              <EmptyDescription>
                {resources.isTemporary
                  ? `已临时显示全部，全局算法仍为 ${currentAlgorithm?.name ?? '未选择'}`
                  : '更换算法或查看全部设备'}
              </EmptyDescription>
            </EmptyHeader>
            {!readOnly && (
              <EmptyContent>
                <Button size='sm' variant='outline' onClick={() => resources.setTemporaryShowAll(true)}>
                  查看全部
                </Button>
              </EmptyContent>
            )}
          </Empty>
        )}

      {/* 临时解除算法过滤 Alert */}
      {resources.isTemporary && (
        <Alert className='py-2'>
          <Info aria-hidden='true' className='size-4' />
          <AlertDescription className='text-xs'>
            已临时显示全部，全局算法仍为 {currentAlgorithm?.name ?? '未选择'}
          </AlertDescription>
        </Alert>
      )}

      {/* voice_llm Alert（步骤三顶部） */}
      {!isApi && isVoiceLlm && (
        <Alert className='py-2'>
          <Info aria-hidden='true' className='size-4' />
          <AlertDescription className='text-xs'>{voiceLlmAlert}</AlertDescription>
        </Alert>
      )}

      {/* 资源区（E2E 设备网格 / API 表格） */}
      {resources.isLoading ? (
        <div aria-busy='true' className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className='h-44 w-full rounded-xl' />
          ))}
        </div>
      ) : isApi ? (
        <ApiTable
          apis={visibleApis}
          selectedIds={resources.apiIds}
          readOnly={readOnly}
          canTest={canApiTest}
          canEdit={canApiEdit}
          canDelete={canApiDelete}
          testingIds={testingIds}
          onToggle={resources.toggleApi}
          onToggleAll={() => {
            const onlineIds = resources.apis.filter((a) => a.status === 'online').map((a) => a.id)
            const allSelected = onlineIds.every((id) => resources.apiIds.includes(id))
            resources.selectAllApis(allSelected ? [] : onlineIds)
          }}
          onTestConnection={handleApiTest}
          onEdit={onOpenApiEdit}
          onDelete={(api) => void apisCrud.remove(api)}
        />
      ) : (
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
          {visibleDevices.map((device) => (
            <DeviceCard
              key={device.id}
              device={device}
              selected={resources.deviceIds.includes(device.id)}
              readOnly={readOnly}
              canControl={canDeviceControl}
              testing={testingIds.has(device.id)}
              onToggle={resources.toggleDevice}
              onTestConnection={() => void handleTestConnection(device)}
            />
          ))}
        </div>
      )}

      {/* 已选资源汇总行 */}
      {!readOnly && (
        <SelectionSummary
          mode='resource'
          count={isApi ? resources.apiIds.length : resources.deviceIds.length}
          unitText={isApi ? '个 API' : '台设备'}
          concurrencyText={isApi ? `并发上限 ${apiConcurrencySum}` : undefined}
          items={
            isApi
              ? selectedApis.map((a) => ({ id: a.id, name: a.name, status: a.status }))
              : selectedDevices.map((d) => ({ id: d.id, name: d.name, status: d.status }))
          }
          onClear={() =>
            isApi ? resources.selectAllApis([]) : resources.selectAllDevices([])
          }
          onRemoveItem={(id) => (isApi ? resources.removeApi(id) : resources.removeDevice(id))}
        />
      )}

      {/* 执行参数区（§3.6.3） */}
      <div className='border-border/70 bg-background/95 ring-foreground/5 rounded-xl border p-4 ring-1'>
        <h3 className='mb-3 text-sm font-semibold'>执行参数</h3>
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
          {/* 测试配置 */}
          <ParamCard
            label='测试轮数'
            value={`${params.rounds}`}
            description='每个用例执行的轮次数'
            readOnly={readOnly || isApi}
          >
            <Input
              type='number'
              min={1}
              max={20}
              value={params.rounds}
              onChange={(e) => setParams({ rounds: Number(e.target.value) || 1 })}
              className='h-8'
            />
          </ParamCard>
          <ParamCard
            label='超时时间'
            value={`${params.timeout}s`}
            description='单轮次执行超时上限，超时按该轮失败处理'
            readOnly={readOnly || isApi}
          >
            <Input
              type='number'
              min={1}
              value={params.timeout}
              onChange={(e) => setParams({ timeout: Number(e.target.value) || 60 })}
              className='h-8'
            />
          </ParamCard>
          <ParamCard
            label='重试次数'
            value={`${params.retries}`}
            description='执行失败自动重试次数'
            readOnly={readOnly || isApi}
          >
            <Input
              type='number'
              min={0}
              max={5}
              value={params.retries}
              onChange={(e) => setParams({ retries: Number(e.target.value) || 0 })}
              className='h-8'
            />
          </ParamCard>

          {/* 并发数参数卡（E2E 可改 / API 只读自动求和） */}
          <ParamCard
            label='并发任务数'
            value={isApi ? `${apiConcurrencySum}` : `${params.concurrency}`}
            description={isApi ? '由所选 API 的并发上限自动合计' : '同时执行的用例数上限'}
            readOnly={readOnly || isApi}
          >
            {!isApi && (
              <Input
                type='number'
                min={1}
                max={32}
                value={params.concurrency}
                onChange={(e) => setParams({ concurrency: Number(e.target.value) || 4 })}
                className='h-8'
              />
            )}
          </ParamCard>
        </div>

        {/* voice_llm 建议并发（E2E） */}
        {!isApi && isVoiceLlm && (
          <p className='text-warning mt-3 text-xs'>
            voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。
          </p>
        )}

        {/* 网络配置（E2E，device:control 才可设；tester 无权限项隐藏只读展示） */}
        {!isApi && (
          <div className='mt-4'>
            <h4 className='mb-2 text-xs font-medium'>网络配置</h4>
            {canDeviceControl && !readOnly ? (
              <Select
                value={params.network}
                onValueChange={(v) => setParams({ network: v ?? '默认' })}
              >
                <SelectTrigger className='h-8 w-40 text-xs'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {NETWORK_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p className='text-muted-foreground text-xs'>当前：{params.network}（需 device:control 权限设置）</p>
            )}
          </div>
        )}

        {/* 报告配置 */}
        <div className='mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
          <ParamCard
            label='报告模板'
            value={params.reportTemplate}
            description='生成报告使用的模板'
            readOnly={readOnly}
          >
            <Select
              value={params.reportTemplate}
              onValueChange={(v) => setParams({ reportTemplate: v ?? '标准模板' })}
            >
              <SelectTrigger className='h-8 w-full text-xs'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REPORT_TEMPLATE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </ParamCard>

          <ParamCard
            label='包含内容'
            value={`${REPORT_INCLUDE_OPTIONS.filter((o) => params[o.value as keyof typeof params]).length} 项`}
            description='图表 / 详细日志 / 参考参数'
            readOnly={readOnly}
          >
            <div className='flex flex-col gap-1'>
              {REPORT_INCLUDE_OPTIONS.map((option) => {
                const key = option.value as 'includeCharts' | 'includeDetailedLogs' | 'includeReferenceParams'
                return (
                  <label key={option.value} className='flex items-center gap-1.5 text-xs'>
                    <input
                      type='checkbox'
                      className='size-3.5 accent-[var(--primary)]'
                      checked={params[key]}
                      onChange={(e) => setParams({ [key]: e.target.checked })}
                    />
                    {option.label}
                  </label>
                )
              })}
            </div>
          </ParamCard>

          <ParamCard
            label='导出格式'
            value={params.exportFormats.join('/').toUpperCase()}
            description='报告导出格式预选（CSV/Excel/PDF/HTML）'
            readOnly={readOnly}
          >
            <div className='flex flex-wrap gap-1'>
              {['csv', 'excel', 'pdf', 'html'].map((format) => (
                <button
                  key={format}
                  type='button'
                  className={cn(
                    'rounded-md border px-1.5 py-0.5 text-[11px] uppercase transition-colors',
                    params.exportFormats.includes(format)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground'
                  )}
                  onClick={() =>
                    setParams({
                      exportFormats: params.exportFormats.includes(format)
                        ? params.exportFormats.filter((f) => f !== format)
                        : [...params.exportFormats, format],
                    })
                  }
                >
                  {format}
                </button>
              ))}
            </div>
          </ParamCard>
        </div>
      </div>

      {/* 分页 */}
      <div className='flex items-center justify-between text-xs'>
        <span className='text-muted-foreground'>
          共 {isApi ? resources.apis.length : resources.devices.length} 个{resourceNoun}
        </span>
        <span className='text-muted-foreground'>每页 10 条 · 第 1 / 1 页</span>
      </div>
    </div>
  )
}
