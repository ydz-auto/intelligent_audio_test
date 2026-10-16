import { createFileRoute, redirect } from '@tanstack/react-router'

import { hasPermission } from '@/domain/models/user'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { AudioImportPage } from '@/features/audio-import'

/**
 * 音频管理 /audio-import（侧栏「测试资产」组，INT-346 树）。
 * 16_设备域.md §5 全量可视稿：统计徽章行 + 列表/文件夹双视图 + 五维 facet + 上传进度卡
 * + 批量浮条 + 分页 Portal + 弹窗群（上传/文件夹导入/URL 导入/批量标注/预览/元数据/
 * 转换/特征分析/播放历史/批量操作）。本卡替换占位路由为完整实现（INT-505）。
 * beforeLoad：audio:read 守卫 → 无码整页 /403（§8.3）。
 */
export const Route = createFileRoute('/_authenticated/audio-import')({
  beforeLoad: () => {
    const user = useAuthStore.getState().user
    if (!hasPermission(user, 'audio:read')) {
      throw redirect({ to: '/403' })
    }
  },
  component: AudioImportPage,
})
