/**
 * AI 复核会话文案（19 规范 §7 AI 复核（对话式）全量中文 + §5.2/§5.3/§5.4）。
 * 灵犀Agent 复核会话（内嵌 Dialog）独立会话 scope，与主工作台文案分域。
 */

/** 复核会话标题与头行（§5.2） */
export const AI_REVIEW_SESSION_COPY = {
  title: 'AI 复核',
  subtitle: '由灵犀Agent 对当前评估结果进行复核，可追问，结论供人工确认；不直接修改统计。',
  expandToChat: '展开到 /ai-chat',
  close: '关闭',
  demoBadge: 'Demo',
  demoTooltip: '演示版：对话使用你配置的 LLM 供应商；保存复核结论走后端 AI 复检（真实端点）',
} as const

/** 复核上下文摘要（§5.3 结构化首条 assistant） */
export const AI_REVIEW_CONTEXT_COPY = {
  title: '复核上下文',
  object: '复核对象',
  resultsCount: '设备×结果',
  lowDimension: '低分维度',
  llmComment: 'LLM 评语',
  existingConclusion: '已有 AI 复核结论',
  noExisting: '无',
  loading: '正在加载复核上下文…',
} as const

/** 对话与追问（§5.4） */
export const AI_REVIEW_CHAT_COPY = {
  initialUserPrompt: '请复核该用例的评估结果，给出复核通过/不通过/存疑结论 + 置信度 + 理由。',
  placeholder: '输入追问，例如：为什么判不通过？',
  send: '发送',
  stop: '停止',
  noProviderChat: '未配置 LLM 供应商，请先在「管理供应商」中添加',
  noModel: '请先在模型/供应商切换器中选择模型',
  thinking: '正在分析…',
  error: 'AI 服务响应异常，请重试',
  quickChips: ['为什么判不通过？', '哪个维度失分最多？', '对比其他设备的表现', '给出逐设备复核意见'],
} as const

/** AI 复核结论卡（§5.4 对话结论，供人工参考） */
export const AI_REVIEW_VERDICT_COPY = {
  title: 'AI 复核结论',
  sourceNote: '对话结论供人工参考；「保存复核结论」后以后端 AI 复检落位结果为准。',
  compareTitle: 'AI 判定 vs 原评估判定',
  verdictNotReady: '等待 Agent 给出复核结论…',
} as const

/** 结论落位（§5.5）与记录卡 */
export const AI_REVIEW_RECORD_COPY = {
  save: '保存复核结论',
  saving: 'AI 复核中…',
  saveConfirmTitle: '将本次复核结论写入 AI 复核记录？',
  saveConfirmContent: '保存后将发起后端 AI 复检，落位为 AI 复核记录；人工确认后结论生效。',
  saveConfirm: '保存',
  cancel: '取消',
  saved: 'AI 复核结论已保存',
  recordTitle: 'AI 复核记录',
  status: '状态',
  verdict: '结论',
  confidence: '置信度',
  reasoning: '理由',
  adoptedAt: '已采纳',
  rejectedAt: '已驳回',
  adopt: '采纳为复核结果',
  reject: '驳回',
  later: '稍后处理',
  adoptedDone: '已采纳 AI 复核结论，复核已提交',
  rejectedDone: '已驳回 AI 复核结论，原判定保持不变（记录标记已驳回备查）',
  failed: 'AI 复核失败',
  retry: '重试',
  hasExisting: '该用例已有 AI 复核结论（{time}），可查看或重新复核',
  noRecords: '暂无 AI 复核记录',
} as const
