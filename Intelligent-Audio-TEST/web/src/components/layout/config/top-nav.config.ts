import type { TopNavLink } from '../types'

/**
 * 顶部导航兜底链接（02_导航栏.md §2.2 文案定稿：主页→控制台→报告→排行榜→文档→关于）。
 * 实际链接由 useTopNavLinks 生成（application 层）；此文件保留 newAPI 的
 * 「配置兜底」分层：后端导航模块接线后由动态链接覆盖。
 */
export const defaultTopNavLinks: TopNavLink[] = [
  { title: '主页', href: '/' },
  { title: '控制台', href: '/dashboard' },
  { title: '报告', href: '/reports' },
  { title: '排行榜', href: '/rankings' },
  { title: '文档', href: '/user-guide' },
  { title: '关于', href: '/about' },
]
