/**
 * 设备管理页（16_设备域.md §3；INT-491 可视稿）。
 * SectionPageLayout fixedContent + Title「设备管理」徽标「在线 {n}/共 {m}」（当前页签）+
 * 页头动作区（三开关+主按钮+更多操作）+ Content（Tabs 测试设备/播放设备/测试API →
 * 监控告警面板（仅测试页签，开关②）→ 筛选工具栏 → 统计徽章行 → 页签表格 → 批量浮条）+
 * Footer 分页 Portal。
 * 弹窗群（§6）：新增/编辑抽屉（随页签三分叉）、详情、扫描、分组管理、告警规则、实验室管理
 * （INT-655 真实 /laboratories CRUD）、关联声压映射、删除/批量确认。
 * 全局算法联动（§2.2，INT-1622）：测试设备列表按 useAlgorithmStore().algorithmId 过滤
 * （supportedAlgorithms contains，同后端 DeviceListQuery.algorithm_type 口径；列表全量拉取
 * 故在 feature 层过滤），切换器变更即时联动、chip × 清空回全部；本页不重复算法筛选器。
 */
import { useNavigate } from '@tanstack/react-router'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ApiError } from '@/infrastructure/api/api-error'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import {
  useApiDevices,
  useAlarmRules,
  useDeviceAlarms,
  useDeviceGroupDetailQuery,
  useDeviceGroups,
  useDeviceMutations,
  useLaboratories,
  usePlaybackDevices,
  useStatusHistory,
  useTestDevices,
  useAlarmMutations,
} from '@/application/devices/use-devices'
import {
  DEFAULT_PAGE_SIZE,
  DEVICES_STATS_LABELS,
  DEVICES_TABS,
  PAGE_SIZE_OPTIONS,
  type DevicesTabKey,
} from '@/features/devices/constants'
import type {
  ApiDeviceFilters,
  AssociateSplState,
  DeviceDeleteTarget,
  DeviceDetailState,
  DeviceHeaderToggles,
  DeviceMutateState,
  DevicesFilters,
  PlaybackDeviceFilters,
  TestDeviceFilters,
} from '@/features/devices/types'
import { DevicesPrimaryButtons } from '@/features/devices/components/devices-primary-buttons'
import { findDeviceGroup } from '@/features/devices/lib/device-group-tree'
import { filterTestDevicesByAlgorithm } from '@/features/devices/lib/device-algorithm-filter'
import { DevicesFilterToolbar } from '@/features/devices/components/devices-filter-toolbar'
import { DevicesStatsRow } from '@/features/devices/components/devices-stats-row'
import { TestDeviceTable } from '@/features/devices/components/test-device-table'
import { PlaybackDeviceTable } from '@/features/devices/components/playback-device-table'
import { ApiDeviceTable } from '@/features/devices/components/api-device-table'
import { DeviceBulkActions } from '@/features/devices/components/device-bulk-actions'
import { AlarmPanel } from '@/features/devices/components/monitor/alarm-panel'
import { AlarmRuleDialog } from '@/features/devices/components/monitor/alarm-rule-dialog'
import { DeviceMutateDrawer } from '@/features/devices/components/modals/device-mutate-drawer'
import { ScanDevicesDialog } from '@/features/devices/components/modals/scan-devices-dialog'
import { ImportDevicesDialog } from '@/features/devices/components/modals/import-devices-dialog'
import { ExportDevicesDialog } from '@/features/devices/components/modals/export-devices-dialog'
import { DeviceDetailDialog } from '@/features/devices/components/modals/device-detail-dialog'
import { DeviceGroupManagerDialog } from '@/features/devices/components/modals/device-group-manager-dialog'
import { LaboratoryManagerDialog } from '@/features/devices/components/modals/laboratory-manager-dialog'
import { AssociateSplDialog } from '@/features/devices/components/modals/associate-spl-dialog'
import {
  DeviceOperateDialog,
  type DeviceOperateKind,
} from '@/features/devices/components/modals/device-operate-dialog'
import type { TestDevice } from '@/domain/models/testDevice'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { ApiDevice } from '@/domain/models/apiDevice'
import type { DeviceGroup } from '@/domain/models/deviceGroup'

const DEFAULT_FILTERS: DevicesFilters = {
  search: '',
  status: null,
  labId: null,
  groupId: null,
}

const DEFAULT_TEST_FILTERS: TestDeviceFilters = { ...DEFAULT_FILTERS, connectionType: null }
const DEFAULT_PLAYBACK_FILTERS: PlaybackDeviceFilters = { ...DEFAULT_FILTERS, deviceType: null }
const DEFAULT_API_FILTERS: ApiDeviceFilters = {
  search: '',
  status: null,
  protocol: null,
  environment: null,
}

export function DevicesPage({ tab }: { tab: DevicesTabKey }) {
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const canCreate = hasPermission(
    tab === 'test' ? 'device:create' : tab === 'playback' ? 'playback:create' : 'api_config:create'
  )
  const canUpdate = hasPermission(
    tab === 'test' ? 'device:update' : tab === 'playback' ? 'playback:update' : 'api_config:update'
  )
  const canDelete = hasPermission(
    tab === 'test' ? 'device:delete' : tab === 'playback' ? 'playback:delete' : 'api_config:delete'
  )
  const canControl = hasPermission(
    tab === 'test' ? 'device:control' : tab === 'playback' ? 'playback:control' : 'api_config:test'
  )
  /** 健康检查权限：API 页签走 api_config:read（§3.6），测试页签走 device:control（P2-7 返修） */
  const canHealth = hasPermission(
    tab === 'api' ? 'api_config:read' : tab === 'test' ? 'device:control' : 'playback:control'
  )
  /** 批量健康检查（§3.3：device:control 且仅测试设备页签，P2-8 返修） */
  const canBatchHealth = hasPermission('device:control') && tab === 'test'
  const canRead = hasPermission(
    tab === 'test' ? 'device:read' : tab === 'playback' ? 'playback:read' : 'api_config:read'
  )
  const canGroupManage = hasPermission('device:read')
  const canLabManage = hasPermission('device:read')

  /** 支持算法 value→中文名映射（照 V9.7.10 getAlgorithmTypeName；INT-1215 无裸枚举） */
  const { options: algorithmOptions } = useAlgorithmOptions()
  const algorithmNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const opt of algorithmOptions) {
      if (opt.value) map[opt.value] = opt.name
    }
    return map
  }, [algorithmOptions])

  /** §2.2 全局算法：订阅右上角切换器同一 store（变更即时联动；空串＝全部算法） */
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const testQuery = useTestDevices()
  const playbackQuery = usePlaybackDevices()
  const apiQuery = useApiDevices()
  const labsQuery = useLaboratories()
  const groupsQuery = useDeviceGroups()
  const alarmsQuery = useDeviceAlarms()
  const rulesQuery = useAlarmRules()
  const historyQuery = useStatusHistory()
  const { removeTest, removePlayback, removeApi, control, setOccupied, batch, invalidateAll } =
    useDeviceMutations()
  const { acknowledge } = useAlarmMutations()

  const [testFilters, setTestFilters] = useState<TestDeviceFilters>(DEFAULT_TEST_FILTERS)
  const [playbackFilters, setPlaybackFilters] = useState<PlaybackDeviceFilters>(DEFAULT_PLAYBACK_FILTERS)
  const [apiFilters, setApiFilters] = useState<ApiDeviceFilters>(DEFAULT_API_FILTERS)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [toggles, setToggles] = useState<DeviceHeaderToggles>({
    batchMode: false,
    alarmsOpen: false,
    idSort: false,
  })

  // 弹窗群
  const [mutateState, setMutateState] = useState<DeviceMutateState>({
    open: false,
    mode: 'create',
    kind: 'test',
  })
  const [mutatePrefill, setMutatePrefill] = useState<
    Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null
  >(null)
  const [scanOpen, setScanOpen] = useState(false)
  /** 导入/导出弹窗（INT-1624：接 INT-816 三资源端点，按当前页签取资源） */
  const [importOpen, setImportOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  /** INT-1029 扫描弹窗来源（header=更多操作扫描 → 开新增；drawer=抽屉内扫描 → 回填当前表单） */
  const [scanInvoker, setScanInvoker] = useState<'header' | 'drawer'>('header')
  const [mutateScanFill, setMutateScanFill] = useState<{
    nonce: number
    kind: DevicesTabKey
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  } | null>(null)
  const [detailState, setDetailState] = useState<DeviceDetailState>({
    open: false,
    kind: 'test',
    device: null,
  })
  const [groupManagerOpen, setGroupManagerOpen] = useState(false)
  const [labManagerOpen, setLabManagerOpen] = useState(false)
  const [ruleDialogOpen, setRuleDialogOpen] = useState(false)
  const [associateSplState, setAssociateSplState] = useState<AssociateSplState>({
    open: false,
    device: null,
  })
  const [operateState, setOperateState] = useState<{
    open: boolean
    kind: DeviceOperateKind | null
    device: TestDevice | null
  }>({ open: false, kind: null, device: null })
  const [deleteTarget, setDeleteTarget] = useState<DeviceDeleteTarget | null>(null)
  const [batchConfirm, setBatchConfirm] = useState<{ action: string; count: number } | null>(null)
  const [confirmPending, setConfirmPending] = useState(false)

  // 页签切换重置筛选与选择
  useEffect(() => {
    setTestFilters(DEFAULT_TEST_FILTERS)
    setPlaybackFilters(DEFAULT_PLAYBACK_FILTERS)
    setApiFilters(DEFAULT_API_FILTERS)
    setSelectedIds(new Set())
    setPage(1)
    setToggles((prev) => ({ ...prev, alarmsOpen: false }))
    // 页签切换即关导入/导出弹窗（资源随页签变化，避免在旧页签资源上继续操作）
    setImportOpen(false)
    setExportOpen(false)
  }, [tab])

  // 全局算法变更（含 chip × 清空）→ 回第一页并清空选择，避免对已不可见的设备做批量操作
  useEffect(() => {
    setPage(1)
    setSelectedIds(new Set())
  }, [algorithmId])

  const testDevices = testQuery.data ?? []
  /** 测试设备先按全局算法收窄（§2.2）；工具栏/统计/徽标/分页均基于收窄后的口径 */
  const algorithmFilteredTestDevices = useMemo(
    () => filterTestDevicesByAlgorithm(testDevices, algorithmId),
    [testDevices, algorithmId]
  )
  const playbackDevices = playbackQuery.data ?? []
  const apiDevices = apiQuery.data ?? []
  const labs = labsQuery.data ?? []
  const groups = groupsQuery.data ?? []
  const alarms = alarmsQuery.data?.alarms ?? []
  const alarmStats = alarmsQuery.data?.stats ?? null
  const rules = rulesQuery.data ?? []
  const history = historyQuery.data ?? []
  /** P2-1：分组筛选走详情真实成员（列表 device_ids 恒空；选中分组时按需拉取） */
  const groupFilterDetail = useDeviceGroupDetailQuery(testFilters.groupId)

  /* ───────── 过滤 / 排序 / 分页 ───────── */

  const filteredRows = useMemo(() => {
    if (tab === 'test') {
      let rows = algorithmFilteredTestDevices
      const f = testFilters
      const keyword = f.search.trim().toLowerCase()
      if (keyword) {
        rows = rows.filter(
          (row) =>
            row.name.toLowerCase().includes(keyword) ||
            (row.model ?? '').toLowerCase().includes(keyword) ||
            (row.serialNumber ?? '').toLowerCase().includes(keyword)
        )
      }
      if (f.status) rows = rows.filter((row) => row.status === f.status)
      if (f.connectionType) rows = rows.filter((row) => row.connectionType === f.connectionType)
      if (f.groupId) {
        // INT-864：分组树嵌套后，按引用查找需递归（含子分组）
        const group = findDeviceGroup(groups, f.groupId)
        // P2-1：详情 device_ids 为真实成员（列表恒空）；并合树成员兜底（嵌套/未来列表补 device_ids）
        const memberIds = new Set<number>([
          ...(groupFilterDetail.data?.members ?? []),
          ...(group ? collectGroupMemberIds(group) : []),
        ])
        rows = rows.filter((row) => memberIds.has(row.id))
      }
      if (f.labId) rows = rows.filter((row) => String(row.labId) === f.labId)
      return rows
    }
    if (tab === 'playback') {
      let rows = playbackDevices
      const f = playbackFilters
      const keyword = f.search.trim().toLowerCase()
      if (keyword) {
        rows = rows.filter(
          (row) =>
            row.name.toLowerCase().includes(keyword) ||
            (row.model ?? '').toLowerCase().includes(keyword)
        )
      }
      if (f.status) rows = rows.filter((row) => row.status === f.status)
      if (f.deviceType) rows = rows.filter((row) => row.deviceType === f.deviceType)
      if (f.labId) rows = rows.filter((row) => String(row.labId) === f.labId)
      return rows
    }
    let rows = apiDevices
    const f = apiFilters
    const keyword = f.search.trim().toLowerCase()
    if (keyword) {
      rows = rows.filter(
        (row) =>
          row.name.toLowerCase().includes(keyword) ||
          // INT-1223：Master URL 移除，关键字过滤只走名称与端点列表
          row.endpoints.some((ep) => ep.endpoint.toLowerCase().includes(keyword))
      )
    }
    if (f.status) rows = rows.filter((row) => row.status === f.status)
    if (f.protocol) rows = rows.filter((row) => row.protocol === f.protocol)
    if (f.environment) rows = rows.filter((row) => row.environment === f.environment)
    return rows
  }, [tab, algorithmFilteredTestDevices, playbackDevices, apiDevices, testFilters, playbackFilters, apiFilters, groups, groupFilterDetail.data])

  const sortedRows = useMemo(() => {
    const rows = [...filteredRows]
    if (toggles.idSort) {
      rows.sort((a, b) => a.id - b.id)
    } else {
      rows.sort((a, b) => {
        const diff = new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime()
        return sortOrder === 'desc' ? diff : -diff
      })
    }
    return rows
  }, [filteredRows, toggles.idSort, sortOrder])

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => sortedRows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [sortedRows, safePage, pageSize]
  )

  const isFiltered = useMemo(() => {
    const f =
      tab === 'test' ? testFilters : tab === 'playback' ? playbackFilters : apiFilters
    return Object.values(f).some((value) => value != null && value !== '' && value !== 'all')
  }, [tab, testFilters, playbackFilters, apiFilters])

  const activeFilters = tab === 'test' ? testFilters : tab === 'playback' ? playbackFilters : apiFilters
  const setActiveFilters = (
    next: TestDeviceFilters | PlaybackDeviceFilters | ApiDeviceFilters
  ) => {
    setPage(1)
    if (tab === 'test') setTestFilters(next as TestDeviceFilters)
    else if (tab === 'playback') setPlaybackFilters(next as PlaybackDeviceFilters)
    else setApiFilters(next as ApiDeviceFilters)
  }

  /* ───────── 统计徽章（§9：总/在线/离线/异常；API 独立口径） ───────── */

  const statsValues = useMemo(() => {
    if (tab === 'api') {
      const online = apiDevices.filter((d) => d.status === 'online').length
      const offline = apiDevices.filter((d) => d.status === 'offline').length
      const testing = apiDevices.filter((d) => d.occupied).length
      return [apiDevices.length, online, offline, testing]
    }
    const devices = tab === 'test' ? algorithmFilteredTestDevices : playbackDevices
    const online = devices.filter((d) => d.status === 'online').length
    // §3.4 注 / INT-487：连接中/断开中为瞬时态不入徽章，离线只计 status==='offline'（P2-5 返修）
    const offline = devices.filter((d) => d.status === 'offline').length
    const error = devices.filter((d) => d.status === 'error').length
    return [devices.length, online, offline, error]
  }, [tab, algorithmFilteredTestDevices, playbackDevices, apiDevices])

  /* ───────── 选择 ───────── */

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    // P3-30 返修：按「本页是否全选」切换，保留跨页选择集（不再 prev.size===pageRows.length 巧合清选）
    setSelectedIds((prev) => {
      const pageSelected = pageRows.filter((row) => prev.has(row.id))
      if (pageRows.length > 0 && pageSelected.length === pageRows.length) {
        const next = new Set(prev)
        pageRows.forEach((row) => next.delete(row.id))
        return next
      }
      const next = new Set(prev)
      pageRows.forEach((row) => next.add(row.id))
      return next
    })
  }

  /* ───────── 行操作分派 ───────── */

  /** P2-3 返修：行级控制透传 device.id（不再打向 id=0）；P2-2：操作参数透传到请求体 */
  const handleControl = async (id: number, action: string, params?: Record<string, unknown>) => {
    const result = await control.mutateAsync({ id, action, params })
    void result
    toast.success('操作已提交')
  }

  const openMutate = (
    state: DeviceMutateState,
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice> | null = null
  ) => {
    setMutatePrefill(prefill)
    setMutateState(state)
  }

  const handleDetailEdit = (kind: DevicesTabKey, device: TestDevice | PlaybackDevice | ApiDevice) => {
    setMutateState({ open: true, mode: 'edit', kind, device })
  }

  /** P3-20 返修：测试/停止测试置/清 occupied 本地瞬时态兜底（INT-487 §3.4 注③） */
  const handleTest = (device: TestDevice) => {
    void setOccupied.mutateAsync({ kind: 'test', id: device.id, occupied: true })
    toast.success(`已开始测试：${device.name}`)
  }

  const handleStopTest = (device: TestDevice) => {
    void setOccupied.mutateAsync({ kind: 'test', id: device.id, occupied: false })
    toast.success(`已停止设备「${device.name}」的测试`)
  }

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return
    setConfirmPending(true)
    try {
      let result: { success: boolean; message?: string } = { success: true }
      if (deleteTarget.kind === 'test') result = await removeTest.mutateAsync(deleteTarget.device.id)
      else if (deleteTarget.kind === 'playback') result = await removePlayback.mutateAsync(deleteTarget.device.id)
      else result = await removeApi.mutateAsync(deleteTarget.device.id)
      if (result.success) toast.success('设备已删除')
      else toast.error(result.message ?? '删除失败，请重试')
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    } finally {
      setConfirmPending(false)
    }
  }

  const handleBatchAction = async (action: string) => {
    if (selectedIds.size === 0) {
      toast.info('请先勾选需要操作的设备')
      return
    }
    if (action === 'delete') {
      setBatchConfirm({ action, count: selectedIds.size })
      return
    }
    setBatchConfirm({ action, count: selectedIds.size })
  }

  const handleBatchConfirm = async () => {
    if (!batchConfirm) return
    setConfirmPending(true)
    try {
      if (batchConfirm.action === 'delete') {
        // §3.8：delete 前端串行（batch 白名单不含 delete，§11-7）
        for (const id of [...selectedIds]) {
          if (tab === 'test') await removeTest.mutateAsync(id)
          else if (tab === 'playback') await removePlayback.mutateAsync(id)
          else await removeApi.mutateAsync(id)
        }
        toast.success(`批量删除完成：成功 ${selectedIds.size} 个`)
      } else {
        const result = await batch.mutateAsync({
          action: batchConfirm.action,
          ids: [...selectedIds],
        })
        const label = BATCH_ACTION_LABEL[batchConfirm.action] ?? batchConfirm.action
        // P2-6 返修：按 batch 响应命中标记（replayedCount）区分；部分失败显「成功 s/t」
        toast.success(
          (result.replayedCount ?? 0) > 0
            ? `${label}：命中幂等回放，未重复执行`
            : `${label}完成：成功 ${result.successCount}/${result.total}`
        )
      }
      setSelectedIds(new Set())
      setBatchConfirm(null)
    } catch {
      toast.error('操作失败，请稍后重试')
    } finally {
      setConfirmPending(false)
    }
  }

  /** P2-13 返修：扫描「添加」透传行数据预填（§6.1 test: name/model/serialNumber/system归一/...） */
  const handleScanAdd = (
    kind: DevicesTabKey,
    prefill: Partial<TestDevice> | Partial<PlaybackDevice> | Partial<ApiDevice>
  ) => {
    // INT-1029：抽屉内扫描「选择」→ 回填当前抽屉表单（编辑/新增态均保持打开）；头部扫描 → 开新增抽屉
    if (scanInvoker === 'drawer' && mutateState.open) {
      setMutateScanFill({ nonce: Date.now(), kind, prefill })
      setScanOpen(false)
      setScanInvoker('header')
      return
    }
    setScanOpen(false)
    openMutate({ open: true, mode: 'create', kind }, prefill)
  }

  const tabRowCallbacks = {
    test: {
      canRead,
      canUpdate,
      canDelete,
      canControl,
      canHealth,
      onDetail: (device: TestDevice) => setDetailState({ open: true, kind: 'test', device }),
      onEdit: (device: TestDevice) => openMutate({ open: true, mode: 'edit', kind: 'test', device }),
      onHealth: (device: TestDevice) => {
        void handleControl(device.id, 'health_check')
        toast.success(`健康检查已发起：${device.name}`)
      },
      onTest: (device: TestDevice) => handleTest(device),
      onStopTest: (device: TestDevice) => handleStopTest(device),
      onControl: (device: TestDevice, action: string) => void handleControl(device.id, action),
      onInstallApp: (device: TestDevice) =>
        setOperateState({ open: true, kind: 'install-app', device }),
      onUninstallApp: (device: TestDevice) =>
        setOperateState({ open: true, kind: 'uninstall-app', device }),
      onDelete: (device: TestDevice) => setDeleteTarget({ kind: 'test', device }),
      onEmptyAdd: () => openMutate({ open: true, mode: 'create', kind: 'test' }),
    },
    playback: {
      canRead,
      canUpdate,
      canDelete,
      canControl,
      canHealth,
      onDetail: (device: PlaybackDevice) => setDetailState({ open: true, kind: 'playback', device }),
      onEdit: (device: PlaybackDevice) => openMutate({ open: true, mode: 'edit', kind: 'playback', device }),
      onAssociateSpl: (device: PlaybackDevice) => setAssociateSplState({ open: true, device }),
      onPlayTest: (device: PlaybackDevice) => toast.success(`已开始播放测试：${device.name}`),
      onStop: (device: PlaybackDevice) => toast.success(`已停止播放：${device.name}`),
      onControl: (device: PlaybackDevice, action: string) => void handleControl(device.id, action),
      onResultAnalysis: (device: PlaybackDevice) => toast.success(`已生成播放测试结果分析：${device.name}`),
      onDiagnose: (device: PlaybackDevice) => toast.success(`设备诊断完成：${device.name}`),
      onDelete: (device: PlaybackDevice) => setDeleteTarget({ kind: 'playback', device }),
      onEmptyAdd: () => openMutate({ open: true, mode: 'create', kind: 'playback' }),
    },
    api: {
      canRead,
      canUpdate,
      canDelete,
      canControl,
      canHealth,
      onDetail: (device: ApiDevice) => setDetailState({ open: true, kind: 'api', device }),
      onEdit: (device: ApiDevice) => openMutate({ open: true, mode: 'edit', kind: 'api', device }),
      onHealth: (device: ApiDevice) => {
        // 接线 INT-644：API 健康检查走 POST /apis/{id}/health（区别于测试设备 /test-devices/health-check）
        void handleControl(device.id, 'api_health_check')
        toast.success(`健康检查已发起：${device.name}`)
      },
      onStopTest: (device: ApiDevice) => toast.success(`已停止测试：${device.name}`),
      onDelete: (device: ApiDevice) => setDeleteTarget({ kind: 'api', device }),
      onEmptyAdd: () => openMutate({ open: true, mode: 'create', kind: 'api' }),
    },
  }

  /* ───────── 页面装配（§3.1 骨架） ───────── */

  const onlineCount = tab === 'api'
    ? apiDevices.filter((d) => d.status === 'online').length
    : (tab === 'test' ? algorithmFilteredTestDevices : playbackDevices).filter((d) => d.status === 'online').length
  const totalCount = tab === 'api' ? apiDevices.length : (tab === 'test' ? algorithmFilteredTestDevices : playbackDevices).length

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            设备管理
            <Badge variant='outline' className='font-normal tabular-nums'>
              {/* §3.1/§9 口径「在线 {n}/共 {m}」（P3-23 返修：API 页签不再用「可用」） */}
              在线 {onlineCount}/共 {totalCount}
            </Badge>
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <DevicesPrimaryButtons
            tab={tab}
            toggles={toggles}
            onTogglesChange={setToggles}
            canCreate={canCreate}
            canImport={canCreate}
            canExport={canRead}
            canControl={canControl}
            canBatchHealth={canBatchHealth}
            canGroupManage={canGroupManage}
            canLabManage={canLabManage}
            onAdd={() => openMutate({ open: true, mode: 'create', kind: tab })}
            onScan={() => {
              setScanInvoker('header')
              setScanOpen(true)
            }}
            onGroupManage={() => setGroupManagerOpen(true)}
            onLabManage={() => setLabManagerOpen(true)}
            onBatchHealth={() => void handleBatchAction('health_check')}
            onImport={() => setImportOpen(true)}
            onExport={() => setExportOpen(true)}
          />
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            {/* 页签（§3.1 测试设备/播放设备/测试API；路径式 /devices/$tab） */}
            <Tabs
              value={tab}
              onValueChange={(value) =>
                void navigate({ to: '/devices/$tab', params: { tab: value } })
              }
            >
              <TabsList className='max-w-full flex-wrap justify-start'>
                {DEVICES_TABS.filter(
                  (item) => item.value === tab || hasPermission(item.requiredPermission)
                ).map((item) => (
                  <TabsTrigger key={item.value} value={item.value}>
                    {item.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {/* 监控告警面板（仅测试设备页签，开关②） */}
            {tab === 'test' && (
              <AlarmPanel
                open={toggles.alarmsOpen}
                onOpenChange={(alarmsOpen) => setToggles((prev) => ({ ...prev, alarmsOpen }))}
                alarms={alarms}
                stats={alarmStats}
                statusHistory={history}
                loading={alarmsQuery.isLoading}
                canControl={canControl}
                canUpdate={canUpdate}
                onAcknowledge={(alarm) => {
                  void acknowledge.mutateAsync(alarm.id)
                  toast.success('告警已确认')
                }}
                onManageRules={() => setRuleDialogOpen(true)}
              />
            )}

            <DevicesFilterToolbar
              tab={tab}
              showAlgorithmChip={tab === 'test'}
              searchValue={activeFilters.search}
              onSearch={(value) => setActiveFilters({ ...activeFilters, search: value })}
              status={activeFilters.status}
              onStatus={(status) => setActiveFilters({ ...activeFilters, status })}
              labs={labs}
              labId={tab === 'api' ? null : tab === 'test' ? testFilters.labId : playbackFilters.labId}
              onLabId={(labId) => {
                // P3-30 返修：分组/实验室筛选变更也重置页码
                setPage(1)
                if (tab === 'test') setTestFilters({ ...testFilters, labId })
                else if (tab === 'playback') setPlaybackFilters({ ...playbackFilters, labId })
              }}
              groups={groups}
              groupId={tab === 'test' ? testFilters.groupId : null}
              onGroupId={(groupId) => {
                setPage(1)
                setTestFilters({ ...testFilters, groupId })
              }}
              connectionType={testFilters.connectionType}
              onConnectionType={(connectionType) =>
                setActiveFilters({ ...testFilters, connectionType })
              }
              deviceType={playbackFilters.deviceType}
              onDeviceType={(deviceType) =>
                setActiveFilters({ ...playbackFilters, deviceType })
              }
              protocol={apiFilters.protocol}
              onProtocol={(protocol) => setActiveFilters({ ...apiFilters, protocol })}
              environment={apiFilters.environment}
              onEnvironment={(environment) => setActiveFilters({ ...apiFilters, environment })}
              isFiltered={isFiltered}
              onReset={() => {
                if (tab === 'test') setTestFilters(DEFAULT_TEST_FILTERS)
                else if (tab === 'playback') setPlaybackFilters(DEFAULT_PLAYBACK_FILTERS)
                else setApiFilters(DEFAULT_API_FILTERS)
                setPage(1)
              }}
            />

            <DevicesStatsRow
              labels={DEVICES_STATS_LABELS[tab]}
              values={statsValues}
              loading={tab === 'test' ? testQuery.isLoading : tab === 'playback' ? playbackQuery.isLoading : apiQuery.isLoading}
            />

            <div className='min-h-0 flex-1 overflow-y-auto'>
              {tab === 'test' && (
                <TestDeviceTable
                  rows={pageRows as TestDevice[]}
                  loading={testQuery.isLoading}
                  total={sortedRows.length}
                  unfilteredTotal={testDevices.length}
                  searchKeyword={testFilters.search}
                  selectedIds={selectedIds}
                  batchMode={toggles.batchMode}
                  sortOrder={sortOrder}
                  algorithmNameMap={algorithmNameMap}
                  onSortChange={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
                  onToggleSelect={toggleSelect}
                  onToggleSelectAll={toggleSelectAll}
                  {...tabRowCallbacks.test}
                />
              )}
              {tab === 'playback' && (
                <PlaybackDeviceTable
                  rows={pageRows as PlaybackDevice[]}
                  loading={playbackQuery.isLoading}
                  total={sortedRows.length}
                  searchKeyword={playbackFilters.search}
                  selectedIds={selectedIds}
                  batchMode={toggles.batchMode}
                  sortOrder={sortOrder}
                  onSortChange={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
                  onToggleSelect={toggleSelect}
                  onToggleSelectAll={toggleSelectAll}
                  {...tabRowCallbacks.playback}
                />
              )}
              {tab === 'api' && (
                <ApiDeviceTable
                  rows={pageRows as ApiDevice[]}
                  loading={apiQuery.isLoading}
                  total={sortedRows.length}
                  searchKeyword={apiFilters.search}
                  selectedIds={selectedIds}
                  batchMode={toggles.batchMode}
                  onToggleSelect={toggleSelect}
                  onToggleSelectAll={toggleSelectAll}
                  {...tabRowCallbacks.api}
                />
              )}
            </div>

            {/* 批量浮条（§3.8：勾选≥1 浮起；批量模式开启时亦可显） */}
            <DeviceBulkActions
              tab={tab}
              count={selectedIds.size}
              canControl={canControl}
              canDelete={canDelete}
              onClear={() => setSelectedIds(new Set())}
              onAction={(action) => void handleBatchAction(action)}
            />

            {/* 分页 Portal（§3.9） */}
            <PageFooterPortal>
              <PaginationBar
                page={safePage}
                pageCount={pageCount}
                pageSize={pageSize}
                total={sortedRows.length}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </PageFooterPortal>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§6 Context Provider 挂页级） */}
      <DeviceMutateDrawer
        state={mutateState}
        prefill={mutatePrefill}
        onOpenChange={(open) =>
          setMutateState((prev) => ({ ...prev, open, mode: open ? prev.mode : 'create' }))
        }
        onScan={() => {
          setScanInvoker('drawer')
          setScanOpen(true)
        }}
        scanFill={mutateScanFill}
      />
      <ScanDevicesDialog
        open={scanOpen}
        onOpenChange={(open) => {
          setScanOpen(open)
          if (!open) setScanInvoker('header')
        }}
        tab={tab}
        onAddToMutate={handleScanAdd}
        fillMode={scanInvoker === 'drawer'}
      />
      {/* 导入/导出（§4.5；INT-1624 接 INT-816；导入成功刷新列表/徽章/统计卡） */}
      <ImportDevicesDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        tab={tab}
        onImported={invalidateAll}
      />
      <ExportDevicesDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        tab={tab}
        selectedIds={[...selectedIds]}
        filteredIds={sortedRows.map((row) => row.id)}
      />
      <DeviceDetailDialog
        state={detailState}
        onOpenChange={(open) => setDetailState((prev) => ({ ...prev, open, device: open ? prev.device : null }))}
        onEdit={handleDetailEdit}
        canUpdate={canUpdate}
        algorithmNameMap={algorithmNameMap}
      />
      <DeviceGroupManagerDialog
        open={groupManagerOpen}
        onOpenChange={setGroupManagerOpen}
        groups={groups}
        testDevices={testDevices}
      />
      <LaboratoryManagerDialog
        open={labManagerOpen}
        onOpenChange={setLabManagerOpen}
        labs={labs}
      />
      <AlarmRuleDialog
        open={ruleDialogOpen}
        onOpenChange={setRuleDialogOpen}
        rules={rules}
      />
      <AssociateSplDialog
        state={associateSplState}
        onOpenChange={(open) => setAssociateSplState((prev) => ({ ...prev, open }))}
      />
      <DeviceOperateDialog
        open={operateState.open}
        kind={operateState.kind}
        device={operateState.device}
        onOpenChange={(open) =>
          setOperateState((prev) => ({ ...prev, open, kind: open ? prev.kind : null }))
        }
        onConfirm={(kind, filePath, packageName) => {
          const device = operateState.device
          if (!device) return
          // P2-2：安装/卸载参数进真实请求体（device_command_service.control 契约 body.params：
          // install_app 需 file_path（+ package_name），uninstall_app 需 package_name）
          const action = kind === 'install-app' ? 'install_app' : 'uninstall_app'
          const params =
            kind === 'install-app'
              ? { file_path: filePath, package_name: packageName }
              : { package_name: packageName }
          void (async () => {
            try {
              await control.mutateAsync({ id: device.id, action, params })
              toast.success(
                kind === 'install-app'
                  ? `已发起安装「${packageName}」（路径 ${filePath}）`
                  : `已发起卸载「${packageName}」`
              )
            } catch (error) {
              toast.error(error instanceof ApiError ? error.userMessage : '操作失败，请重试')
            } finally {
              setOperateState({ open: false, kind: null, device: null })
            }
          })()
        }}
      />

      {/* 删除确认（§3.4.1/§3.5/§3.6） */}
      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除设备'
        desc={
          deleteTarget
            ? `确定要删除「${deleteTarget.device.name}」吗？此操作不可撤销。`
            : ''
        }
        destructive
        confirmText='删除'
        isLoading={confirmPending}
        handleConfirm={() => void handleDeleteConfirm()}
      />

      {/* 批量操作确认（§3.8） */}
      <ConfirmDialog
        open={batchConfirm != null}
        onOpenChange={(open) => !open && setBatchConfirm(null)}
        title='批量操作'
        desc={
          batchConfirm
            ? `确定对选中的 ${batchConfirm.count} 个${tab === 'api' ? 'API' : '设备'}执行「${BATCH_ACTION_LABEL[batchConfirm.action] ?? batchConfirm.action}」？`
            : ''
        }
        destructive={batchConfirm?.action === 'delete'}
        confirmText={batchConfirm?.action === 'delete' ? '批量删除' : '确认执行'}
        isLoading={confirmPending}
        handleConfirm={() => void handleBatchConfirm()}
      />
    </>
  )
}

/* ───────── 批量动作中文（§9 toast 口径） ───────── */

/** P3-29 返修：递归收集分组（含嵌套子分组）成员 id */
function collectGroupMemberIds(group: DeviceGroup, acc: Set<number> = new Set()): Set<number> {
  for (const member of group.members) acc.add(member)
  for (const child of group.children) collectGroupMemberIds(child, acc)
  return acc
}

const BATCH_ACTION_LABEL: Record<string, string> = {
  connect: '连接',
  disconnect: '断开',
  reboot: '重启',
  shutdown: '关机',
  health_check: '健康检查',
  delete: '删除',
}

/* ───────────────────────── 分页条（§3.9） ───────────────────────── */

function PaginationBar({
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number
  pageCount: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}) {
  return (
    <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
      <span className='text-muted-foreground tabular-nums'>共 {total} 条</span>
      <Select
        value={String(pageSize)}
        items={PAGE_SIZE_OPTIONS.map((size) => ({
          value: String(size),
          label: `${size} 条/页`,
        }))}
        onValueChange={(value) => onPageSizeChange(Number(value ?? DEFAULT_PAGE_SIZE))}
      >
        <SelectTrigger size='sm' className='w-24'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZE_OPTIONS.map((size) => (
            <SelectItem key={size} value={String(size)}>
              {size} 条/页
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className='flex items-center gap-1'>
        {/* P3-33：首/末页 DoubleArrow（§3.9） */}
        <Button
          variant='outline'
          size='sm'
          className='h-8 min-w-8 px-2'
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
          aria-label='首页'
        >
          <ChevronsLeft aria-hidden='true' className='size-3.5' />
        </Button>
        <Button
          variant='outline'
          size='sm'
          className='h-8 min-w-8 px-2'
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label='上一页'
        >
          <ChevronLeft aria-hidden='true' className='size-3.5' />
        </Button>
        <span className='text-muted-foreground px-1 tabular-nums'>
          {page} / {pageCount}
        </span>
        <Button
          variant='outline'
          size='sm'
          className='h-8 min-w-8 px-2'
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label='下一页'
        >
          <ChevronRight aria-hidden='true' className='size-3.5' />
        </Button>
        <Button
          variant='outline'
          size='sm'
          className='h-8 min-w-8 px-2'
          disabled={page >= pageCount}
          onClick={() => onPageChange(pageCount)}
          aria-label='末页'
        >
          <ChevronsRight aria-hidden='true' className='size-3.5' />
        </Button>
      </div>
    </div>
  )
}
