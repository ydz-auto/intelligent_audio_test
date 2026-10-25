/**
 * 步骤二：选择设备/API 与执行参数（interfaces/features/test-execution/components；
 * 10_测试执行.md §3.6；INT-486 2026-10-16 追加口径：开始测试不再分 E2E/API——
 * 本步同屏同选设备 + API（混合执行），筛选按设备/API 维度组合）。
 * 工具行（搜索/状态/实验室/系统类型 + API 厂商/协议筛选）+ 设备网格 + 被测 API 卡片网格
 * （INT-1061 2026-10-20：API 与设备同一套卡片形态，混选同屏一眼同形；纯 API 表格保留 api-table 备用）
 * + 执行参数区（测试配置/并发/网络，照 playground-parameter-panel 参数卡形态；
 *   INT-1060 返工 / INT-1119 2026-10-21：执行模式改为**逐卡配置**——设备卡/API 卡 SegmentedControl
 *   「并行｜串行」，底部 execution-diagram 实时示意，执行参数区不再含全局执行模式开关）。
 * 报告参数不在第二步配置（负责人 2026-10-16 口径确认：报告内容/导出在报告阶段处理）。
 * readOnly（§3.1.1）：设备/API 列表只读可见；扫描/新增/连接测试/编辑/删除隐藏；参数只读展示；
 * 逐卡模式只读 Badge + 底部示意图只读渲染（§3.6.4）。
 * 多友商口径（负责人 2026-10-16 核心业务口径）：多被测主体同集同指标同时实测=本步
 * 设备 + API 多选 + 并发自动合计（「并发任务数」由所选 API 并发上限求和）。
 */
import { Info, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useResourceSelection } from '@/application/test-execution/useResourceSelection'
import { useApisCrud } from '@/application/test-execution/useApisCrud'
import { useTargetModes } from '@/application/test-execution/useTargetModes'
import { useExecutionStore } from '@/infrastructure/stores/execution-store'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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

import { DeviceCard } from '@/features/test-execution/components/device-card'
import { ApiCard } from '@/features/test-execution/components/api-card'
import { ParamCard } from '@/features/test-execution/components/param-card'
import { SelectionSummary } from '@/features/test-execution/components/selection-summary'
import { ExecutionDiagram } from '@/features/test-execution/components/execution-diagram'
import {
  MOCK_RESOURCE_LABS,
  NETWORK_OPTIONS,
  RESOURCE_PROTOCOL_OPTIONS,
  RESOURCE_STATUS_OPTIONS,
  RESOURCE_STREAMING_OPTIONS,
  RESOURCE_SYSTEM_OPTIONS,
  RESOURCE_VENDOR_OPTIONS,
} from '@/features/test-execution/constants'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { Device } from '@/domain/models/device'

/**
 * 实验室筛选选项（INT-1633：作 Select items，关闭态才会把 'all'/lab id 映射成中文名）
 */
const LAB_FILTER_OPTIONS = [
  { value: 'all', label: '全部实验室' },
  ...MOCK_RESOURCE_LABS.map((lab) => ({ value: lab.id, label: lab.name })),
]

interface StepResourcesProps {
  voiceLlmAlert: string
  readOnly: boolean
  onOpenApiEdit: (api?: ApiConfig) => void
  onOpenApiHealth: (api: ApiConfig) => void
  onScanDevices: () => void
  onAddDevice: () => void
}

export function StepResources({
  voiceLlmAlert,
  readOnly,
  onOpenApiEdit,
  onOpenApiHealth,
  onScanDevices,
  onAddDevice,
}: StepResourcesProps) {
  const { hasPermission } = usePermissions()
  const { current: currentAlgorithm, algorithmType } = useAlgorithmChannel()
  const resources = useResourceSelection(algorithmType)
  const targetModes = useTargetModes()
  const apisCrud = useApisCrud()
  const params = useExecutionStore((s) => s.params)
  const setParams = useExecutionStore((s) => s.setParams)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'online' | 'offline'>('all')
  // INT-486 口径 2026-10-16：实验室/系统类型筛选（INT-487 设备-实验室绑定待接线）
  const [labFilter, setLabFilter] = useState('all')
  const [systemFilter, setSystemFilter] = useState<'all' | 'android' | 'harmony' | 'api'>('all')
  // INT-486 口径 2026-10-16：API 厂商/协议筛选维度；INT-1800：协议 + 流式性两维独立
  const [vendorFilter, setVendorFilter] = useState('all')
  const [protocolFilter, setProtocolFilter] = useState('all')
  const [streamingFilter, setStreamingFilter] = useState('all')
  const [testingIds, setTestingIds] = useState<Set<number>>(new Set())

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
      // 系统类型 facet：API 均为网关，「仅 API 网关」命中；物理系统筛选对 API 无命中
      if (systemFilter === 'android' || systemFilter === 'harmony') return false
      if (vendorFilter !== 'all' && a.vendor !== vendorFilter) return false
      if (protocolFilter !== 'all' && a.protocol !== protocolFilter) return false
      if (streamingFilter !== 'all' && a.streaming !== (streamingFilter === 'streaming')) return false
      if (q) {
        // INT-1223：Master URL 移除，搜索 haystack 只含名称与首个端点
        const haystack = `${a.name} ${a.endpoints[0]?.endpoint ?? ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [resources.apis, keyword, statusFilter, labApiIds, systemFilter, vendorFilter, protocolFilter, streamingFilter])

  /** API 并发自动求和（§3.6.3 并发数参数卡；现 apiTest.steps.ts:154-158 口径） */
  const apiConcurrencySum = useMemo(
    () =>
      resources.apis
        .filter((a) => resources.apiIds.includes(a.id))
        .reduce((sum, a) => sum + a.maxConcurrent, 0),
    [resources.apis, resources.apiIds]
  )

  /** 卡片网格「全选在线 API」控制（当前筛选可见在线集；离线不可选） */
  const visibleOnlineApis = useMemo(
    () => visibleApis.filter((a) => a.status === 'online'),
    [visibleApis]
  )
  const allVisibleApisSelected =
    visibleOnlineApis.length > 0 &&
    visibleOnlineApis.every((a) => resources.apiIds.includes(a.id))

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
  const totalSelected = resources.deviceIds.length + resources.apiIds.length

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
            placeholder='搜索设备或 API 名称'
            className='h-8 w-[200px] ps-7 sm:w-[240px]'
          />
        </div>

        {/* 状态 facet */}
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as 'all' | 'online' | 'offline')}
          items={RESOURCE_STATUS_OPTIONS}
        >
          <SelectTrigger className='h-8 w-28 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RESOURCE_STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 实验室 facet（INT-486 口径；INT-487 设备-实验室绑定待接线） */}
        <Select
          value={labFilter}
          onValueChange={(v) => setLabFilter(v ?? 'all')}
          items={LAB_FILTER_OPTIONS}
        >
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LAB_FILTER_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 系统类型 facet（设备按 system/type；API 均为网关） */}
        <Select
          value={systemFilter}
          onValueChange={(v) => setSystemFilter(v as 'all' | 'android' | 'harmony' | 'api')}
          items={RESOURCE_SYSTEM_OPTIONS}
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

        {/* 厂商 facet（API 筛选维度，INT-486 口径） */}
        <Select
          value={vendorFilter}
          onValueChange={(v) => setVendorFilter(v ?? 'all')}
          items={RESOURCE_VENDOR_OPTIONS}
        >
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RESOURCE_VENDOR_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 协议 facet（API 筛选维度，INT-486 口径；INT-1800：4 个规范值） */}
        <Select
          value={protocolFilter}
          onValueChange={(v) => setProtocolFilter(v ?? 'all')}
          items={RESOURCE_PROTOCOL_OPTIONS}
        >
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RESOURCE_PROTOCOL_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 流式性 facet（INT-1800：第二维，与协议独立） */}
        <Select
          value={streamingFilter}
          onValueChange={(v) => setStreamingFilter(v ?? 'all')}
          items={RESOURCE_STREAMING_OPTIONS}
        >
          <SelectTrigger className='h-8 w-32 text-xs' aria-label='流式性筛选'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RESOURCE_STREAMING_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 右端操作（权限显隐；readOnly 隐藏） */}
        {!readOnly && (
          <div className='ml-auto flex items-center gap-2'>
            {canDeviceControl && (
              <Button variant='outline' size='sm' onClick={onScanDevices}>
                扫描设备
              </Button>
            )}
            {canDeviceCreate && (
              <Button variant='outline' size='sm' onClick={onAddDevice}>
                新增设备
              </Button>
            )}
            {canApiCreate && (
              <Button size='sm' onClick={() => onOpenApiEdit()}>
                新增 API
              </Button>
            )}
          </div>
        )}
      </div>

      {/* 过滤空态兜底（§3.3） */}
      {resources.devices.length === 0 &&
        resources.apis.length === 0 &&
        !resources.isLoading && (
          <Empty className='min-h-[200px] border-dashed'>
            <EmptyHeader>
              <EmptyMedia variant='icon' />
              <EmptyTitle>
                当前算法（{currentAlgorithm?.name ?? '未选择'}）下没有可用设备或 API
              </EmptyTitle>
              <EmptyDescription>
                {resources.isTemporary
                  ? `已临时显示全部，全局算法仍为 ${currentAlgorithm?.name ?? '未选择'}`
                  : '更换算法或查看全部资源'}
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
      {isVoiceLlm && (
        <Alert className='py-2'>
          <Info aria-hidden='true' className='size-4' />
          <AlertDescription className='text-xs'>{voiceLlmAlert}</AlertDescription>
        </Alert>
      )}

      {/* 资源区（设备网格 + 被测 API 表格，同屏同选混合执行） */}
      {resources.isLoading ? (
        <div aria-busy='true' className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className='h-44 w-full rounded-xl' />
          ))}
        </div>
      ) : (
        <>
          {/* 设备 */}
          <section className='space-y-2'>
            <h3 className='text-sm font-semibold'>
              设备
              <span className='text-muted-foreground ms-2 text-xs font-normal'>
                {visibleDevices.length} 台在线可执行设备
              </span>
            </h3>
            <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
              {visibleDevices.map((device) => (
                <DeviceCard
                  key={device.id}
                  device={device}
                  selected={resources.deviceIds.includes(device.id)}
                  readOnly={readOnly}
                  canControl={canDeviceControl}
                  testing={testingIds.has(device.id)}
                  mode={targetModes.getMode('device', device.id)}
                  onModeChange={(mode) => targetModes.setMode('device', device.id, mode)}
                  onToggle={resources.toggleDevice}
                  onTestConnection={() => void handleTestConnection(device)}
                />
              ))}
            </div>
            {visibleDevices.length === 0 && (
              <p className='text-muted-foreground text-xs'>当前筛选条件下没有可用设备</p>
            )}
          </section>

          {/* 被测 API（INT-1061：与设备同一套卡片形态，混选同屏一眼同形） */}
          <section className='space-y-2'>
            <div className='flex items-center justify-between'>
              <h3 className='text-sm font-semibold'>
                被测 API
                <span className='text-muted-foreground ms-2 text-xs font-normal'>
                  {visibleApis.length} 个可执行 API
                </span>
              </h3>
              {!readOnly && visibleOnlineApis.length > 0 && (
                <label className='flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground'>
                  <Checkbox
                    checked={allVisibleApisSelected}
                    aria-label='全选在线 API'
                    className='size-4'
                    onCheckedChange={() =>
                      resources.selectAllApis(
                        allVisibleApisSelected ? [] : visibleOnlineApis.map((a) => a.id)
                      )
                    }
                  />
                  全选在线
                </label>
              )}
            </div>
            <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
              {visibleApis.map((api) => (
                <ApiCard
                  key={api.id}
                  api={api}
                  selected={resources.apiIds.includes(api.id)}
                  readOnly={readOnly}
                  canTest={canApiTest}
                  canEdit={canApiEdit}
                  canDelete={canApiDelete}
                  testing={testingIds.has(api.id)}
                  mode={targetModes.getMode('api', api.id)}
                  onModeChange={(mode) => targetModes.setMode('api', api.id, mode)}
                  onToggle={resources.toggleApi}
                  onTestConnection={handleApiTest}
                  onEdit={onOpenApiEdit}
                  onDelete={(api) => void apisCrud.remove(api)}
                />
              ))}
            </div>
            {visibleApis.length === 0 && (
              <p className='text-muted-foreground text-xs'>当前筛选条件下没有可用 API</p>
            )}
          </section>
        </>
      )}

      {/* 执行参数区（§3.6.3；报告参数不在本步配置——负责人 2026-10-16 口径） */}
      <div className='border-border/70 bg-background/95 ring-foreground/5 rounded-xl border p-4 ring-1'>
        <h3 className='mb-3 text-sm font-semibold'>执行参数</h3>
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
          {/* 测试配置 */}
          <ParamCard
            label='测试轮数'
            value={`${params.rounds}`}
            description='每个用例执行的轮次数'
            readOnly={readOnly}
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
            readOnly={readOnly}
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
            readOnly={readOnly}
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

          {/* 并发数参数卡（可编辑；API 并发上限自动合计作补充） */}
          <ParamCard
            label='并发任务数'
            value={`${params.concurrency}`}
            description={`同时执行的用例数上限；所选 API 并发上限合计 ${apiConcurrencySum}`}
            readOnly={readOnly}
          >
            <Input
              type='number'
              min={1}
              max={32}
              value={params.concurrency}
              onChange={(e) => setParams({ concurrency: Number(e.target.value) || 4 })}
              className='h-8'
            />
          </ParamCard>
        </div>

        {/* voice_llm 建议并发 */}
        {isVoiceLlm && (
          <p className='text-warning mt-3 text-xs'>
            voice_llm 多轮对话测试建议并发数为 2（默认 4），以获得更稳定的结果。
          </p>
        )}

        {/* 网络配置（device:control 才可设；tester 无权限项隐藏只读展示） */}
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
      </div>

      {/* 已选资源汇总行（§3.6.3；位于执行参数区下方） */}
      {!readOnly && (
        <SelectionSummary
          mode='resource'
          count={totalSelected}
          countText={`${resources.deviceIds.length} 台设备 · ${resources.apiIds.length} 个 API`}
          unitText='个资源'
          concurrencyText={`并发上限 ${apiConcurrencySum}`}
          items={[
            ...selectedDevices.map((d) => ({ id: d.id, name: d.name, status: d.status })),
            ...selectedApis.map((a) => ({ id: a.id, name: a.name, status: a.status })),
          ]}
          onClear={() => {
            resources.selectAllDevices([])
            resources.selectAllApis([])
          }}
          onRemoveItem={(id) => {
            if (resources.deviceIds.includes(id)) resources.removeDevice(id)
            else resources.removeApi(id)
          }}
        />
      )}

      {/* 底部并行/串行示意图（§3.6.4：随选中目标 + 每卡模式实时更新；readOnly 只读渲染；
          全量列表解析名称——已选目标即使被筛选隐藏仍正确显示） */}
      <ExecutionDiagram
        devices={resources.allDevices}
        apis={resources.allApis}
      />

      {/* 分页 */}
      <div className='flex items-center justify-between text-xs'>
        <span className='text-muted-foreground'>
          共 {resources.devices.length} 台设备 · {resources.apis.length} 个 API
        </span>
        <span className='text-muted-foreground'>每页 10 条 · 第 1 / 1 页</span>
      </div>
    </div>
  )
}
