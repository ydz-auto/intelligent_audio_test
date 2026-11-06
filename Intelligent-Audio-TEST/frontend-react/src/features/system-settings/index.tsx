/**
 * 系统设置 drill-in 工作区外壳（interfaces 层）：仅 <Outlet/>。
 * 侧栏树由 layout/config/system-settings.config.ts 接管（六域树），
 * 页头「返回工作台」指向 /dashboard（INT-346 定稿）。
 */
import { Outlet } from '@tanstack/react-router'

export default function SystemSettingsWorkspace() {
  return <Outlet />
}
