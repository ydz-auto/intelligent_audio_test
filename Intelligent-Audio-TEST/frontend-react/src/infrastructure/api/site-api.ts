/**
 * 站点配置 API（infrastructure/api 层，接线壳 INT-607）。
 * 真实端点：GET /api/v1/home/site（对照主库 home/site 配置端点口径；home_bp.py
 * 仅 stats/details·refresh·summary 三端点，site 配置端点待后端立项——见
 * FEAT 卡「站点配置端点」）。
 * 端点缺失/失败时回落缺省配置（规范「缺省「智能语音测试平台」」），不阻断壳渲染；
 * 不写兼容层。端点落定后本文件仅需删除回落分支并保持 DTO 映射。
 */
import { apiClient } from './client'
import type { SiteConfig } from '@/domain/models/site'
import { DEFAULT_SITE_CONFIG } from '@/domain/models/site'
import {
  toSiteConfig,
  type SiteConfigDto,
} from '@/infrastructure/dto/site.dto'

/**
 * 拉取站点配置。端点未落/请求失败（404/网络异常/无权限）→ 返回缺省配置，
 * 保证品牌区/登录页在端点缺失时仍按规范缺省值渲染。
 */
export async function fetchSiteConfig(): Promise<SiteConfig> {
  try {
    const dto = await apiClient.get<SiteConfigDto>('/home/site')
    return toSiteConfig(dto ?? {})
  } catch {
    // 站点配置端点未落（待 INT-FEAT）：回落缺省，静默不报错
    return DEFAULT_SITE_CONFIG
  }
}
