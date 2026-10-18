/**
 * 权限矩阵（interfaces 层，对位 newAPI permission-matrix 实测形态）：
 * 22 模块分组 Collapsible（默认全展开），每组头「模块名 + 已选 x/y Badge + 全选/清空」；
 * 资源行 = 权限点 Checkbox + Tooltip（权限码 + 中文描述）；通配 * 行禁用 +
 * Tooltip「通配权限不可单独授予或收回」（WILDCARD_FORBIDDEN 实测约束）。
 * 角色详情/用户抽屉共用本组件；admin 角色特例整块禁用。
 */
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ChevronRight, CircleX, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

import type { PermissionModule } from '@/domain/models/permission'
import { PERMISSION_CATALOG } from '@/domain/models/permission'

export const WILDCARD_PERMISSION = '*'

type PermissionMatrixProps = {
  /** 已选权限码集合 */
  value: string[]
  onChange: (codes: string[]) => void
  /** 整块禁用（admin 特例 / 只读角色详情） */
  disabled?: boolean
  /** 禁用原因说明（如「超级管理员持有全部权限（通配），不可修改」） */
  disabledReason?: string
  /** 顶部说明文案（用户抽屉节文案） */
  description?: string
  permissionModules?: PermissionModule[]
}

export function PermissionMatrix(props: PermissionMatrixProps) {
  // 目录缺省取全量 22 模块（矩阵行按角色 permissions 渲染）
  const modules = props.permissionModules ?? PERMISSION_CATALOG

  const togglePermission = (code: string) => {
    if (props.disabled || code === WILDCARD_PERMISSION) return
    const next = new Set(props.value)
    if (next.has(code)) {
      next.delete(code)
    } else {
      next.add(code)
    }
    props.onChange([...next])
  }

  const selectAllInModule = (module: PermissionModule) => {
    if (props.disabled) return
    const codes = module.permissions.map((p) => p.code)
    const next = new Set(props.value)
    codes.forEach((code) => next.add(code))
    props.onChange([...next])
  }

  const clearModule = (module: PermissionModule) => {
    if (props.disabled) return
    const codes = new Set(module.permissions.map((p) => p.code))
    props.onChange(props.value.filter((code) => !codes.has(code)))
  }

  return (
    <TooltipProvider delay={100}>
      <div className={cn('flex flex-col gap-3', props.disabled && 'opacity-70')}>
        {props.description && (
          <p className='text-muted-foreground text-xs'>{props.description}</p>
        )}
        {props.disabled && props.disabledReason && (
          <p className='text-muted-foreground rounded-lg bg-muted/40 px-3 py-2 text-xs'>
            {props.disabledReason}
          </p>
        )}
        <div className='flex flex-col gap-2'>
          {modules.map((module) => {
            const moduleCodes = module.permissions.map((p) => p.code)
            const selectedCount = moduleCodes.filter((code) =>
              props.value.includes(code)
            ).length
            return (
              <Collapsible
                key={module.id}
                defaultOpen
                className='group/module'
                disabled={props.disabled}
              >
                <div
                  className={cn(
                    'border-border/70 hover:bg-muted/50 flex w-full items-center gap-2 rounded-lg border px-3 py-2',
                    props.disabled && 'cursor-not-allowed'
                  )}
                >
                  <CollapsibleTrigger className='group/trigger flex min-w-0 flex-1 items-center gap-2 rounded-lg text-left'>
                    <ChevronRight className='size-4 shrink-0 transition-transform duration-200 group-data-[panel-open]/module:rotate-90' />
                    <span className='min-w-0 flex-1 truncate text-sm font-medium'>
                      {module.name}
                    </span>
                    <Badge variant='secondary' className='shrink-0'>
                      已选 {selectedCount}/{moduleCodes.length}
                    </Badge>
                  </CollapsibleTrigger>
                  <span className='flex shrink-0 items-center gap-1'>
                    <Button
                      type='button'
                      variant='ghost'
                      size='sm'
                      className='h-6 px-1.5 text-xs'
                      disabled={props.disabled}
                      onClick={() => selectAllInModule(module)}
                    >
                      <Check className='size-3' aria-hidden='true' />
                      全选
                    </Button>
                    <Button
                      type='button'
                      variant='ghost'
                      size='sm'
                      className='h-6 px-1.5 text-xs'
                      disabled={props.disabled}
                      onClick={() => clearModule(module)}
                    >
                      <CircleX className='size-3' aria-hidden='true' />
                      清空
                    </Button>
                  </span>
                </div>
                <CollapsibleContent>
                  <div className='mt-1 flex flex-col gap-1 pl-6'>
                    {module.permissions.map((permission) => {
                      const isWildcard = permission.code === WILDCARD_PERMISSION
                      const isChecked = props.value.includes(permission.code)
                      const isDisabled = props.disabled || isWildcard
                      return (
                        <div key={permission.code} className='flex items-center gap-2 py-1'>
                          <Checkbox
                            id={`perm-${permission.code}`}
                            checked={isChecked}
                            disabled={isDisabled}
                            onCheckedChange={() => togglePermission(permission.code)}
                          />
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <label
                                  htmlFor={`perm-${permission.code}`}
                                  className='text-sm'
                                />
                              }
                            >
                              {permission.name}
                            </TooltipTrigger>
                            <TooltipContent>
                              <span className='font-mono text-xs'>{permission.code}</span>
                              <span className='text-muted-foreground ml-1 text-xs'>
                                {isWildcard
                                  ? '通配权限不可单独授予或收回'
                                  : permission.name}
                              </span>
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      )
                    })}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )
          })}
        </div>
      </div>
    </TooltipProvider>
  )
}
