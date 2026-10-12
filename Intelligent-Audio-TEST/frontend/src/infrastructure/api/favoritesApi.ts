/**
 * Favorites / Trash API module（INT-141 收藏 + 回收站）
 * 出口契约：Domain（camelCase）；snake_case 转换收敛在本文件（Infrastructure 层）。
 */
import { request } from '../http/client';

/** 可收藏实体类型 */
export type FavoriteEntityType = 'task' | 'report' | 'testcase';

/** 收藏/取消收藏（幂等：重复收藏返回成功 + alreadyFavorited） */
export async function favorite(entityType: FavoriteEntityType, entityId: string | number) {
  return request<{ entity_type: string; entity_id: string; already_favorited?: boolean }>(
    'POST', `/${entityType}s/${entityId}/favorite`);
}

/** 取消收藏（幂等：未收藏同样成功） */
export async function unfavorite(entityType: FavoriteEntityType, entityId: string | number) {
  return request<Record<string, unknown>>('DELETE', `/${entityType}s/${entityId}/favorite`);
}

/** 当前用户收藏的实体 ID 列表（entityType 空 = 全部三类） */
export async function listFavoriteIds(entityType: FavoriteEntityType | '' = '') {
  const data = await request<Record<string, string[]>>(
    'GET', `/favorites${entityType ? `?entity_type=${entityType}` : ''}`);
  return {
    task: data.task ?? [],
    report: data.report ?? [],
    testcase: data.testcase ?? [],
  };
}

/** 回收站恢复（单个：ids 传一个；批量：传多个） */
export async function restore(entityType: FavoriteEntityType, ids: Array<string | number>) {
  return request<{ restored_count?: number }>(
    'POST', `/${entityType}s/restore`, { ids });
}

/** 回收站彻底删除（物理删除；服务端校验 admin/owner） */
export async function purge(entityType: FavoriteEntityType, ids: Array<string | number>) {
  return request<{ purged_count?: number }>(
    'POST', `/${entityType}s/purge`, { ids });
}
