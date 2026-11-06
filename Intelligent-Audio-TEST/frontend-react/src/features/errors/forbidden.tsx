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
import { useNavigate, useRouter } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 403 页面（newAPI 版式照搬，文案 §7）：返回 / 返回主页 / 切换账号（登出→登录）；
 * `from` 来源页面小字（守卫 redirect 携带，无则隐藏，§4.3）。
 */
export function ForbiddenError({ from }: { from?: string }) {
  const navigate = useNavigate()
  const { history } = useRouter()

  function handleSwitchAccount() {
    // 登出并跳登录页（服务角色变更/权限收紧场景，§4.3 第三钮）
    void useAuthStore.getState().logout().then(() => {
      void navigate({ to: '/login' })
    })
  }

  return (
    <div className='h-svh'>
      <div className='m-auto flex h-full w-full flex-col items-center justify-center gap-2'>
        <h1 className='text-[7rem] leading-tight font-bold'>403</h1>
        <span className='font-medium'>禁止访问</span>
        <p className='text-muted-foreground text-center'>
          您没有必要的权限，
          <br />
          无法查看此资源。
        </p>
        {from && (
          <p className='text-muted-foreground text-xs'>来源页面：{from}</p>
        )}
        <div className='mt-6 flex flex-wrap justify-center gap-4'>
          <Button variant='outline' onClick={() => history.go(-1)}>
            返回
          </Button>
          <Button onClick={() => navigate({ to: '/' })}>返回主页</Button>
          <Button variant='ghost' onClick={handleSwitchAccount}>
            切换账号
          </Button>
        </div>
      </div>
    </div>
  )
}
