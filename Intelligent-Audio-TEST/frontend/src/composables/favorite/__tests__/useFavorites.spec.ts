/**
 * INT-216：useFavorites 单测补齐（INT-141 前端零单测的建议项 S1）。
 *
 * 覆盖：加载成功填充 / 失败降级提示（INT-215 P5 后口径，不再静默）、
 * toggle 幂等（pendingIds 防抖）、收藏↔取消收藏状态机、
 * id 字符串化归一（number/string 等价）、restore/purge 透传、
 * per-user 隔离口径（user_id 由后端 JWT 解析，前端锁定 entityType 圈定）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const api = vi.hoisted(() => ({
  listFavoriteIds: vi.fn(),
  favorite: vi.fn(),
  unfavorite: vi.fn(),
  restore: vi.fn(),
  purge: vi.fn(),
}));

vi.mock('@/infrastructure/api/favoritesApi', () => api);

import { provideNotification } from '@/composables/modal/useNotification';
import { useFavorites } from '../useFavorites';

const show = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  provideNotification({ show });
});

describe('useFavorites 加载（loadFavorites）', () => {
  it('成功：按 entityType 圈定填充字符串化 id 集合', async () => {
    api.listFavoriteIds.mockResolvedValue({
      task: [1, '2'],
      report: ['r9'],
      testcase: ['c8'],
    });

    const fav = useFavorites('task');
    await fav.loadFavorites();

    expect(api.listFavoriteIds).toHaveBeenCalledWith('task');
    expect(fav.favoriteIds.value).toEqual(new Set(['1', '2']));
    expect(fav.isFavorite(1)).toBe(true);       // number 归一
    expect(fav.isFavorite('2')).toBe(true);
    expect(fav.isFavorite('r9')).toBe(false);   // 其他实体类型不混入
  });

  it('失败：一次性降级提示且不抛出（星标态可能失真）', async () => {
    api.listFavoriteIds.mockRejectedValue(new Error('gRPC down'));

    const fav = useFavorites('report');
    await expect(fav.loadFavorites()).resolves.toBeUndefined();

    expect(show).toHaveBeenCalledTimes(1);
    const [message, type] = show.mock.calls[0];
    expect(message).toContain('收藏状态加载失败');
    expect(type).toBe('warning');
    expect(fav.favoriteIds.value.size).toBe(0);
  });

  it('响应缺当前 entityType 键时按空集合处理', async () => {
    api.listFavoriteIds.mockResolvedValue({ task: ['t1'] });

    const fav = useFavorites('testcase');
    await fav.loadFavorites();

    expect(fav.favoriteIds.value.size).toBe(0);
  });
});

describe('useFavorites 切换（toggleFavorite）', () => {
  it('未收藏 → 调 favorite 并加入集合', async () => {
    api.favorite.mockResolvedValue({ entity_id: '7' });

    const fav = useFavorites('task');
    await fav.toggleFavorite(7);

    expect(api.favorite).toHaveBeenCalledWith('task', 7);
    expect(fav.isFavorite('7')).toBe(true);
    expect(api.unfavorite).not.toHaveBeenCalled();
  });

  it('已收藏 → 调 unfavorite 并移出集合（幂等语义由后端兜底）', async () => {
    api.listFavoriteIds.mockResolvedValue({ task: ['7'] });
    api.unfavorite.mockResolvedValue({});

    const fav = useFavorites('task');
    await fav.loadFavorites();
    await fav.toggleFavorite('7');

    expect(api.unfavorite).toHaveBeenCalledWith('task', '7');
    expect(fav.isFavorite(7)).toBe(false);
  });

  it('并发重复触发同 id：pendingIds 防抖，仅发起一次请求', async () => {
    let release!: (v: unknown) => void;
    api.favorite.mockReturnValue(new Promise(resolve => { release = resolve; }));

    const fav = useFavorites('task');
    const first = fav.toggleFavorite('9');
    const second = fav.toggleFavorite('9'); // 首次未落定，第二次应被吞掉

    release({});
    await Promise.all([first, second]);

    expect(api.favorite).toHaveBeenCalledTimes(1);
    expect(fav.isFavorite('9')).toBe(true);
  });

  it('请求失败：向上抛出（由调用方统一反馈）且防抖集清理可重试', async () => {
    api.favorite.mockRejectedValueOnce(new Error('403'));

    const fav = useFavorites('task');
    await expect(fav.toggleFavorite('5')).rejects.toThrow('403');

    expect(fav.isFavorite('5')).toBe(false);

    api.favorite.mockResolvedValueOnce({});
    await fav.toggleFavorite('5'); // 重试成功
    expect(fav.isFavorite('5')).toBe(true);
  });
});

describe('useFavorites 回收站操作（restore / purge）', () => {
  it('restore/purge 原样透传 entityType 与 ids（count 判真由调用方负责）', async () => {
    api.restore.mockResolvedValue({ restored_count: 2 });
    api.purge.mockResolvedValue({ purged_count: 0 });

    const fav = useFavorites('report');
    await expect(fav.restore([1, '2'])).resolves.toEqual({ restored_count: 2 });
    await expect(fav.purge(['x'])).resolves.toEqual({ purged_count: 0 });

    expect(api.restore).toHaveBeenCalledWith('report', [1, '2']);
    expect(api.purge).toHaveBeenCalledWith('report', ['x']);
  });
});
