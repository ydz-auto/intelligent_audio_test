/**
 * 分析结论（15_报告域.md §3.3.3，AnalysisEditorComponent 对位）。
 * 非编辑态 sanitizeConclusion 清洗后渲染（空则占位「暂无分析结论...」）；
 * 编辑态 Textarea field-sizing-content；保存 → PUT /reports/{id} analysis（双写兼容）。
 * 结论标签池默认折叠（性能优化/功能改进/稳定性问题/兼容性问题/建议改进）。
 */
import { Check, ChevronDown, Pencil, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Textarea } from '@/components/ui/textarea'
import {
  DEFAULT_CONCLUSION_TAGS,
  sanitizeConclusion,
} from '@/application/report-view/use-report-analysis'
import { cn } from '@/lib/utils'

interface AnalysisEditorProps {
  title: string
  analysis?: string
  readonly?: boolean
  editing: boolean
  onStartEditing: () => void
  onExitEditing: () => void
  onSaveAnalysis: (content: string) => void
}

export function AnalysisEditor({
  title,
  analysis,
  readonly,
  editing,
  onStartEditing,
  onExitEditing,
  onSaveAnalysis,
}: AnalysisEditorProps) {
  const [draft, setDraft] = useState(analysis ?? '')
  const [tagsOpen, setTagsOpen] = useState(false)
  const hasAnalysis = Boolean(analysis && sanitizeConclusion(analysis).trim())

  // 报告头「保存」退出编辑模式时提交未保存草稿（INT-503：编辑/保存一致——退出编辑不再丢改动）；
  // 「取消」置 cancelRef，跳过提交
  const lastSavedRef = useRef<string | null>(null)
  const cancelRef = useRef(false)
  const prevEditingRef = useRef(editing)
  useEffect(() => {
    const wasEditing = prevEditingRef.current
    prevEditingRef.current = editing
    if (wasEditing && !editing) {
      if (cancelRef.current) {
        cancelRef.current = false
        return
      }
      if (lastSavedRef.current !== draft) {
        lastSavedRef.current = draft
        onSaveAnalysis(draft)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing])

  const handleStartEditing = () => {
    setDraft(analysis ?? '')
    onStartEditing()
  }

  return (
    <Collapsible open className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>{title}</span>
          <ChevronDown aria-hidden='true' className='text-muted-foreground size-4' />
        </CollapsibleTrigger>
        {!readonly && !editing && (
          <Button variant='outline' size='sm' onClick={handleStartEditing}>
            <Pencil aria-hidden='true' className='size-3.5' />
            编辑
          </Button>
        )}
      </div>

      <CollapsibleContent>
        {editing ? (
          <div className='space-y-2'>
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder='请输入分析结论...'
              className='min-h-24 max-h-96 w-full field-sizing-content'
            />
            <div className='flex items-center gap-2'>
              <Button
                size='sm'
                onClick={() => {
                  lastSavedRef.current = draft
                  onSaveAnalysis(draft)
                  onExitEditing()
                }}
              >
                <Check aria-hidden='true' className='size-3.5' />
                保存
              </Button>
              <Button
                variant='ghost'
                size='sm'
                onClick={() => {
                  cancelRef.current = true
                  onExitEditing()
                }}
              >
                <X aria-hidden='true' className='size-3.5' />
                取消
              </Button>
              <div className='flex-1' />
              <Button
                variant='ghost'
                size='sm'
                onClick={() => setTagsOpen((v) => !v)}
              >
                结论标签
                <ChevronDown
                  aria-hidden='true'
                  className={cn('size-3.5 transition-transform', tagsOpen && 'rotate-180')}
                />
              </Button>
            </div>
            {tagsOpen && (
              <div className='flex flex-wrap gap-1.5 pt-1'>
                {DEFAULT_CONCLUSION_TAGS.map((tag) => (
                  <Badge key={tag} variant='outline' className='cursor-pointer'>
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ) : hasAnalysis ? (
          <div
            className='text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap'
            dangerouslySetInnerHTML={{ __html: sanitizeConclusion(analysis) }}
          />
        ) : (
          <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
            暂无分析结论，点击编辑按钮添加分析内容
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
