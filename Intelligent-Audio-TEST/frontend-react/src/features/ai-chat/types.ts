/**
 * AI 对话页类型（interfaces 层；08_AI对话页.md §7）。
 * 领域模型在 domain/models/aiChat.ts，本文件做页面级再导出与派生类型。
 * 2026-10-17 新口径：ChatParameterKey/ChatParameterEnabled 随模型参数注册表整块移除。
 */
export type {
  AgentToolCall,
  AgentToolStatus,
  ChatConfig,
  ChatDocumentChange,
  ChatMessage,
  ChatMessageRole,
  ChatMessageStatus,
  ChatReasoning,
  ChatSourceRef,
  LlmProvider,
  ReportContextOption,
  ReportContextType,
} from '@/domain/models/aiChat'
