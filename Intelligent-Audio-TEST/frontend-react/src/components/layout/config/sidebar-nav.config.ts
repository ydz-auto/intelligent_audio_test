import {
  Activity,
  ArrowLeftRight,
  ClipboardList,
  FileBarChart,
  FileText,
  Headphones,
  ListChecks,
  MessagesSquare,
  Music,
  Settings,
  Smartphone,
} from 'lucide-react'

import type { NavGroup } from '../types'

/**
 * 控制台侧栏树（04_控制台.md §3.2 定稿：总览/测试执行/测试资产/管理 四组十项；
 * 08_AI对话页.md §3.1 回写：新增「AI 工具」组 → 五组十一项）。
 * 权限码与图标均为规范定稿值；系统设置入口点击进入 drill-in 视图。
 */
export const ROOT_SIDEBAR_NAV: NavGroup[] = [
  {
    id: 'overview',
    title: '总览',
    items: [
      {
        title: '工作台',
        url: '/dashboard',
        icon: Activity,
        requiredPermission: 'home:read',
      },
    ],
  },
  {
    id: 'testing',
    title: '测试执行',
    items: [
      {
        title: '端到端测试',
        url: '/E2ETest',
        icon: Smartphone,
        requiredPermission: 'task:execute',
      },
      {
        title: 'API 测试',
        url: '/APITest',
        icon: ArrowLeftRight,
        requiredPermission: 'task:execute',
      },
      {
        title: '任务管理',
        url: '/tasks',
        icon: ClipboardList,
        requiredPermission: 'task:read',
        // 任务详情 /tasks/:id 同项高亮（checkIsActive activeUrls 等价机制）
        activeUrls: ['/tasks'],
      },
    ],
  },
  {
    id: 'assets',
    title: '测试资产',
    items: [
      {
        title: '用例管理',
        url: '/testcases',
        icon: ListChecks,
        requiredPermission: 'testcase:read',
      },
      {
        title: '音频管理',
        url: '/audio-import',
        icon: Music,
        requiredPermission: 'audio:read',
      },
      {
        title: '设备管理',
        url: '/devices',
        icon: Headphones,
        requiredPermission: 'device:read',
      },
      {
        title: '报告中心',
        url: '/report-center',
        icon: FileBarChart,
        requiredPermission: 'report:read',
      },
    ],
  },
  {
    id: 'ai-tools',
    title: 'AI 工具',
    items: [
      {
        title: 'AI 对话',
        url: '/ai-chat',
        icon: MessagesSquare,
        requiredPermission: 'report:read',
      },
    ],
  },
  {
    id: 'admin',
    title: '管理',
    items: [
      {
        title: '日志查看',
        url: '/logs',
        icon: FileText,
        requiredPermission: 'log:read',
      },
      {
        title: '系统设置',
        url: '/system-settings/site',
        icon: Settings,
        requiredPermissions: [
          'user:read',
          'auth:manage_provider',
          'algorithm:definition_manage',
          'evaluation:dim_manage',
          'tag:create',
          'spl:create',
          'digital_spl:create',
        ],
      },
    ],
  },
]
