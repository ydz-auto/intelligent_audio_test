/**
 * 用例域 mock 常量（infrastructure 层；红线④：不接真实后端）。
 * 形态对照 api_gateway/schemas/testcase.py TestCaseListItem / TagItem / TagCategoryItem、
 * group.py GroupItem、evaluation.py DimensionItem 实测；接线时字段不返工。
 * 标签分类/色值走业务数据自带 color（INT-487 按分类呈现，数据驱动色非主题色）。
 */
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type {
  Dimension,
  EvaluationCategory,
  EvaluationDimensionItem,
} from '@/domain/models/evaluationDimension'
import type { TagCategory, TagItem } from '@/domain/models/testTag'

/** 标签分类（testcase.py TagCategoryItem：id/name/description/color/sort_order/tag_count） */
export const MOCK_TAG_CATEGORIES: TagCategory[] = [
  { id: 1, name: '人数', description: '按参与人数区分测试场景', color: '#f97316', sortOrder: 1, tagCount: 3, createdAt: '2026-09-01 10:00', updatedAt: '2026-09-01 10:00' },
  { id: 2, name: '场景', description: '按使用场景区分', color: '#06b6d4', sortOrder: 2, tagCount: 5, createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 3, name: '语种', description: '测试语种', color: '#8b5cf6', sortOrder: 3, tagCount: 2, createdAt: '2026-09-01 10:10', updatedAt: '2026-09-01 10:10' },
  { id: 4, name: '噪声环境', description: '背景噪声条件', color: '#84cc16', sortOrder: 4, tagCount: 3, createdAt: '2026-09-01 10:15', updatedAt: '2026-09-01 10:15' },
  { id: 5, name: '设备类型', description: '被测设备形态', color: '#14b8a6', sortOrder: 5, tagCount: 2, createdAt: '2026-09-01 10:20', updatedAt: '2026-09-01 10:20' },
  { id: 6, name: '距离', description: '按测试距离区分远场近场', color: '#6366f1', sortOrder: 6, tagCount: 3, createdAt: '2026-09-01 10:25', updatedAt: '2026-09-01 10:25' },
]

/** 标签（testcase.py TagItem：id/name/description/color/category_id/category_name） */
export const MOCK_TAGS: TagItem[] = [
  { id: 11, name: '1人', description: null, color: '#f97316', categoryId: 1, categoryName: '人数', createdAt: '2026-09-01 10:00', updatedAt: '2026-09-01 10:00' },
  { id: 12, name: '2人', description: null, color: '#fb923c', categoryId: 1, categoryName: '人数', createdAt: '2026-09-01 10:00', updatedAt: '2026-09-01 10:00' },
  { id: 13, name: '多人', description: null, color: '#fdba74', categoryId: 1, categoryName: '人数', createdAt: '2026-09-01 10:00', updatedAt: '2026-09-01 10:00' },
  { id: 21, name: '客厅', description: null, color: '#06b6d4', categoryId: 2, categoryName: '场景', createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 22, name: '车内', description: null, color: '#0ea5e9', categoryId: 2, categoryName: '场景', createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 23, name: '会议室', description: null, color: '#38bdf8', categoryId: 2, categoryName: '场景', createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 24, name: '车载', description: null, color: '#22d3ee', categoryId: 2, categoryName: '场景', createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 25, name: '会议', description: null, color: '#67e8f9', categoryId: 2, categoryName: '场景', createdAt: '2026-09-01 10:05', updatedAt: '2026-09-01 10:05' },
  { id: 31, name: '中文', description: null, color: '#8b5cf6', categoryId: 3, categoryName: '语种', createdAt: '2026-09-01 10:10', updatedAt: '2026-09-01 10:10' },
  { id: 32, name: '英文', description: null, color: '#a78bfa', categoryId: 3, categoryName: '语种', createdAt: '2026-09-01 10:10', updatedAt: '2026-09-01 10:10' },
  { id: 41, name: '安静', description: null, color: '#84cc16', categoryId: 4, categoryName: '噪声环境', createdAt: '2026-09-01 10:15', updatedAt: '2026-09-01 10:15' },
  { id: 42, name: '嘈杂', description: null, color: '#a3e635', categoryId: 4, categoryName: '噪声环境', createdAt: '2026-09-01 10:15', updatedAt: '2026-09-01 10:15' },
  { id: 43, name: '音乐', description: null, color: '#bef264', categoryId: 4, categoryName: '噪声环境', createdAt: '2026-09-01 10:15', updatedAt: '2026-09-01 10:15' },
  { id: 51, name: '音箱', description: null, color: '#14b8a6', categoryId: 5, categoryName: '设备类型', createdAt: '2026-09-01 10:20', updatedAt: '2026-09-01 10:20' },
  { id: 52, name: '手机', description: null, color: '#2dd4bf', categoryId: 5, categoryName: '设备类型', createdAt: '2026-09-01 10:20', updatedAt: '2026-09-01 10:20' },
  { id: 61, name: '1m', description: null, color: '#6366f1', categoryId: 6, categoryName: '距离', createdAt: '2026-09-01 10:25', updatedAt: '2026-09-01 10:25' },
  { id: 62, name: '2m', description: null, color: '#818cf8', categoryId: 6, categoryName: '距离', createdAt: '2026-09-01 10:25', updatedAt: '2026-09-01 10:25' },
  { id: 63, name: '3m', description: null, color: '#a5b4fc', categoryId: 6, categoryName: '距离', createdAt: '2026-09-01 10:25', updatedAt: '2026-09-01 10:25' },
]

/** 用例分组（group.py GroupItem：id/name/description/algorithm_type/created_at/updated_at/test_case_count） */
export const MOCK_GROUPS: TestCaseGroup[] = [
  { id: 'g1', name: '智能音箱功能测试', description: '智能音箱核心语音功能回归', algorithmType: 'asr-v3', createdAt: '2026-09-01 11:00', updatedAt: '2026-10-14 16:20', testCaseCount: 5 },
  { id: 'g2', name: '车载语音交互', description: '车载场景语音交互链路', algorithmType: 'asr-v3', createdAt: '2026-09-02 09:30', updatedAt: '2026-10-12 15:10', testCaseCount: 3 },
  { id: 'g3', name: '手机助手场景', description: '手机端语音助手专项', algorithmType: 'asr-stream', createdAt: '2026-09-03 14:00', updatedAt: '2026-10-11 10:40', testCaseCount: 3 },
  { id: 'g4', name: '会议转写测试', description: '多人会议场景转写评估', algorithmType: 'eval-ensemble', createdAt: '2026-09-05 10:00', updatedAt: '2026-10-10 18:05', testCaseCount: 2 },
]

/** 评估维度选项（evaluation.py DimensionItem 子集；facet 用主维度，type≠sub） */
export const MOCK_DIMENSIONS: EvaluationDimensionItem[] = [
  { id: 1, name: '识别准确率', description: '语音识别整体准确率', dimensionType: 'main', parentDimensionId: null, categoryId: null, weight: 9, status: true, createdAt: '2026-08-01 09:00', updatedAt: '2026-09-20 11:00' },
  { id: 2, name: '语义理解', description: '指令语义理解正确性', dimensionType: 'main', parentDimensionId: null, categoryId: null, weight: 7, status: true, createdAt: '2026-08-01 09:00', updatedAt: '2026-09-20 11:00' },
  { id: 3, name: '唤醒成功率', description: '唤醒词响应成功率', dimensionType: 'main', parentDimensionId: null, categoryId: null, weight: 6, status: true, createdAt: '2026-08-02 10:00', updatedAt: '2026-09-21 14:00' },
  { id: 4, name: '响应时延', description: '指令响应端到端时延', dimensionType: 'main', parentDimensionId: null, categoryId: null, weight: 5, status: true, createdAt: '2026-08-02 10:00', updatedAt: '2026-09-21 14:00' },
  { id: 11, name: '字准率', description: '逐字识别准确率', dimensionType: 'sub', parentDimensionId: 1, categoryId: null, weight: 8, status: true, createdAt: '2026-08-01 09:05', updatedAt: '2026-09-20 11:00' },
  { id: 12, name: '句准率', description: '整句识别准确率', dimensionType: 'sub', parentDimensionId: 1, categoryId: null, weight: 7, status: true, createdAt: '2026-08-01 09:05', updatedAt: '2026-09-20 11:00' },
]

/**
 * 用例编辑抽屉维度选项（§5.1 轮次评估步骤 / §5.1.2 整体评估共用，Dimension 全字段子集）。
 * 含主/子层级（main/sub + parentDimensionId）与 LLM Judge 维度（派生布尔 llmJudge，结果类型仍是
 * 数值/布尔/文本的整数）+ 关联算法，
 * 按当前算法过滤（associated_algorithms 口径）；接线后收敛 GET /evaluation/dimensions 同源。
 */
export const MOCK_CASE_DIMENSIONS: Dimension[] = [
  { id: 1, name: '识别准确率', description: '语音识别整体准确率', dimensionType: 'main', parentDimensionId: null, categoryId: 1, resultType: 1, weight: 9, status: true, associatedAlgorithms: [{ algorithmType: 'asr-v3', isDefault: true, weight: 9 }, { algorithmType: 'asr-stream', isDefault: false, weight: 8 }] },
  { id: 11, name: '字准率', description: '逐字识别准确率', dimensionType: 'sub', parentDimensionId: 1, categoryId: 1, resultType: 1, weight: 8, status: true },
  { id: 12, name: '句准率', description: '整句识别准确率', dimensionType: 'sub', parentDimensionId: 1, categoryId: 1, resultType: 1, weight: 7, status: true },
  { id: 2, name: '语义理解', description: '指令语义理解与执行正确性', dimensionType: 'main', parentDimensionId: null, categoryId: 2, resultType: 1, llmJudge: true, weight: 7, status: true, associatedAlgorithms: [{ algorithmType: 'asr-v3', isDefault: false, weight: 7 }, { algorithmType: 'eval-ensemble', isDefault: true, weight: 8 }] },
  { id: 21, name: '指令完成度', description: '指令完整执行程度', dimensionType: 'sub', parentDimensionId: 2, categoryId: 2, resultType: 1, llmJudge: true, weight: 6, status: true },
  { id: 3, name: '唤醒成功率', description: '唤醒词响应成功率', dimensionType: 'main', parentDimensionId: null, categoryId: 3, resultType: 1, weight: 6, status: true, associatedAlgorithms: [{ algorithmType: 'asr-stream', isDefault: true, weight: 6 }] },
  { id: 4, name: '响应时延', description: '指令响应端到端时延', dimensionType: 'main', parentDimensionId: null, categoryId: 3, resultType: 1, weight: 5, status: true, associatedAlgorithms: [{ algorithmType: 'asr-stream', isDefault: false, weight: 5 }, { algorithmType: 'eval-ensemble', isDefault: false, weight: 4 }] },
  { id: 5, name: '对话连贯性', description: '多轮对话上下文一致性', dimensionType: 'main', parentDimensionId: null, categoryId: 2, resultType: 1, llmJudge: true, weight: 6, status: true, associatedAlgorithms: [{ algorithmType: 'eval-ensemble', isDefault: true, weight: 6 }] },
]

/**
 * 评估维度分类（evaluation.py CategoryItem；用例编辑抽屉 mock 维度按 categoryId 归属，
 * DimensionPicker 分类分组组头用——负责人 2026-10-19「评估维度已经分组/分类了」口径）。
 */
export const MOCK_EVALUATION_CATEGORIES: EvaluationCategory[] = [
  { id: 1, name: '识别质量', description: '语音识别准确率相关指标', icon: 'fas fa-microphone', createdAt: '2026-08-01 09:00', updatedAt: '2026-09-20 11:00' },
  { id: 2, name: '语义理解', description: '指令语义理解与执行正确性', icon: 'fas fa-brain', createdAt: '2026-08-01 09:00', updatedAt: '2026-09-20 11:00' },
  { id: 3, name: '响应体验', description: '唤醒与响应端到端体验', icon: 'fas fa-bolt', createdAt: '2026-08-02 10:00', updatedAt: '2026-09-21 14:00' },
]

/**
 * 用例列表 mock（schemas/testcase.py TestCaseListItem 全字段实测）。
 * 含回收站项（tc-017 deleted）与收藏项（isFavorite）；分组含未分组（groupId null）。
 */
export const MOCK_TEST_CASES: TestCaseListItem[] = [
  {
    id: 'tc-001', name: '智能音箱-播放音乐-中文-客厅', description: '客厅环境播放中文音乐，验证连续指令', groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e',
    tags: ['音箱', '中文', '客厅', '音乐', '1m'], algorithmType: 'asr-v3', createdAt: '2026-09-10 10:00', updatedAt: '2026-10-15 09:32',
    isFavorite: true, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 156, rounds: 2,
  },
  {
    id: 'tc-002', name: '智能音箱-调节音量-2人', description: '两人对话场景下调节音量', groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e',
    tags: ['音箱', '中文', '2人', '安静'], algorithmType: 'asr-v3', createdAt: '2026-09-11 09:00', updatedAt: '2026-10-14 16:20',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 48, rounds: 1,
  },
  {
    id: 'tc-003', name: '智能音箱-语音点歌-嘈杂环境', description: '嘈杂环境下语音点歌稳定性', groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e',
    tags: ['音箱', '中文', '嘈杂'], algorithmType: 'asr-stream', createdAt: '2026-09-12 14:00', updatedAt: '2026-10-14 10:05',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 210, rounds: 3,
  },
  {
    id: 'tc-004', name: '智能音箱-天气查询-1人', description: '单人天气查询 API 通道', groupId: 'g1', groupName: '智能音箱功能测试', type: 'api',
    tags: ['音箱', '1人', '安静', '2m'], algorithmType: 'asr-v3', createdAt: '2026-09-13 10:30', updatedAt: '2026-10-13 09:50',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 12, rounds: 1,
  },
  {
    id: 'tc-005', name: '智能音箱-闹钟设置-音乐干扰', description: '音乐背景下的闹钟设置指令', groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e',
    tags: ['音箱', '2人', '音乐', '3m'], algorithmType: 'asr-v3', createdAt: '2026-09-14 08:00', updatedAt: '2026-10-12 11:30',
    isFavorite: true, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 132, rounds: 2,
  },
  {
    id: 'tc-006', name: '车载-导航指令-车内-1人', description: '车内导航指令识别', groupId: 'g2', groupName: '车载语音交互', type: 'e2e',
    tags: ['车载', '车内', '1人', '嘈杂', '1m'], algorithmType: 'asr-v3', createdAt: '2026-09-15 09:00', updatedAt: '2026-10-12 15:10',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 96, rounds: 2,
  },
  {
    id: 'tc-007', name: '车载-电话接听-音乐场景', description: '音乐播放中接听电话指令', groupId: 'g2', groupName: '车载语音交互', type: 'api',
    tags: ['车载', '音乐'], algorithmType: 'asr-stream', createdAt: '2026-09-16 10:00', updatedAt: '2026-10-11 16:40',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 30, rounds: 1,
  },
  {
    id: 'tc-008', name: '车载-空调调节-多人', description: '多人对话时空调调节指令', groupId: 'g2', groupName: '车载语音交互', type: 'e2e',
    tags: ['车载', '多人', '车内'], algorithmType: 'asr-v3', createdAt: '2026-09-17 11:00', updatedAt: '2026-10-10 09:20',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 84, rounds: 2,
  },
  {
    id: 'tc-009', name: '手机-语音助手-唤醒', description: '手机语音助手唤醒成功率专项', groupId: 'g3', groupName: '手机助手场景', type: 'e2e',
    tags: ['手机', '1人', '安静', '2m'], algorithmType: 'asr-stream', createdAt: '2026-09-18 09:30', updatedAt: '2026-10-11 10:40',
    isFavorite: true, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 60, rounds: 2,
  },
  {
    id: 'tc-010', name: '手机-发送消息-英文', description: '英文语音发送消息', groupId: 'g3', groupName: '手机助手场景', type: 'api',
    tags: ['手机', '英文', '2人'], algorithmType: 'asr-v3', createdAt: '2026-09-19 13:00', updatedAt: '2026-10-09 17:30',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 24, rounds: 1,
  },
  {
    id: 'tc-011', name: '手机-日程提醒-会议室', description: '会议室场景日程提醒', groupId: 'g3', groupName: '手机助手场景', type: 'e2e',
    tags: ['手机', '会议室'], algorithmType: 'asr-v3', createdAt: '2026-09-20 09:00', updatedAt: '2026-10-08 10:15',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 40, rounds: 1,
  },
  {
    id: 'tc-012', name: '会议-双人转写-中文', description: '双人中文会议转写评估', groupId: 'g4', groupName: '会议转写测试', type: 'e2e',
    tags: ['会议', '2人', '中文', '会议室', '3m'], algorithmType: 'eval-ensemble', createdAt: '2026-09-21 10:00', updatedAt: '2026-10-10 18:05',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 180, rounds: 2,
  },
  {
    id: 'tc-013', name: '会议-英文转写-多人', description: '多人英文会议转写评估', groupId: 'g4', groupName: '会议转写测试', type: 'api',
    tags: ['会议', '多人', '英文'], algorithmType: 'eval-ensemble', createdAt: '2026-09-22 14:00', updatedAt: '2026-10-09 15:00',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 66, rounds: 1,
  },
  {
    id: 'tc-014', name: '临时-接口稳定性回归', description: 'API 通道稳定性回归用例', groupId: null, groupName: null, type: 'api',
    tags: [], algorithmType: 'asr-stream', createdAt: '2026-09-23 09:00', updatedAt: '2026-10-07 10:00',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 20, rounds: 1,
    // §3.3.2 预览置灰演示：无关联音频文件
    audioCount: 0,
  },
  {
    id: 'tc-015', name: '临时-唤醒率对比', description: '不同环境唤醒率对比', groupId: null, groupName: null, type: 'e2e',
    tags: ['1人'], algorithmType: 'asr-v3', createdAt: '2026-09-24 09:00', updatedAt: '2026-10-06 14:20',
    isFavorite: false, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 98, rounds: 2,
  },
  {
    id: 'tc-016', name: '临时-长文本转写', description: '长文本会议转写边界验证', groupId: null, groupName: null, type: 'e2e',
    tags: ['中文', '会议室'], algorithmType: 'eval-ensemble', createdAt: '2026-09-25 09:00', updatedAt: '2026-10-15 08:40',
    isFavorite: true, deleted: false, deletedAt: null, deletedByUserId: null, totalDuration: 240, rounds: 3,
  },
  {
    id: 'tc-017', name: '已删除-旧版唤醒测试', description: '旧版唤醒链路回归（已移入回收站）', groupId: 'g1', groupName: '智能音箱功能测试', type: 'e2e',
    tags: ['音箱', '1人'], algorithmType: 'asr-v3', createdAt: '2026-08-30 09:00', updatedAt: '2026-09-30 11:00',
    isFavorite: false, deleted: true, deletedAt: '2026-10-10 14:20', deletedByUserId: 1001, totalDuration: 45, rounds: 1,
  },
]

/** 未分组虚拟组计数（INT-249 口径：总数 − Σ分组计数；回收站/收藏态下由 api 层按可见数据集计算） */
export const MOCK_UNGROUPED_COUNT = MOCK_TEST_CASES.filter(
  (c) => !c.deleted && c.groupId === null
).length
