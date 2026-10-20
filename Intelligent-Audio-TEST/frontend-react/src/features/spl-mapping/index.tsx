/**
 * 声压级映射管理页（16_设备域.md §4；INT-506 可视稿）。
 * SectionPageLayout fixedContent + Title「声压级映射管理」徽标「已校准 {n}/共 {m}」+ 页头动作区
 * （主按钮随页签切换「添加增益映射/添加 RMS-SPL 映射」+ 设备页签「批量配置 SPL」「导入映射数据」
 * 禁用）+ 双口径 Tabs + 筛选工具栏（搜索+校准状态 facet+关联设备/关联 API facet）+ 统计徽章行
 * + DataTable（物理域/数字域）+ 三口径对称 Alert + 分页 Portal。
 * 弹窗群（§6.7-6.12 / §6.22）：映射表单/详情/校准历史/数字校准/数字表单/数字详情/批量 SPL 配置/删除确认。
 * mock 数据对齐 api_gateway/schemas/spl.py + api_rms_spl.py；不接后端。
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { AudioWaveform, ChevronsLeft, ChevronsRight, Plus, UploadCloud } from 'lucide-react'

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  usePlaybackDeviceRefs,
  useSplMappings,
  useSplMutations,
  useSplStats,
} from '@/application/spl/useSplMappings'
import {
  useApiRefs,
  useDigitalSplMappings,
  useDigitalSplMutations,
} from '@/application/spl/useDigitalSplMappings'
import {
  DEFAULT_PAGE_SIZE,
  DOMAIN_TABS,
  PAGE_SIZE_OPTIONS,
} from '@/features/spl-mapping/constants'
import type {
  BatchSplDialogState,
  DeviceSplDialogState,
  DigitalSplDialogState,
  SplDomain,
  SplListFilters,
} from '@/features/spl-mapping/types'
import { SplStatsRow } from '@/features/spl-mapping/components/spl-stats-row'
import { SplFilterToolbar } from '@/features/spl-mapping/components/spl-filter-toolbar'
import { DeviceSplTable } from '@/features/spl-mapping/components/device-spl-table'
import { DigitalSplTable } from '@/features/spl-mapping/components/digital-spl-table'
import { SplSymmetryAlert } from '@/features/spl-mapping/components/spl-symmetry-alert'
import { SplMappingFormDialog } from '@/features/spl-mapping/components/modals/spl-mapping-form-dialog'
import { SplMappingDetailDialog } from '@/features/spl-mapping/components/modals/spl-mapping-detail-dialog'
import { SplHistoryDialog } from '@/features/spl-mapping/components/modals/spl-history-dialog'
import { ApiRmsSplFormDialog } from '@/features/spl-mapping/components/modals/api-rms-spl-form-dialog'
import { ApiRmsSplDetailDialog } from '@/features/spl-mapping/components/modals/api-rms-spl-detail-dialog'
import { ApiRmsSplCalibrationDialog } from '@/features/spl-mapping/components/modals/api-rms-spl-calibration-dialog'
import { BatchSplDialog } from '@/features/spl-mapping/components/modals/batch-spl-dialog'
import type { ApiRmsSplMapping } from '@/domain/models/digitalSpl'
import type { SplMapping } from '@/domain/models/splMapping'

const DEFAULT_FILTERS: SplListFilters = {
  search: '',
  calibrationStatus: 'all',
  deviceId: null,
  apiId: null,
}

export function SplMappingPage() {
  const { hasPermission } = usePermissions()
  const canSplRead = hasPermission('spl:read')
  const canSplCreate = hasPermission('spl:create')
  const canSplUpdate = hasPermission('spl:update')
  const canSplDelete = hasPermission('spl:delete')
  const canDigitalRead = hasPermission('digital_spl:read')
  const canDigitalCreate = hasPermission('digital_spl:create')
  const canDigitalUpdate = hasPermission('digital_spl:update')
  const canDigitalDelete = hasPermission('digital_spl:delete')

  const splQuery = useSplMappings()
  const splStatsQuery = useSplStats()
  const playbackDevicesQuery = usePlaybackDeviceRefs()
  const digitalQuery = useDigitalSplMappings()
  const apiRefsQuery = useApiRefs()
  const { remove: removeSpl, calibrate: calibrateSpl } = useSplMutations()
  const {
    remove: removeDigital,
    setDefault: setDefaultDigital,
  } = useDigitalSplMutations()

  const [domain, setDomain] = useState<SplDomain>('device')
  const [filters, setFilters] = useState<SplListFilters>(DEFAULT_FILTERS)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  // 弹窗群
  const [deviceDialog, setDeviceDialog] = useState<DeviceSplDialogState | null>(null)
  const [digitalDialog, setDigitalDialog] = useState<DigitalSplDialogState | null>(null)
  const [batchDialog, setBatchDialog] = useState<BatchSplDialogState | null>(null)
  const [deleteSplTarget, setDeleteSplTarget] = useState<SplMapping | null>(null)
  const [deleteDigitalTarget, setDeleteDigitalTarget] = useState<ApiRmsSplMapping | null>(null)
  const [confirmPending, setConfirmPending] = useState(false)

  const splMappings = splQuery.data ?? []
  const digitalMappings = digitalQuery.data ?? []
  const playbackDevices = playbackDevicesQuery.data ?? []
  const apis = apiRefsQuery.data ?? []

  /* ───────── 过滤 / 排序 / 分页 ───────── */

  const filteredSpl = useMemo(() => {
    let rows = splMappings
    const keyword = filters.search.trim().toLowerCase()
    if (keyword) {
      rows = rows.filter(
        (row) =>
          row.name.toLowerCase().includes(keyword) ||
          (row.description ?? '').toLowerCase().includes(keyword)
      )
    }
    if (filters.calibrationStatus !== 'all') {
      rows = rows.filter((row) => row.calibrationStatus === filters.calibrationStatus)
    }
    if (filters.deviceId) {
      rows = rows.filter((row) => String(row.deviceId) === filters.deviceId)
    }
    return rows
  }, [splMappings, filters])

  const filteredDigital = useMemo(() => {
    let rows = digitalMappings
    const keyword = filters.search.trim().toLowerCase()
    if (keyword) {
      rows = rows.filter((row) => {
        const apiName = apis.find((a) => a.id === row.apiId)?.name ?? ''
        return (
          (row.name ?? '').toLowerCase().includes(keyword) ||
          apiName.toLowerCase().includes(keyword)
        )
      })
    }
    if (filters.calibrationStatus !== 'all') {
      rows = rows.filter((row) => row.calibrationStatus === filters.calibrationStatus)
    }
    if (filters.apiId) {
      rows = rows.filter((row) => String(row.apiId) === filters.apiId)
    }
    return rows
  }, [digitalMappings, apis, filters])

  const sortedSpl = useMemo(() => {
    const rows = [...filteredSpl]
    rows.sort(
      (a, b) => new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime()
    )
    return rows
  }, [filteredSpl])

  const sortedDigital = useMemo(() => {
    const rows = [...filteredDigital]
    rows.sort(
      (a, b) => new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime()
    )
    return rows
  }, [filteredDigital])

  /** 当前域活动行（分页数据源；按域分支以保类型安全） */
  const deviceActiveRows = sortedSpl
  const digitalActiveRows = sortedDigital
  const activeCount = domain === 'device' ? deviceActiveRows.length : digitalActiveRows.length
  const pageCount = Math.max(1, Math.ceil(activeCount / pageSize))
  const safePage = Math.min(page, pageCount)

  const devicePageRows = useMemo(
    () => deviceActiveRows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [deviceActiveRows, safePage, pageSize]
  )
  const digitalPageRows = useMemo(
    () => digitalActiveRows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [digitalActiveRows, safePage, pageSize]
  )

  /* ───────── 统计（§4.1.2） ───────── */

  const deviceStats = useMemo(() => {
    const stats = splStatsQuery.data
    if (!stats) return undefined
    return { total: stats.total, calibrated: stats.calibrated, uncalibrated: stats.uncalibrated, associated: stats.associatedDevices }
  }, [splStatsQuery.data])

  const digitalStats = useMemo(() => {
    const total = digitalMappings.length
    const calibrated = digitalMappings.filter((m) => m.calibrationStatus === 'calibrated').length
    return {
      total,
      calibrated,
      uncalibrated: total - calibrated,
      associated: new Set(digitalMappings.map((m) => m.apiId)).size,
    }
  }, [digitalMappings])

  const currentStats = domain === 'device' ? deviceStats : digitalStats

  const isFiltered =
    filters.search !== '' ||
    filters.calibrationStatus !== 'all' ||
    filters.deviceId != null ||
    filters.apiId != null

  /* ───────── 行操作 ───────── */

  const currentSplMapping = useMemo(() => {
    if (!deviceDialog || deviceDialog.kind === 'create') return null
    return splMappings.find((m) => m.id === deviceDialog.mappingId) ?? null
  }, [deviceDialog, splMappings])

  const currentDigitalMapping = useMemo(() => {
    if (!digitalDialog || digitalDialog.kind === 'create') return null
    return digitalMappings.find((m) => m.id === digitalDialog.mappingId) ?? null
  }, [digitalDialog, digitalMappings])

  /** §4.2.1 执行校准（接线：POST /spl/{id}/calibrate，现状后端为模拟校准，请求体忽略） */
  const handleCalibrateSpl = async (mapping: SplMapping) => {
    try {
      const result = await calibrateSpl.mutateAsync({ id: mapping.id })
      if (result.success) toast.success('校准完成：映射已置为已校准')
      else toast.error(result.message ?? '校准失败，请重试')
    } catch {
      toast.error('校准失败，请重试')
    }
  }

  /** §4.3.1 设默认/清除默认 */
  const handleToggleDefault = async (mapping: ApiRmsSplMapping) => {
    const api = apis.find((a) => a.id === mapping.apiId)
    const isDefault = api?.rmsSplMappingId != null && api.rmsSplMappingId === mapping.id
    try {
      await setDefaultDigital.mutateAsync({
        apiId: mapping.apiId,
        mappingId: isDefault ? null : mapping.id,
      })
      toast.success(isDefault ? '已清除默认映射' : '已设为该 API 的默认映射')
    } catch {
      toast.error('设置默认映射失败，请重试')
    }
  }

  const handleConfirmDeleteSpl = async () => {
    if (!deleteSplTarget) return
    setConfirmPending(true)
    try {
      const result = await removeSpl.mutateAsync(deleteSplTarget.id)
      if (result.success) toast.success('增益映射已删除')
      else toast.error(result.message ?? '删除失败，请重试')
      setDeleteSplTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    } finally {
      setConfirmPending(false)
    }
  }

  const handleConfirmDeleteDigital = async () => {
    if (!deleteDigitalTarget) return
    setConfirmPending(true)
    try {
      const result = await removeDigital.mutateAsync(deleteDigitalTarget.id)
      if (result.success) toast.success('RMS-SPL 映射已删除')
      else toast.error(result.message ?? '删除失败，请重试')
      setDeleteDigitalTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    } finally {
      setConfirmPending(false)
    }
  }

  /* ───────── 页面装配（§4.1 骨架） ───────── */

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            声压级映射管理
            <Badge variant='outline' className='font-normal tabular-nums'>
              已校准 {currentStats?.calibrated ?? '—'}/共 {currentStats?.total ?? '—'}
            </Badge>
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <div className='flex flex-wrap items-center gap-2'>
            {domain === 'device' ? (
              <>
                {canSplUpdate && (
                  <Button
                    variant='outline'
                    size='sm'
                    className='gap-1.5'
                    onClick={() => setBatchDialog({ mappingIds: filteredSpl.map((m) => m.id), count: filteredSpl.length })}
                  >
                    <AudioWaveform aria-hidden='true' className='size-3.5' />
                    批量配置 SPL
                  </Button>
                )}
                {canSplCreate && (
                  <Tooltip>
                    <TooltipTrigger render={<Button variant='outline' size='sm' className='gap-1.5' disabled />}>
                      <UploadCloud aria-hidden='true' className='size-3.5' />
                      导入映射数据
                    </TooltipTrigger>
                    <TooltipContent>映射导入后端建设中</TooltipContent>
                  </Tooltip>
                )}
                {canSplCreate && (
                  <Button size='sm' className='gap-1.5' onClick={() => setDeviceDialog({ kind: 'create' })}>
                    <Plus aria-hidden='true' className='size-3.5' />
                    添加增益映射
                  </Button>
                )}
              </>
            ) : (
              canDigitalCreate && (
                <Button size='sm' className='gap-1.5' onClick={() => setDigitalDialog({ kind: 'create' })}>
                  <Plus aria-hidden='true' className='size-3.5' />
                  添加 RMS-SPL 映射
                </Button>
              )
            )}
          </div>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3'>
            <Tabs value={domain} onValueChange={(value) => setDomain(value as SplDomain)}>
              <TabsList className='w-fit'>
                {DOMAIN_TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            <SplFilterToolbar
              domain={domain}
              filters={filters}
              playbackDevices={playbackDevices}
              apis={apis}
              onChange={(next) => {
                setFilters(next)
                setPage(1)
              }}
              onReset={() => {
                setFilters(DEFAULT_FILTERS)
                setPage(1)
              }}
              isFiltered={isFiltered}
            />

            <SplStatsRow domain={domain} stats={currentStats} />

            <div className='min-h-0 flex-1 overflow-y-auto'>
              {domain === 'device' ? (
                <DeviceSplTable
                  rows={devicePageRows}
                  loading={splQuery.isLoading}
                  searchKeyword={filters.search}
                  canRead={canSplRead}
                  canUpdate={canSplUpdate}
                  canCreate={canSplCreate}
                  canDelete={canSplDelete}
                  onEmptyCreate={() => setDeviceDialog({ kind: 'create' })}
                  onDetail={(mapping) => setDeviceDialog({ kind: 'detail', mappingId: mapping.id })}
                  onEdit={(mapping) => setDeviceDialog({ kind: 'edit', mappingId: mapping.id })}
                  onCalibrate={handleCalibrateSpl}
                  onHistory={(mapping) => setDeviceDialog({ kind: 'history', mappingId: mapping.id })}
                  onDelete={(mapping) => setDeleteSplTarget(mapping)}
                />
              ) : (
                <DigitalSplTable
                  rows={digitalPageRows}
                  apis={apis}
                  loading={digitalQuery.isLoading}
                  searchKeyword={filters.search}
                  canRead={canDigitalRead}
                  canUpdate={canDigitalUpdate}
                  canCreate={canDigitalCreate}
                  canDelete={canDigitalDelete}
                  onEmptyCreate={() => setDigitalDialog({ kind: 'create' })}
                  onDetail={(mapping) => setDigitalDialog({ kind: 'detail', mappingId: mapping.id })}
                  onEdit={(mapping) => setDigitalDialog({ kind: 'edit', mappingId: mapping.id })}
                  onCalibrate={(mapping) => setDigitalDialog({ kind: 'calibrate', mappingId: mapping.id })}
                  onToggleDefault={handleToggleDefault}
                  onDelete={(mapping) => setDeleteDigitalTarget(mapping)}
                />
              )}
            </div>

            <SplSymmetryAlert />

            <PageFooterPortal>
              <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
                <span className='text-muted-foreground tabular-nums'>
                  共 {activeCount} 条
                </span>
                <PaginationBar
                  page={safePage}
                  pageCount={pageCount}
                  pageSize={pageSize}
                  onPageChange={setPage}
                  onPageSizeChange={(size) => {
                    setPageSize(size)
                    setPage(1)
                  }}
                />
              </div>
            </PageFooterPortal>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 物理域弹窗（§6.7-6.9） */}
      <SplMappingFormDialog
        open={deviceDialog?.kind === 'create' || deviceDialog?.kind === 'edit'}
        onOpenChange={(open) => !open && setDeviceDialog(null)}
        mapping={
          deviceDialog?.kind === 'edit' ? currentSplMapping : deviceDialog?.kind === 'create' ? null : null
        }
        playbackDevices={playbackDevices}
      />
      <SplMappingDetailDialog
        open={deviceDialog?.kind === 'detail'}
        onOpenChange={(open) => !open && setDeviceDialog(null)}
        mapping={deviceDialog?.kind === 'detail' ? currentSplMapping : null}
        onViewHistory={(mapping) => setDeviceDialog({ kind: 'history', mappingId: mapping.id })}
      />
      <SplHistoryDialog
        open={deviceDialog?.kind === 'history'}
        onOpenChange={(open) => !open && setDeviceDialog(null)}
        mappingId={deviceDialog?.kind === 'history' ? deviceDialog.mappingId : null}
      />

      {/* 数字域弹窗（§6.10-6.12） */}
      <ApiRmsSplFormDialog
        open={digitalDialog?.kind === 'create' || digitalDialog?.kind === 'edit'}
        onOpenChange={(open) => !open && setDigitalDialog(null)}
        mapping={digitalDialog?.kind === 'edit' ? currentDigitalMapping : null}
        apis={apis}
      />
      <ApiRmsSplDetailDialog
        open={digitalDialog?.kind === 'detail'}
        onOpenChange={(open) => !open && setDigitalDialog(null)}
        mapping={digitalDialog?.kind === 'detail' ? currentDigitalMapping : null}
        apis={apis}
      />
      <ApiRmsSplCalibrationDialog
        open={digitalDialog?.kind === 'calibrate'}
        onOpenChange={(open) => !open && setDigitalDialog(null)}
        mapping={digitalDialog?.kind === 'calibrate' ? currentDigitalMapping : null}
      />

      {/* 批量 SPL 配置（§6.22） */}
      <BatchSplDialog
        open={batchDialog != null}
        onOpenChange={(open) => !open && setBatchDialog(null)}
        mappings={filteredSpl}
        count={batchDialog?.count ?? filteredSpl.length}
      />

      {/* 删除确认（§4.2.1 / §4.3.1） */}
      <ConfirmDialog
        open={deleteSplTarget != null}
        onOpenChange={(open) => !open && setDeleteSplTarget(null)}
        title='删除增益映射'
        desc='确定要删除此映射吗？此操作不可撤销。'
        destructive
        confirmText='删除'
        isLoading={confirmPending}
        handleConfirm={handleConfirmDeleteSpl}
      />
      <ConfirmDialog
        open={deleteDigitalTarget != null}
        onOpenChange={(open) => !open && setDeleteDigitalTarget(null)}
        title='删除 RMS-SPL 映射'
        desc={
          deleteDigitalTarget
            ? `确定要删除映射「${deleteDigitalTarget.name || `#${deleteDigitalTarget.id}`}」吗？此操作不可撤销。`
            : ''
        }
        destructive
        confirmText='删除'
        isLoading={confirmPending}
        handleConfirm={handleConfirmDeleteDigital}
      />
    </>
  )
}

/* ───────────────────────── 分页条（§3.9 DataTablePagination 对位） ───────────────────────── */

function PaginationBar({
  page,
  pageCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  page: number
  pageCount: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}) {
  return (
    <div className='flex flex-wrap items-center gap-2 text-sm'>
      <Select
        value={String(pageSize)}
        onValueChange={(value) => onPageSizeChange(Number(value ?? DEFAULT_PAGE_SIZE))}
      >
        <SelectTrigger size='sm' className='w-24' aria-label='每页条数'>
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
        <Button
          variant='outline'
          size='sm'
          aria-label='第一页'
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
        >
          <ChevronsLeft aria-hidden='true' className='size-3.5' />
        </Button>
        <Button
          variant='outline'
          size='sm'
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          上一页
        </Button>
        <span className='text-muted-foreground px-1 tabular-nums'>
          {page} / {pageCount}
        </span>
        <Button
          variant='outline'
          size='sm'
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
        </Button>
        <Button
          variant='outline'
          size='sm'
          aria-label='最后一页'
          disabled={page >= pageCount}
          onClick={() => onPageChange(pageCount)}
        >
          <ChevronsRight aria-hidden='true' className='size-3.5' />
        </Button>
      </div>
    </div>
  )
}
