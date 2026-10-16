/**
 * 个人信息卡（13_个人中心.md §3.4）：对位 newAPI ProfileSettingsCard 卡片形态，
 * 内容为只读信息行（无保存链，后端无自助改资料端点）+ 权限概览 Popover（§3.4.1）。
 */
import { ChevronRight, Settings } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import { useCurrentUser } from '@/application/profile/use-current-user'
import { CopyButton } from '@/components/copy-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import {
  COPY_USER_ID_ARIA,
  COPY_USER_ID_TOAST,
  EMAIL_PENDING_TOOLTIP,
  EMAIL_PENDING_VALUE,
  PERMISSION_POPOVER_DESCRIPTION,
  PERMISSION_POPOVER_TITLE,
  PERMISSION_WILDCARD_COPY,
  PERSONAL_INFO_DESCRIPTION,
  PERSONAL_INFO_FOOTNOTE,
  PERSONAL_INFO_TITLE,
} from '../constants'
import { TitledCard } from './titled-card'

/** 权限码按模块前缀分组（§3.4.1）：{模块}（{n}）组头 + 码列表，去重排序 */
function groupPermissions(permissions: string[]): Array<{
  module: string
  codes: string[]
}> {
  const groups = new Map<string, Set<string>>()
  for (const code of permissions) {
    const module = code.includes(':') ? code.split(':')[0] : code
    const set = groups.get(module) ?? new Set<string>()
    set.add(code)
    groups.set(module, set)
  }
  return [...groups.entries()]
    .map(([module, codes]) => ({
      module,
      codes: [...codes].sort(),
    }))
    .sort((a, b) => a.module.localeCompare(b.module))
}

function PermissionPopover({ permissions }: { permissions: string[] }) {
  const groups = useMemo(() => groupPermissions(permissions), [permissions])
  const isWildcard = permissions.includes('*')

  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type='button'
            className='flex items-center gap-1 rounded-md transition-colors hover:text-primary'
            aria-label='查看权限清单'
          />
        }
      >
        <Badge variant='secondary' className='tabular-nums'>
          {permissions.length} 项权限
        </Badge>
        <ChevronRight aria-hidden='true' className='text-muted-foreground size-3.5' />
      </PopoverTrigger>
      <PopoverContent className='w-72' align='end'>
        <PopoverHeader>
          <PopoverTitle>{PERMISSION_POPOVER_TITLE}</PopoverTitle>
          <PopoverDescription>{PERMISSION_POPOVER_DESCRIPTION}</PopoverDescription>
        </PopoverHeader>
        {isWildcard ? (
          <p className='text-sm'>{PERMISSION_WILDCARD_COPY}</p>
        ) : (
          <div className='grid max-h-72 gap-2 overflow-y-auto'>
            {groups.map((group) => (
              <div key={group.module} className='grid gap-1'>
                <p className='text-muted-foreground text-xs font-medium'>
                  {group.module}（{group.codes.length}）
                </p>
                <div className='flex flex-wrap gap-1'>
                  {group.codes.map((code) => (
                    <code
                      key={code}
                      className='bg-muted text-foreground rounded-md px-1.5 py-0.5 font-mono text-xs'
                    >
                      {code}
                    </code>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}

/** 只读信息行（§3.4：左=Label，右=值；行版式 flex justify-between py-2.5） */
function InfoRow({
  label,
  children,
  note,
}: {
  label: string
  children: ReactNode
  note?: string
}) {
  return (
    <div className='flex items-center justify-between gap-4 py-2.5'>
      <div className='grid gap-0.5'>
        <span className='text-sm font-medium'>{label}</span>
        {note && <span className='text-muted-foreground text-xs'>{note}</span>}
      </div>
      <div className='text-muted-foreground flex shrink-0 items-center gap-1.5 text-sm'>
        {children}
      </div>
    </div>
  )
}

export function PersonalInfoCard() {
  const { user } = useCurrentUser()

  return (
    <TitledCard
      icon={<Settings aria-hidden='true' />}
      tone='info'
      title={PERSONAL_INFO_TITLE}
      description={PERSONAL_INFO_DESCRIPTION}
    >
      <div className='grid'>
        <InfoRow label='用户名' note='用户名创建后不可修改，如需变更请联系管理员'>
          @{user?.username ?? '—'}
        </InfoRow>
        <InfoRow label='角色'>
          {user?.roleName ? (
            <Badge className='bg-muted text-muted-foreground'>{user.roleName}</Badge>
          ) : (
            '—'
          )}
        </InfoRow>
        <InfoRow label='用户 ID'>
          {user ? (
            <>
              <span className='font-mono tabular-nums'>{user.id}</span>
              <CopyButton
                value={user.id}
                aria-label={COPY_USER_ID_ARIA}
                successTooltip={COPY_USER_ID_TOAST}
                className='size-6 [&_svg]:size-3'
              />
            </>
          ) : (
            '—'
          )}
        </InfoRow>
        <InfoRow label='邮箱'>
          <Tooltip>
            <TooltipTrigger render={<span className='cursor-default' />}>
              {EMAIL_PENDING_VALUE}
            </TooltipTrigger>
            <TooltipContent>
              <p>{EMAIL_PENDING_TOOLTIP}</p>
            </TooltipContent>
          </Tooltip>
        </InfoRow>
        <InfoRow label='权限概览'>
          {user && <PermissionPopover permissions={user.permissions} />}
        </InfoRow>
      </div>
      <Alert className='mt-1'>
        <AlertDescription className='text-xs'>{PERSONAL_INFO_FOOTNOTE}</AlertDescription>
      </Alert>
    </TitledCard>
  )
}
