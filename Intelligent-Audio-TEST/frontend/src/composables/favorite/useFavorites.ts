import { ref } from 'vue';
import * as favoritesApi from '../../infrastructure/api/favoritesApi';
import type { FavoriteEntityType } from '../../infrastructure/api/favoritesApi';

/**
 * useFavorites - 收藏 / 回收站组合式函数（INT-141）
 *
 * per-user 收藏集合 + 星标切换 + 收藏筛选 + 回收站恢复/彻底删除。
 * user_id 由后端从 JWT 解析（AUTH_MODE=off 时为未收藏语义），前端不传。
 */
export function useFavorites(entityType: FavoriteEntityType) {
  /** 当前用户在该实体类型下已收藏的 ID 集合（字符串化 key） */
  const favoriteIds = ref<Set<string>>(new Set());
  /** 列表“仅收藏”筛选开关 */
  const favoriteOnly = ref(false);
  /** 操作中状态（防抖） */
  const pendingIds = ref<Set<string>>(new Set());

  const keyOf = (id: string | number) => String(id);

  async function loadFavorites() {
    try {
      const ids = await favoritesApi.listFavoriteIds(entityType);
      favoriteIds.value = new Set((ids[entityType] ?? []).map(keyOf));
    } catch (e) {
      console.warn('[useFavorites] 收藏列表加载失败', e);
    }
  }

  function isFavorite(id: string | number): boolean {
    return favoriteIds.value.has(keyOf(id));
  }

  async function toggleFavorite(id: string | number) {
    const key = keyOf(id);
    if (pendingIds.value.has(key)) return;
    pendingIds.value.add(key);
    try {
      if (favoriteIds.value.has(key)) {
        await favoritesApi.unfavorite(entityType, id);
        const next = new Set(favoriteIds.value);
        next.delete(key);
        favoriteIds.value = next;
      } else {
        await favoritesApi.favorite(entityType, id);
        favoriteIds.value = new Set(favoriteIds.value).add(key);
      }
    } catch (e) {
      console.error('[useFavorites] 切换收藏失败', e);
      throw e;
    } finally {
      const next = new Set(pendingIds.value);
      next.delete(key);
      pendingIds.value = next;
    }
  }

  async function restore(ids: Array<string | number>) {
    return favoritesApi.restore(entityType, ids);
  }

  /** 彻底删除（前端二次确认由调用方完成；服务端校验 admin/owner） */
  async function purge(ids: Array<string | number>) {
    return favoritesApi.purge(entityType, ids);
  }

  return {
    favoriteIds,
    favoriteOnly,
    isFavorite,
    loadFavorites,
    toggleFavorite,
    restore,
    purge,
  };
}
