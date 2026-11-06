import { create } from 'zustand'

import type { SiteConfig } from '@/domain/models/site'
import { DEFAULT_SITE_CONFIG } from '@/domain/models/site'
import { fetchSiteConfig } from '@/infrastructure/api/site-api'

/**
 * 站点配置 store（infrastructure/stores 层，接线壳 INT-607）。
 * systemName 等站点级配置的真实数据源（SystemBrand / 登录页品牌 / 页脚消费）；
 * 由 main 装配引导 hydrate（与 auth 会话引导同源模式），失败回落缺省配置。
 * 登录态无关（公开数据），不持久化。
 */
type SiteConfigState = {
  config: SiteConfig
  /** 是否已从后端加载（首帧缺省值渲染，加载完成后就地更新） */
  loaded: boolean
  hydrate: () => Promise<void>
}

export const useSiteConfigStore = create<SiteConfigState>()((set) => ({
  config: DEFAULT_SITE_CONFIG,
  loaded: false,
  hydrate: async () => {
    const config = await fetchSiteConfig()
    set({ config, loaded: true })
  },
}))

/** 会话引导共享 promise（main 装配/测试共用；避免重复请求） */
let siteBootstrap: Promise<void> | null = null

export function ensureSiteConfig(): Promise<void> {
  if (!siteBootstrap) {
    siteBootstrap = useSiteConfigStore.getState().hydrate()
  }
  return siteBootstrap
}

/** 复位引导（测试隔离用；下次 ensureSiteConfig 重新拉取） */
export function resetSiteConfigBootstrap(): void {
  siteBootstrap = null
}
