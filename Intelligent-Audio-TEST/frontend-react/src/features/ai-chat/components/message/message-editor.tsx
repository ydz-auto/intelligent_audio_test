/**
 * 消息编辑器（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI playground-message-editor）：
 * CodeBlockEditor markdown rows=8 + 「编辑」标题 + 未保存提示 + 保存并重发/保存/重置/取消
 * + beforeunload 守卫 + 离开确认 ConfirmDialog。
 */
import { Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { CodeBlockEditor } from '@/components/ai-elements/code-block'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { getCurrentMessageContent } from '@/features/ai-chat/lib/message'
import type { ChatMessage } from '@/domain/models/aiChat'

type MessageEditorProps = {
  editText: string
  message: ChatMessage
  onEditTextChange: (text: string) => void
  onSaveEdit: (newContent: string) => void
  onSaveEditAndSubmit: (newContent: string) => void
  onCancelEdit: (open: boolean) => void
  originalText: string
}

export function MessageEditor({
  editText,
  message,
  onEditTextChange,
  onSaveEdit,
  onSaveEditAndSubmit,
  onCancelEdit,
  originalText,
}: MessageEditorProps) {
  const [leaveOpen, setLeaveOpen] = useState(false)
  const hasChanged = editText !== originalText
  const originalContent = getCurrentMessageContent(message)

  // beforeunload 守卫：有未保存更改时拦截刷新/离开
  useEffect(() => {
    if (!hasChanged) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasChanged])

  const handleCancel = () => {
    if (hasChanged) {
      setLeaveOpen(true)
    } else {
      onCancelEdit(false)
    }
  }

  return (
    <div className='w-full'>
      <CodeBlockEditor
        hasChanged={hasChanged}
        onChange={onEditTextChange}
        onCancel={handleCancel}
        onReset={() => onEditTextChange(originalContent)}
        onSave={() => onSaveEdit(editText)}
        placeholder='编辑消息内容…'
        rows={8}
        title='编辑'
        value={editText}
        actions={
          hasChanged ? (
            <Button
              className='h-7 gap-1 px-2.5 text-xs'
              onClick={() => onSaveEditAndSubmit(editText)}
              size='sm'
              type='button'
            >
              <Send className='size-3.5' />
              保存并重发
            </Button>
          ) : undefined
        }
      />
      <ConfirmDialog
        desc='你有未保存的更改，确定要离开吗？'
        open={leaveOpen}
        cancelBtnText='留在此页'
        confirmText='离开'
        handleConfirm={() => onCancelEdit(false)}
        onOpenChange={setLeaveOpen}
        title='放弃未保存的更改？'
      />
    </div>
  )
}
