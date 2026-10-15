import type { TopNavLink } from '@/components/layout/types'

/**
 * 顶部导航链接（application 层）。
 * 文案定稿：主页→控制台→报告→排行榜→文档→关于（02_导航栏.md §2.2）。
 * TODO(API 接线): 可见性按后端导航模块配置 + 权限码过滤；未建路由命中 404 页为可视稿预期。
 */
export function useTopNavLinks(): TopNavLink[] {
  return [
    { title: '主页', href: '/' },
    { title: '控制台', href: '/dashboard' },
    { title: '报告', href: '/reports' },
    { title: '排行榜', href: '/rankings' },
    { title: '文档', href: '/user-guide' },
    { title: '关于', href: '/about' },
  ]
}
