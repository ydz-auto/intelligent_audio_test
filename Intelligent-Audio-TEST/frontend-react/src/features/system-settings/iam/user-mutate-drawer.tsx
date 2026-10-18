/**
 * 新建/编辑用户抽屉（interfaces 层，INT-347 §4.4.1）：
 * Sheet `sm:max-w-[600px]` 三段式（基本信息 / 角色与状态 / 附加权限 PermissionMatrix）；
 * 打开时按目标用户回填，角色变更走 assign_role、信息变更走 update、权限变更走 grant。
 * 新建态状态字段置灰固定「正常」（POST /auth/users 不落 status，INT-691 P3-1），
 * 创建后可在列表中启用/停用；编辑态状态可选并随 PUT 落库。
 */
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  SideDrawerSection,
  SideDrawerSectionHeader,
  sideDrawerContentClassName,
  sideDrawerFooterClassName,
  sideDrawerFormClassName,
  sideDrawerHeaderClassName,
} from '@/components/drawer-layout'
import { ROLE_META, type RoleCode } from '@/domain/models/role'
import {
  USER_STATUS_META,
  type PlatformUser,
  type PlatformUserStatus,
} from '@/domain/models/user'

import { PermissionMatrix } from '../components/permission-matrix'

type UserMutateDrawerProps = {
  open: boolean
  mode: 'create' | 'edit'
  user: PlatformUser | null
  roles: Array<{ code: string; name: string }>
  permissionModules: Parameters<typeof PermissionMatrix>[0]['permissionModules']
  onOpenChange: (open: boolean) => void
  onCreate: (input: {
    username: string
    displayName?: string
    email: string
    password: string
    roleCode: string
    status: PlatformUserStatus
  }) => void
  onUpdate: (
    userId: string,
    patch: Partial<
      Pick<PlatformUser, 'displayName' | 'email' | 'status' | 'roleCode' | 'roleName'>
    >
  ) => void
  onAssignRole: (userId: string, roleCode: string, roleName: string) => void
  onGrantPermissions: (userId: string, permissions: string[]) => void
}

export function UserMutateDrawer(props: UserMutateDrawerProps) {
  const isCreate = props.mode === 'create'
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [roleCode, setRoleCode] = useState('tester')
  const [status, setStatus] = useState<PlatformUserStatus>('active')
  const [permissions, setPermissions] = useState<string[]>([])

  // 打开/切换目标用户时回填（编辑态不回填密码）
  useEffect(() => {
    if (!props.open) return
    const target = props.user
    setUsername(target?.username ?? '')
    setDisplayName(target?.displayName ?? '')
    setEmail(target?.email ?? '')
    setPassword('')
    setRoleCode(target?.roleCode ?? 'tester')
    setStatus(target?.status ?? 'active')
    setPermissions(target?.extraPermissions ?? [])
  }, [props.open, props.user])

  const baseRoleName = ROLE_META[roleCode as RoleCode]?.name ?? roleCode

  const handleSave = () => {
    if (isCreate) {
      if (!username.trim() || !email.trim() || !password.trim()) return
      props.onCreate({
        username: username.trim(),
        displayName: displayName.trim() || undefined,
        email: email.trim(),
        password,
        roleCode,
        status,
      })
    } else if (props.user) {
      // 角色变更走 assign_role，信息/状态变更走 update，权限变更走 grant
      if (roleCode !== props.user.roleCode) {
        props.onAssignRole(props.user.id, roleCode, baseRoleName)
      }
      props.onUpdate(props.user.id, { displayName, email, status })
      if (
        JSON.stringify(permissions) !==
        JSON.stringify(props.user.extraPermissions)
      ) {
        props.onGrantPermissions(props.user.id, permissions)
      }
    }
  }

  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className={sideDrawerContentClassName('sm:max-w-[600px]')}>
        <SheetHeader className={sideDrawerHeaderClassName()}>
          <SheetTitle>{isCreate ? '新建用户' : '编辑用户'}</SheetTitle>
          <SheetDescription>
            {isCreate
              ? '创建平台账号并分配初始角色'
              : `编辑用户 ${props.user?.username ?? ''} 的信息与权限`}
          </SheetDescription>
        </SheetHeader>
        <div className={sideDrawerFormClassName()}>
          <SideDrawerSection>
            <SideDrawerSectionHeader
              title='基本信息'
              description='用户名创建后不可修改'
            />
            <div className='grid gap-3'>
              <div className='grid gap-1.5'>
                <label className='text-sm font-medium' htmlFor='user-username'>
                  用户名 <span className='text-destructive'>*</span>
                </label>
                <Input
                  id='user-username'
                  placeholder='输入用户名'
                  disabled={!isCreate}
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
                {!isCreate && (
                  <p className='text-muted-foreground text-xs'>
                    用户名创建后不可修改
                  </p>
                )}
              </div>
              <div className='grid gap-1.5'>
                <label
                  className='text-sm font-medium'
                  htmlFor='user-display-name'
                >
                  显示名
                </label>
                <Input
                  id='user-display-name'
                  placeholder='留空则使用用户名'
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </div>
              <div className='grid gap-1.5'>
                <label className='text-sm font-medium' htmlFor='user-email'>
                  邮箱 <span className='text-destructive'>*</span>
                </label>
                <Input
                  id='user-email'
                  placeholder='name@example.com'
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
              <div className='grid gap-1.5'>
                <label className='text-sm font-medium' htmlFor='user-password'>
                  密码
                </label>
                <Input
                  id='user-password'
                  type='password'
                  placeholder={
                    isCreate ? '输入密码（8–128 位）' : '留空表示不修改密码'
                  }
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </div>
          </SideDrawerSection>

          <SideDrawerSection>
            <SideDrawerSectionHeader
              title='角色与状态'
              description='决定该用户的基线权限范围'
            />
            <div className='grid grid-cols-2 gap-3'>
              <div className='grid gap-1.5'>
                <label className='text-sm font-medium' htmlFor='user-role'>
                  角色
                </label>
                <Select
                  value={roleCode}
                  onValueChange={(value) => setRoleCode(value ?? 'tester')}
                >
                  <SelectTrigger id='user-role' className='h-8'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {props.roles.map((role) => (
                      <SelectItem key={role.code} value={role.code}>
                        {role.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-1.5'>
                <label className='text-sm font-medium' htmlFor='user-status'>
                  状态
                </label>
                <Select
                  value={status}
                  disabled={isCreate}
                  itemToStringLabel={(value) =>
                    USER_STATUS_META[value as PlatformUserStatus]?.label ??
                    String(value)
                  }
                  onValueChange={(value) => setStatus(value as PlatformUserStatus)}
                >
                  <SelectTrigger id='user-status' className='h-8'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='active'>正常</SelectItem>
                    <SelectItem value='disabled'>停用</SelectItem>
                    <SelectItem value='locked'>锁定</SelectItem>
                  </SelectContent>
                </Select>
                {isCreate && (
                  <p className='text-muted-foreground text-xs'>
                    创建后可在列表中启用/停用
                  </p>
                )}
              </div>
            </div>
          </SideDrawerSection>

          <SideDrawerSection>
            <SideDrawerSectionHeader
              title='附加权限'
              description='在角色权限基础上追加或收回该用户的额外权限，角色权限本身不受影响'
            />
            <PermissionMatrix
              value={permissions}
              onChange={setPermissions}
              permissionModules={props.permissionModules}
            />
          </SideDrawerSection>
        </div>
        <SheetFooter className={sideDrawerFooterClassName()}>
          <Button variant='outline' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave}>{isCreate ? '创建' : '保存'}</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
