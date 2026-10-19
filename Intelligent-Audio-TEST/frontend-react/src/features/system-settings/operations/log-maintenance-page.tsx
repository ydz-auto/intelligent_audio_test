/**
 * 日志维护分区（interfaces 层，INT-347 §4.7 定稿）：
 * 三段——保留天数（母版 A KV 保存链）/ 立即清理（ConfirmDialog destructive，
 * log:manage）/ 归档管理小节（状态卡 + 归档列表 + 立即归档 + 删除归档，
 * 与保留天数保存链解耦）。权限口径：log:read=查看/归档列表/下载、log:manage=写操作。
 */
import { Download, HardDrive, Trash2, Archive } from 'lucide-react'
import { useMemo, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useLogArchiveMutations, useArchiveItemsQuery, useArchiveStatusQuery } from '@/application/operations/use-log-archive'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { archiveFileCount, formatBytes } from '@/domain/models/log-archive'
import type { LogMaintenanceSettings } from '@/domain/models/option'

import { SettingsFormGrid, SettingsFormGridItem } from '../components/settings-form-layout'
import { SettingsFormPage } from '../components/settings-form-page'
import { SettingsSection } from '../components/settings-section'
import { StaticDataTable, type StaticDataTableColumn } from '../components/static-data-table'

type LogMaintenancePageProps = {
  defaultValues: LogMaintenanceSettings
}

export function LogMaintenancePage({ defaultValues }: LogMaintenancePageProps) {
  const { hasPermission } = usePermissions()
  const canManage = hasPermission('log:manage')
  const archiveStatus = useArchiveStatusQuery()
  const archiveItems = useArchiveItemsQuery()
  const { archiveNow, deleteArchive, clearLogs, downloadArchive } = useLogArchiveMutations()
  const [clearOpen, setClearOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const columns = useMemo<Array<StaticDataTableColumn<{ filename: string; archivedAt: string; sizeBytes: number }>>>(
    () => [
      { key: 'filename', header: '归档文件名', render: (row) => <span className='font-mono text-xs'>{row.filename}</span> },
      { key: 'archivedAt', header: '归档时间', render: (row) => <span className='text-muted-foreground font-mono text-xs'>{row.archivedAt.slice(0, 10)}</span> },
      { key: 'size', header: '大小', render: (row) => <span className='font-mono text-xs'>{formatBytes(row.sizeBytes)}</span> },
    ],
    []
  )

  return (
    <>
      <SettingsFormPage<LogMaintenanceSettings>
        baseline={defaultValues}
        optionKey={() => 'operations.log_retention_days'}
      >
        {(draft, setField) => (
          <SettingsFormGrid>
            <SettingsFormGridItem className='grid gap-1.5'>
              <Label htmlFor='log-retention-days'>日志保留天数</Label>
              <div className='flex items-center gap-2'>
                <Input
                  id='log-retention-days'
                  type='number'
                  min={1}
                  className='w-40'
                  value={String(draft.retentionDays)}
                  onChange={(event) =>
                    setField('retentionDays', Number(event.target.value))
                  }
                />
                <span className='text-muted-foreground text-xs'>天</span>
              </div>
              <p className='text-muted-foreground text-xs'>超过保留期的系统日志自动清理</p>
            </SettingsFormGridItem>
            <SettingsFormGridItem className='grid gap-1.5'>
              <div className='min-h-8' />
              {canManage && (
                <div>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    onClick={() => setClearOpen(true)}
                  >
                    <Trash2 data-icon='inline-start' />
                    立即清理
                  </Button>
                </div>
              )}
            </SettingsFormGridItem>
          </SettingsFormGrid>
        )}
      </SettingsFormPage>

      {/* 归档管理小节（与保留天数 KV 保存链解耦） */}
      <SettingsSection title='归档管理' description='管理日志归档状态、归档文件与归档操作'>
        <div className='grid gap-4 lg:grid-cols-2'>
          <div className='bg-muted/20 flex flex-col gap-2 rounded-xl border p-4'>
            <div className='text-muted-foreground flex items-center gap-2 text-xs font-medium'>
              <HardDrive className='size-3.5' aria-hidden='true' />
              归档状态
            </div>
            {archiveStatus.isLoading ? (
              <div className='text-muted-foreground text-sm'>正在加载…</div>
            ) : archiveStatus.data ? (
              <div className='flex flex-wrap items-center gap-x-6 gap-y-2 text-sm'>
                <div>
                  <div className='text-muted-foreground text-xs'>归档文件数</div>
                  <div className='font-medium tabular-nums'>
                    {archiveFileCount(archiveStatus.data)}
                  </div>
                </div>
                <div>
                  <div className='text-muted-foreground text-xs'>归档状态</div>
                  <StatusBadge
                    label={archiveFileCount(archiveStatus.data) > 0 ? '已归档' : '未归档'}
                    variant={archiveFileCount(archiveStatus.data) > 0 ? 'success' : 'neutral'}
                  />
                </div>
                <div>
                  <div className='text-muted-foreground text-xs'>冷数据量</div>
                  <div className='font-medium tabular-nums'>
                    {archiveStatus.data.coldLogs.toLocaleString()}
                  </div>
                </div>
                <div className='text-muted-foreground text-xs'>
                  任务 {archiveStatus.data.taskArchives.toLocaleString()} · 用例{' '}
                  {archiveStatus.data.caseArchives.toLocaleString()} · 其他{' '}
                  {archiveStatus.data.otherArchives.toLocaleString()}
                </div>
              </div>
            ) : null}
            {canManage && (
              <div>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  onClick={() => setArchiveOpen(true)}
                  disabled={archiveNow.isPending}
                >
                  <Archive data-icon='inline-start' />
                  立即归档
                </Button>
              </div>
            )}
          </div>

          <div className='flex flex-col gap-2 overflow-hidden rounded-xl border'>
            <div className='text-muted-foreground border-b px-4 py-2.5 text-xs font-medium'>
              归档列表
            </div>
            <div className='px-1'>
              <StaticDataTable
                columns={columns}
                rows={archiveItems.data ?? []}
                rowKey={(row) => row.filename}
                emptyText='暂无归档（待 INT-780）'
                emptyDescription='后端全局归档文件清单接口待 FEAT 卡 INT-780 落地，归档统计见左侧状态卡'
                minWidth='480px'
                actions={
                  canManage
                    ? (row) => (
                        <div className='flex justify-end gap-1'>
                          <Button type='button' variant='ghost' size='icon' className='size-7' onClick={() => downloadArchive.mutate(row.filename)}>
                            <Download className='size-3.5' aria-hidden='true' />
                            <span className='sr-only'>下载</span>
                          </Button>
                          <Button
                            type='button'
                            variant='ghost'
                            size='icon'
                            className='size-7'
                            onClick={() => setDeleteTarget(row.filename)}
                          >
                            <Trash2 className='text-destructive size-3.5' aria-hidden='true' />
                            <span className='sr-only'>删除归档</span>
                          </Button>
                        </div>
                      )
                    : undefined
                }
              />
            </div>
          </div>
        </div>
      </SettingsSection>

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title='立即清理日志'
        desc='将删除保留期之前的全部日志，此操作不可恢复。'
        destructive
        cancelBtnText='取消'
        confirmText='确认清理'
        handleConfirm={() => {
          setClearOpen(false)
          clearLogs.mutate()
        }}
      />
      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title='立即归档'
        desc='将当前日志归档至 OSS，确定吗？'
        cancelBtnText='取消'
        confirmText='确认归档'
        isLoading={archiveNow.isPending}
        handleConfirm={() => {
          setArchiveOpen(false)
          archiveNow.mutate()
        }}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title='确认删除归档'
        desc={deleteTarget ? `确认删除归档「${deleteTarget}」？此操作不可恢复。` : ''}
        destructive
        cancelBtnText='取消'
        confirmText='删除'
        isLoading={deleteArchive.isPending}
        handleConfirm={() => {
          if (deleteTarget) deleteArchive.mutate(deleteTarget)
          setDeleteTarget(null)
        }}
      />
    </>
  )
}
