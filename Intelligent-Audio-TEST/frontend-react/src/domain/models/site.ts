/**
 * 站点配置领域模型（domain 层，接线壳 INT-607）。
 * 站名等站点级配置统一经 site-config-store 下发（SystemBrand / 登录页品牌 /
 * 页脚 / document.title 共用）。后端站点配置端点未落（对照主库 home_bp.py
 * 仅 stats/details·refresh·summary 三端点，无 site 配置）——site-api 在
 * infrastructure 层请求真实端点，失败/缺失时回落缺省常量（12_登录与错误页.md
 * §3.2「站名取站点配置 store 的 systemName，缺省「智能语音测试平台」」）。
 */

export type SiteConfig = {
  /** 站点名称（缺省「智能语音测试平台」） */
  systemName: string
  /** 站点版本角标（缺省「演示版」） */
  version: string
  /** 站点 Logo（缺省空串 → 组件内文字标志/图标占位） */
  logo: string
  /** 支持邮箱（缺省空串 → 页脚 mailto 不渲染） */
  supportEmail: string
}

/** 站点配置缺省值（红线④ 品牌常量本地化；后端端点落定后仅替换 infrastructure 读写） */
export const DEFAULT_SITE_CONFIG: SiteConfig = {
  systemName: '智能语音测试平台',
  version: '演示版',
  logo: '',
  supportEmail: '',
}
