/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
import { Link } from '@tanstack/react-router'
import { LogOut, Settings, UserRound } from 'lucide-react'

import { SignOutDialog } from '@/components/sign-out-dialog'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SYSTEM_SETTINGS_PERMISSIONS } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { useDialog } from '@/hooks/use-dialog'
import { getUserAvatarFallback, getUserAvatarStyle } from '@/lib/avatar'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/application/hooks/use-permissions'

/**
 * 用户下拉（右区末项；04_控制台.md §1.1 对位重写）：
 * 触发钮 Avatar 哈希取色 → 下拉 w-56：用户卡（头像+用户名+角色名）→
 * 个人中心 / 系统设置（有设置域权限者显）/ 分隔线 / 登出 destructive。
 */
export function ProfileDropdown() {
  const [signOutOpen, signOut] = useDialog()
  const user = useAuthStore((s) => s.user)
  const { hasAnyPermission } = usePermissions()
  const canOpenSettings = hasAnyPermission([...SYSTEM_SETTINGS_PERMISSIONS])

  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger
          render={
            <Button
              variant='ghost'
              size='icon'
              className='size-8 rounded-full p-0'
              aria-label='用户菜单'
            />
          }
        >
          <Avatar className='size-6'>
            <AvatarFallback
              style={user ? getUserAvatarStyle(user.username) : undefined}
              className='text-xs'
            >
              {user ? getUserAvatarFallback(user.username) : '?'}
            </AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
        <DropdownMenuContent className='w-56' align='end' sideOffset={8}>
          <DropdownMenuLabel className='flex items-center gap-2'>
            <Avatar className='size-8'>
              <AvatarFallback
                style={user ? getUserAvatarStyle(user.username) : undefined}
                className='text-sm'
              >
                {user ? getUserAvatarFallback(user.username) : '?'}
              </AvatarFallback>
            </Avatar>
            <div className='grid min-w-0 flex-1 text-start leading-tight'>
              <span className='truncate text-sm font-medium'>
                {user?.displayName ?? user?.username ?? '未登录'}
              </span>
              <span className='text-muted-foreground truncate text-xs'>
                {user?.roleName ?? '—'}
              </span>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem render={<Link to='/profile' />}>
              <UserRound aria-hidden='true' />
              个人中心
            </DropdownMenuItem>
            {canOpenSettings && (
              <DropdownMenuItem
                render={
                  <Link
                    to='/system-settings/$section'
                    params={{ section: 'site' }}
                  />
                }
              >
                <Settings aria-hidden='true' />
                系统设置
              </DropdownMenuItem>
            )}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant='destructive'
            className={cn('text-destructive')}
            onSelect={(event) => {
              event.preventDefault()
              signOut.open()
            }}
          >
            <LogOut aria-hidden='true' />
            登出
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <SignOutDialog open={signOutOpen} onOpenChange={signOut.toggle} />
    </>
  )
}
