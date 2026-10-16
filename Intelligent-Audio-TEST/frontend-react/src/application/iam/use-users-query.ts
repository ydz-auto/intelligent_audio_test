/**
 * 用户管理 query/mutations（application 层）：
 * 列表 GET /users（分页 ≤100 + status/keyword/role_id 过滤，INT-347 §4.4.1）；
 * 行操作分走 PUT/POST/DELETE；成功 toast + invalidate 联动（对齐 newAPI
 * users-provider triggerRefresh 模式）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  assignMockRole,
  createMockUser,
  deleteMockUser,
  getUsers,
  grantMockPermissions,
  updateMockUser,
  USERS_QUERY_KEY,
  type UserListFilter,
} from '@/infrastructure/api/userApi'
export function useUsersQuery(filter: UserListFilter) {
  return useQuery({
    queryKey: [...USERS_QUERY_KEY, filter],
    queryFn: () => getUsers(filter),
    staleTime: 30_000,
  })
}

export function useUserMutations() {
  const queryClient = useQueryClient()

  const invalidateUsers = () =>
    void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY })

  const createUser = useMutation({
    mutationFn: createMockUser,
    onSuccess: () => {
      toast.success('用户已创建')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const updateUser = useMutation({
    mutationFn: (args: {
      userId: string
      patch: Parameters<typeof updateMockUser>[1]
    }) => updateMockUser(args.userId, args.patch),
    onSuccess: () => {
      toast.success('用户已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const assignRole = useMutation({
    mutationFn: (args: { userId: string; roleCode: string; roleName: string }) =>
      assignMockRole(args.userId, args.roleCode, args.roleName),
    onSuccess: () => {
      toast.success('用户角色已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const grantPermissions = useMutation({
    mutationFn: (args: { userId: string; permissions: string[] }) =>
      grantMockPermissions(args.userId, args.permissions),
    onSuccess: () => {
      toast.success('附加权限已授予')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const deleteUser = useMutation({
    mutationFn: deleteMockUser,
    onSuccess: () => {
      toast.success('用户已删除')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  return { createUser, updateUser, assignRole, grantPermissions, deleteUser }
}
