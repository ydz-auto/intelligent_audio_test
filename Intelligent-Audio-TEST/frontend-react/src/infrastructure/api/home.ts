import type { HomeStatsDetails } from '@/domain/models/home'
import { toHomeStatsDetails } from '@/infrastructure/adapters/dto/home-adapter'
import type { HomeStatsDetailsDto } from '@/infrastructure/dto/home.dto'
import { request } from '@/infrastructure/api/client'

/**
 * 首页统计 details API（infrastructure 层）。
 * 接线 INT-642：GET /api/v1/home/stats/details（home:read 权限；home_bp.py
 * HomeStatsDetails 输出 snake_case）——snake_case→camelCase 转换收敛于
 * adapters/dto/home-adapter（DDD 四层：domain 层不留 snake_case 穿透），
 * 03_首页.md §7 直通口径按 adapters/dto/home-adapter 落实。
 * INT-1032 返修：原实现直通 raw snake_case 致工作台/门户消费端
 * （details.testCases 等 camelCase 访问）崩溃——改用 adapter 归一。
 * INT-1225：skipAuthRedirect——首页门户公开页匿名 401 不触发 sessionExpired
 * 整页跳登录，规模条按「未登录整条替换为登录引导」降级（03_首页.md §3.1/§5）。
 */
export async function fetchHomeStatsDetails(): Promise<HomeStatsDetails> {
  const dto = await request<HomeStatsDetailsDto>('GET', '/home/stats/details', undefined, {
    skipAuthRedirect: true,
  })
  return toHomeStatsDetails(dto)
}
