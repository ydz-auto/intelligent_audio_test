import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { DEVICES_TAB_WHITELIST, type DevicesTabKey } from '@/features/devices/constants'
import { DevicesPage } from '@/features/devices'

/**
 * /devices/$tab 设备管理三页签（16_设备域.md §3.2）。
 * 页签白名单 ['test','playback','api']，非法 beforeLoad 重定向 test；
 * 页签级权限守卫——test 需 device:read、playback 需 playback:read、api 需 api_config:read；
 * 无对应码者该页签整项隐藏（§3.2，页面内 Tabs 过滤），三者皆无不进 /devices（侧栏由
 * device:read 过滤）；整页 URL 直达且无任何码 → /403。
 */
const devicesSearchSchema = z.object({
  page: z.number().optional().catch(1),
  pageSize: z.number().optional().catch(20),
  search: z.string().optional().catch(undefined),
  status: z.string().optional().catch(undefined),
  deviceType: z.string().optional().catch(undefined),
  connectionType: z.string().optional().catch(undefined),
  groupId: z.string().optional().catch(undefined),
  labId: z.string().optional().catch(undefined),
  sortBy: z.string().optional().catch(undefined),
  sortOrder: z.string().optional().catch(undefined),
  batchMode: z.boolean().optional().catch(undefined),
  idSort: z.boolean().optional().catch(undefined),
  alarmsOpen: z.boolean().optional().catch(undefined),
})

const TAB_PERMISSION: Record<string, string> = {
  test: 'device:read',
  playback: 'playback:read',
  api: 'api_config:read',
}

export const Route = createFileRoute('/_authenticated/devices/$tab')({
  beforeLoad: ({ params }) => {
    const user = useAuthStore.getState().user
    const tab = params.tab
    if (!DEVICES_TAB_WHITELIST.includes(tab)) {
      throw redirect({ to: '/devices/$tab', params: { tab: 'test' } })
    }
    const required = TAB_PERMISSION[tab]
    if (!hasPermission(user, required)) {
      throw redirect({ to: '/403' })
    }
  },
  validateSearch: devicesSearchSchema,
  component: DevicesTabPage,
})

function DevicesTabPage() {
  const { tab } = Route.useParams()
  return <DevicesPage tab={tab as DevicesTabKey} />
}
