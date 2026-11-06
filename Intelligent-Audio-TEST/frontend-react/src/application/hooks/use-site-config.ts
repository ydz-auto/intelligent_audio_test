import { useSiteConfigStore } from '@/infrastructure/stores/site-config-store'

/**
 * 站点配置应用层 hook（DDD 依赖单向：interfaces/features 不直连 infrastructure/stores）。
 * SystemBrand / 登录页品牌 / 页脚消费；未加载完成时返回缺省配置（首帧不闪变）。
 */
export function useSiteConfig() {
  const config = useSiteConfigStore((s) => s.config)
  const loaded = useSiteConfigStore((s) => s.loaded)
  return { config, loaded }
}
