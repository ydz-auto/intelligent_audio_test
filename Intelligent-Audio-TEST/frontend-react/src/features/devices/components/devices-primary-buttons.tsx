/**
 * 设备管理页页头动作区（16_设备域.md §3.3；channels-primary-buttons 对位）。
 * 三开关（批量操作模式/监控告警面板/ID 排序）+ 主按钮（随页签「添加测试设备/添加播放设备/
 * 添加测试API」）+ 更多操作下拉（扫描设备/分组管理/实验室管理/批量健康检查/导入导出）。
 * 权限：主按钮随页签 device:create/playback:create/api_config:create，无权限 disabled +
 * Tooltip「无权限执行此操作」；菜单项按码显隐（§8 隐藏而非置灰）。
 * INT-487：实验室管理入口后端 /api/laboratories 未实现 → 禁用 + Tooltip「实验室管理后端建设中」；
 * 导入/导出无处理器（§11-21）→ 禁用 + Tooltip「设备导入导出后端建设中」。
 */
import {
  Bell,
  Boxes,
  Building2,
  Download,
  ListChecks,
  MoreHorizontal,
  Plus,
  ScanLine,
  SortAsc,
  Stethoscope,
  Upload,
  type LucideIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { DEVICES_ADD_BUTTON_LABEL, type DevicesTabKey } from '@/features/devices/constants'
import type { DeviceHeaderToggles } from '@/features/devices/types'

export interface DevicesPrimaryButtonsProps {
  tab: DevicesTabKey
  toggles: DeviceHeaderToggles
  onTogglesChange: (next: DeviceHeaderToggles) => void
  canCreate: boolean
  canControl: boolean
  canGroupManage: boolean
  canLabManage: boolean
  onAdd: () => void
  onScan: () => void
  onGroupManage: () => void
  onLabManage: () => void
  onBatchHealth: () => void
  onImport: () => void
  onExport: () => void
}

/** 开关项（§3.3 三开关；移动端整组进「更多操作」CheckboxItem） */
function HeaderSwitch({
  icon: Icon,
  label,
  checked,
  onCheckedChange,
  hiddenMobile,
}: {
  icon: LucideIcon
  label: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  hiddenMobile?: boolean
}) {
  return (
    <span
      className={cn(
        'flex items-center gap-1.5 text-sm',
        hiddenMobile && 'hidden sm:flex'
      )}
    >
      <Icon aria-hidden='true' className='text-muted-foreground size-3.5' />
      <Label className='text-muted-foreground text-xs font-normal'>{label}</Label>
      <Switch
        size='sm'
        checked={checked}
        onCheckedChange={(next) => onCheckedChange(next)}
        aria-label={label}
      />
    </span>
  )
}

export function DevicesPrimaryButtons(props: DevicesPrimaryButtonsProps) {
  const { tab, toggles, canCreate } = props

  return (
    <div className='flex flex-wrap items-center gap-2'>
      {/* 三开关（§3.3：hidden sm:flex items-center gap-2 rounded-md border px-3 py-1.5） */}
      <span className='hidden items-center gap-2 rounded-md border px-3 py-1.5 sm:flex'>
        <HeaderSwitch
          icon={ListChecks}
          label='批量操作模式'
          checked={toggles.batchMode}
          onCheckedChange={(batchMode) => props.onTogglesChange({ ...toggles, batchMode })}
        />
        {tab === 'test' && (
          <HeaderSwitch
            icon={Bell}
            label='监控告警面板'
            checked={toggles.alarmsOpen}
            onCheckedChange={(alarmsOpen) => props.onTogglesChange({ ...toggles, alarmsOpen })}
          />
        )}
        <HeaderSwitch
          icon={SortAsc}
          label='ID 排序'
          checked={toggles.idSort}
          onCheckedChange={(idSort) => props.onTogglesChange({ ...toggles, idSort })}
        />
      </span>

      {/* 主按钮（§3.3：文案随页签；无权限 disabled + Tooltip） */}
      {canCreate ? (
        <Button size='sm' className='gap-1.5' onClick={props.onAdd}>
          <Plus aria-hidden='true' className='size-3.5' />
          {DEVICES_ADD_BUTTON_LABEL[tab]}
        </Button>
      ) : (
        <Tooltip>
          <TooltipTrigger render={<Button size='sm' className='gap-1.5' disabled />}>
            <Plus aria-hidden='true' className='size-3.5' />
            {DEVICES_ADD_BUTTON_LABEL[tab]}
          </TooltipTrigger>
          <TooltipContent>无权限执行此操作</TooltipContent>
        </Tooltip>
      )}

      {/* 更多操作（§3.3 w-56） */}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant='outline' size='icon-sm' aria-label='更多操作' />}
        >
          <MoreHorizontal aria-hidden='true' />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end' className='w-56'>
          {/* 移动端三开关（§3.3：sm:hidden 进下拉 CheckboxItem） */}
          <div className='flex flex-col gap-0.5 sm:hidden'>
            <DropdownMenuCheckboxItem
              checked={toggles.batchMode}
              onCheckedChange={(batchMode) => props.onTogglesChange({ ...toggles, batchMode })}
            >
              <ListChecks aria-hidden='true' />
              批量操作模式
            </DropdownMenuCheckboxItem>
            {tab === 'test' && (
              <DropdownMenuCheckboxItem
                checked={toggles.alarmsOpen}
                onCheckedChange={(alarmsOpen) => props.onTogglesChange({ ...toggles, alarmsOpen })}
              >
                <Bell aria-hidden='true' />
                监控告警面板
              </DropdownMenuCheckboxItem>
            )}
            <DropdownMenuCheckboxItem
              checked={toggles.idSort}
              onCheckedChange={(idSort) => props.onTogglesChange({ ...toggles, idSort })}
            >
              <SortAsc aria-hidden='true' />
              ID 排序
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
          </div>

          {props.canControl && tab !== 'api' && (
            <DropdownMenuItem onClick={props.onScan}>
              <ScanLine aria-hidden='true' />
              扫描设备
            </DropdownMenuItem>
          )}
          {props.canGroupManage && tab === 'test' && (
            <DropdownMenuItem onClick={props.onGroupManage}>
              <Boxes aria-hidden='true' />
              分组管理
            </DropdownMenuItem>
          )}
          {/* 实验室管理（§3.3/§6.26：三页签均显；INT-487 后端未实现 → 禁用 + Tooltip） */}
          {props.canLabManage && (
            <DropdownMenuItem disabled title='实验室管理后端建设中'>
              <Building2 aria-hidden='true' />
              实验室管理
            </DropdownMenuItem>
          )}
          {props.canControl && (
            <DropdownMenuItem onClick={props.onBatchHealth}>
              <Stethoscope aria-hidden='true' />
              批量健康检查
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          {/* 导入/导出（§3.3/§11-21：现状无处理器 → 禁用 + Tooltip） */}
          {props.canCreate && (
            <DropdownMenuItem disabled title='设备导入导出后端建设中'>
              <Upload aria-hidden='true' />
              导入设备
            </DropdownMenuItem>
          )}
          {props.canCreate && (
            <DropdownMenuItem disabled title='设备导入导出后端建设中'>
              <Download aria-hidden='true' />
              导出设备
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
