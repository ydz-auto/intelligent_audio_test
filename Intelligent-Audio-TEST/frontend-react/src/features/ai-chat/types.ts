/**
 * AI 对话页类型（interfaces 层；08_AI对话页.md §7）。
 * 领域模型在 domain/models/aiChat.ts，本文件做页面级再导出与派生类型。
 */
export type {
  AgentToolCall,
  AgentToolStatus,
  ChatConfig,
  ChatDocumentChange,
  ChatMessage,
  ChatMessageRole,
  ChatMessageStatus,
  ChatParameterEnabled,
  ChatParameterKey,
  ChatReasoning,
  ChatSourceRef,
  ReportContextOption,
  ReportContextType,
} from '@/domain/models/aiChat'
