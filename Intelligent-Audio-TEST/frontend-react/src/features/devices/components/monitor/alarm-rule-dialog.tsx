/**
 * 监控告警规则管理弹窗（16_设备域.md §6.6；Dialog sm:max-w-xl）。
 * 工具行「+ 新建规则」（device:update）；规则 StaticDataTable（名称/指标中文/阈值带单位/级别
 * Badge/邮件 Switch态/启用 Switch态/操作[编辑·删除]）；新建/编辑小表单（规则名称（必填）/告警指标
 * select[离线时长·连续健康检查失败次数·CPU使用率·内存使用率·电量]/阈值（必填，battery 标注
 * 「电量低于该值时告警」）/级别 select[提示·警告·严重]/邮件通知 switch/启用 switch）。
 * 数据 GET /alarm-rules（list 实测 min(per_page,500)）；删除 ConfirmDialog。
 * 现状 cpu/memory/battery 三指标驱动多数未上报→无数据不评估（§11-2）。
 */
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

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
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { StaticDataTable } from '@/features/system-settings/components/static-data-table'
import { cn } from '@/lib/utils'
import type { AlarmRule } from '@/domain/models/alarm'
import {
  ALARM_METRIC_META,
  ALARM_SEVERITY_META,
  type AlarmMetricType,
  type AlarmSeverity,
} from '@/domain/models/alarm'
import { useAlarmRuleMutations } from '@/application/devices/use-devices'

const METRIC_OPTIONS: ReadonlyArray<{ value: AlarmMetricType; label: string }> = [
  { value: 'offline_duration', label: '离线时长' },
  { value: 'health_check_failures', label: '连续健康检查失败次数' },
  { value: 'cpu', label: 'CPU 使用率' },
  { value: 'memory', label: '内存使用率' },
  { value: 'battery', label: '电量' },
]

const SEVERITY_OPTIONS: ReadonlyArray<{ value: AlarmSeverity; label: string }> = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
]

interface RuleForm {
  name: string
  metricType: AlarmMetricType
  thresholdValue: string
  severity: AlarmSeverity
  notifyEmail: boolean
  enabled: boolean
}

const EMPTY_FORM: RuleForm = {
  name: '',
  metricType: 'offline_duration',
  thresholdValue: '30',
  severity: 'warning',
  notifyEmail: true,
  enabled: true,
}

export function AlarmRuleDialog({
  open,
  onOpenChange,
  rules,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  rules: AlarmRule[]
}) {
  const { save, remove } = useAlarmRuleMutations()
  const [editing, setEditing] = useState<AlarmRule | null>(null)
  const [form, setForm] = useState<RuleForm>(EMPTY_FORM)
  const [deleteTarget, setDeleteTarget] = useState<AlarmRule | null>(null)
  const [saving, setSaving] = useState(false)

  // 每次打开重置
  useEffect(() => {
    if (open) {
      setEditing(null)
      setForm(EMPTY_FORM)
      setDeleteTarget(null)
    }
  }, [open])

  const startCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
  }

  const startEdit = (rule: AlarmRule) => {
    setEditing(rule)
    setForm({
      name: rule.name,
      metricType: rule.metricType,
      thresholdValue: String(rule.thresholdValue),
      severity: rule.severity,
      notifyEmail: rule.notifyEmail,
      enabled: rule.enabled,
    })
  }

  const handleSave = async () => {
    if (!form.name.trim() || form.thresholdValue === '') {
      toast.error('请填写规则名称与阈值')
      return
    }
    setSaving(true)
    try {
      await save.mutateAsync({
        id: editing?.id,
        name: form.name.trim(),
        metricType: form.metricType,
        thresholdValue: Number(form.thresholdValue),
        severity: form.severity,
        notifyEmail: form.notifyEmail,
        enabled: form.enabled,
      })
      toast.success(editing ? '告警规则已更新' : '告警规则已创建')
      setEditing(null)
      setForm(EMPTY_FORM)
    } catch {
      toast.error('操作失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await remove.mutateAsync(deleteTarget.id)
      toast.success('告警规则已删除')
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  const metricUnit = ALARM_METRIC_META[form.metricType].unit

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='sm:max-w-xl'>
          <DialogHeader>
            <DialogTitle>监控告警规则</DialogTitle>
            <DialogDescription>配置设备告警的指标、阈值与通知方式。</DialogDescription>
          </DialogHeader>

          <div className='flex flex-col gap-3'>
            <div className='flex items-center justify-between'>
              <Button variant='outline' size='sm' className='gap-1' onClick={startCreate}>
                <Plus aria-hidden='true' className='size-3.5' />
                新建规则
              </Button>
            </div>

            {/* 新建/编辑小表单（恒显：editing 为空即新建态） */}
            <div className='bg-card/50 flex flex-col gap-2.5 rounded-lg border p-3'>
                <div className='grid grid-cols-2 gap-2.5'>
                  <div className='flex flex-col gap-1'>
                    <Label htmlFor='rule-name'>规则名称</Label>
                    <Input
                      id='rule-name'
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder='如：离线超时告警'
                      className='h-8'
                    />
                  </div>
                  <div className='flex flex-col gap-1'>
                    <Label htmlFor='rule-metric'>告警指标</Label>
                    <Select
                      value={form.metricType}
                      onValueChange={(value) =>
                        setForm({ ...form, metricType: value as AlarmMetricType })
                      }
                    >
                      <SelectTrigger id='rule-metric' size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {METRIC_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className='grid grid-cols-2 gap-2.5'>
                  <div className='flex flex-col gap-1'>
                    <Label htmlFor='rule-threshold'>
                      阈值（{metricUnit}
                      {form.metricType === 'battery' ? '，电量低于该值时告警' : ''}）
                    </Label>
                    <Input
                      id='rule-threshold'
                      type='number'
                      value={form.thresholdValue}
                      onChange={(e) => setForm({ ...form, thresholdValue: e.target.value })}
                      className='h-8'
                    />
                  </div>
                  <div className='flex flex-col gap-1'>
                    <Label htmlFor='rule-severity'>告警级别</Label>
                    <Select
                      value={form.severity}
                      onValueChange={(value) =>
                        setForm({ ...form, severity: value as AlarmSeverity })
                      }
                    >
                      <SelectTrigger id='rule-severity' size='sm' className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SEVERITY_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className='flex items-center gap-4'>
                  <label className='flex items-center gap-2 text-sm'>
                    <Switch
                      size='sm'
                      checked={form.notifyEmail}
                      onCheckedChange={(notifyEmail) => setForm({ ...form, notifyEmail })}
                    />
                    <span>邮件通知</span>
                  </label>
                  <label className='flex items-center gap-2 text-sm'>
                    <Switch
                      size='sm'
                      checked={form.enabled}
                      onCheckedChange={(enabled) => setForm({ ...form, enabled })}
                    />
                    <span>启用</span>
                  </label>
                </div>
                <div className='flex justify-end gap-2'>
                  {editing && (
                    <Button variant='ghost' size='sm' onClick={startCreate}>
                      取消编辑
                    </Button>
                  )}
                  <Button size='sm' className='gap-1' disabled={saving} onClick={() => void handleSave()}>
                    {editing ? '保存修改' : '创建规则'}
                  </Button>
                </div>
            </div>

            {/* 规则 StaticDataTable（P3-27 返修：复用 StaticDataTable） */}
            <StaticDataTable
              columns={[
                {
                  key: 'name',
                  header: '名称',
                  className: 'max-w-40',
                  render: (rule: AlarmRule) => (
                    <span className='min-w-0 block truncate'>{rule.name}</span>
                  ),
                },
                {
                  key: 'metric',
                  header: '指标',
                  render: (rule: AlarmRule) => ALARM_METRIC_META[rule.metricType].label,
                },
                {
                  key: 'threshold',
                  header: '阈值',
                  className: 'text-right font-mono tabular-nums',
                  render: (rule: AlarmRule) =>
                    `${rule.thresholdValue} ${ALARM_METRIC_META[rule.metricType].unit}`,
                },
                {
                  key: 'severity',
                  header: '级别',
                  render: (rule: AlarmRule) => {
                    const severity = ALARM_SEVERITY_META[rule.severity]
                    return (
                      <Badge
                        variant='outline'
                        className={cn(
                          'rounded-sm px-1 font-normal',
                          severity.tone === 'destructive' && 'text-destructive border-destructive/40 bg-destructive/10',
                          severity.tone === 'warning' && 'text-warning border-warning/40 bg-warning/10',
                          severity.tone === 'info' && 'text-info border-info/40 bg-info/10'
                        )}
                      >
                        {severity.label}
                      </Badge>
                    )
                  },
                },
                {
                  key: 'email',
                  header: '邮件',
                  className: 'text-center',
                  render: (rule: AlarmRule) => (
                    <Switch
                      size='sm'
                      checked={rule.notifyEmail}
                      onCheckedChange={(notifyEmail) =>
                        void save.mutateAsync({ ...rule, notifyEmail })
                      }
                      aria-label={`${rule.name} 邮件通知`}
                    />
                  ),
                },
                {
                  key: 'enabled',
                  header: '启用',
                  className: 'text-center',
                  render: (rule: AlarmRule) => (
                    <Switch
                      size='sm'
                      checked={rule.enabled}
                      onCheckedChange={(enabled) =>
                        void save.mutateAsync({ ...rule, enabled })
                      }
                      aria-label={`${rule.name} 启用`}
                    />
                  ),
                },
              ]}
              rows={rules}
              rowKey={(rule) => String(rule.id)}
              emptyText='暂无告警规则'
              minWidth='560px'
              actions={(rule) => (
                <span className='flex items-center justify-end gap-1'>
                  <Button variant='ghost' size='sm' className='h-6 px-1.5 text-xs' onClick={() => startEdit(rule)}>
                    编辑
                  </Button>
                  <Button
                    variant='ghost'
                    size='icon-sm'
                    className='size-6 text-destructive'
                    aria-label={`删除规则 ${rule.name}`}
                    onClick={() => setDeleteTarget(rule)}
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                  </Button>
                </span>
              )}
            />
          </div>

          <DialogFooter>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除告警规则'
        desc={deleteTarget ? `确定要删除告警规则「${deleteTarget.name}」吗？此操作不可撤销。` : ''}
        destructive
        confirmText='删除'
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}
