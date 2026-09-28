/**
 * 权限判断 composable（Ports：Application 层唯一权限入口）
 *
 * V9.7.10 过渡策略（对齐后端 AUTH_ENABLED=false）：无认证体系，默认授予全部已发布任务权限点；
 * G 域 RBAC 落地后，改为从 /auth/me 读取 permissions（字符串数组，含 '*' 通配）替换默认值。
 */
import { ref } from 'vue';
import { PermissionPoint, type PermissionPointValue } from '../domain/enums';

// 默认全部放行（过渡期）；G 域接入后通过 setPermissions() 注入真实权限点
const permissionPoints = ref<string[]>(Object.values(PermissionPoint));

export function usePermissions() {
  function setPermissions(points: string[]) {
    permissionPoints.value = points || [];
  }

  /** 当前用户是否持有某权限点（'*' 通配放行） */
  function can(perm: PermissionPointValue | string): boolean {
    const points = permissionPoints.value;
    return points.includes('*') || points.includes(perm);
  }

  return {
    permissionPoints,
    setPermissions,
    can,
  };
}
