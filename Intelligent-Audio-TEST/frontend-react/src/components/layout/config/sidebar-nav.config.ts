import {
  Activity,
  AudioWaveform,
  Box,
  ClipboardList,
  FileBarChart,
  FileText,
  Gauge,
  Headphones,
  ListChecks,
  MessagesSquare,
  Music,
  Play,
  Settings,
  Tags,
} from 'lucide-react'

import type { NavGroup } from '../types'

/**
 * 工作台侧栏树（04_控制台.md §3.2 定稿 + INT-486 负责人口径 2026-10-16 对齐）：
 * 终态六组十五项——总览（概览）/AI 工具（灵犀Agent）/测试执行（开始测试+任务管理）/
 * 测试资产（用例+音频+设备+报告中心）/测试配置（算法配置+评估维度+SPL 映射+标签管理，
 * INT-417 自设置工作区提升；组名取中文业务名「测试配置」，非内部名「测试域」）/
 * 管理（日志+系统设置）。
 * 权限码与图标均为规范定稿值；系统设置入口点击进入 drill-in 视图。
 * 开始测试=端到端+API 合并入口（INT-486：一个入口内部两模式）；algo_engineer
 * 只读观察（INT-449）经 algorithm:read 命中（与 task:execute 任一）。
 */
export const ROOT_SIDEBAR_NAV: NavGroup[] = [
  {
    id: 'overview',
    title: '总览',
    items: [
      {
        title: '概览',
        url: '/dashboard',
        icon: Activity,
        requiredPermission: 'home:read',
      },
    ],
  },
  {
    id: 'ai-tools',
    title: 'AI 工具',
    items: [
      {
        title: '灵犀Agent',
        url: '/ai-chat',
        icon: MessagesSquare,
        requiredPermission: 'report:read',
      },
    ],
  },
  {
    id: 'testing',
    title: '测试执行',
    items: [
      {
        title: '开始测试',
        url: '/start-test',
        icon: Play,
        requiredPermissions: ['task:execute', 'algorithm:read'],
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
        // 双视图路径 /testcases/$view 同项高亮（checkIsActive activeUrls 等价机制）
        activeUrls: ['/testcases'],
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
    id: 'test-config',
    title: '测试配置',
    items: [
      {
        title: '算法配置',
        url: '/AlgorithmConfig',
        icon: Box,
        requiredPermission: 'algorithm:read',
      },
      {
        title: '评估维度',
        url: '/Evaluation',
        icon: Gauge,
        requiredPermission: 'evaluation:read',
      },
      {
        title: 'SPL 映射',
        url: '/SPLMapping',
        icon: AudioWaveform,
        requiredPermissions: ['spl:read', 'digital_spl:read'],
      },
      {
        title: '标签管理',
        url: '/TagManagement',
        icon: Tags,
        requiredPermission: 'tag:read',
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
          'role:read',
          'auth:manage_provider',
          'log:manage',
        ],
      },
    ],
  },
]
