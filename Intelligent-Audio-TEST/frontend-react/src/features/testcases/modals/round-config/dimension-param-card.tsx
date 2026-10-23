/**
 * 已选维度参数卡（用例编辑抽屉 §5.1 / §5.1.2 共用）。
 * 每维度：名称 + LLM Judge 徽章 + 移除钮；权重 number 0-100 默认 50 + 阈值 number 0-100 默认 80
 * （非 LLM Judge）；LLM Judge 时 模型 Select + Prompt 模板 Select——选项来源改为
 * infrastructure/api/llm-judge-options（后端口径，当前留桩待接线；INT-1658 去掉组件内硬编码）。
 * 数据契约 config.dimensions 项 = { id, name, weight, threshold, (llmJudgeConfig: {model, promptTemplate}) }
 */
import { SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  getLlmJudgeOptions,
  withCurrentOption,
} from '@/infrastructure/api/llm-judge-options'

export interface DimensionParamValue {
  weight: number
  threshold: number
  model?: string
  promptTemplate?: string
}

/** LLM Judge 可选值（后端口径；infrastructure 层留桩待接线，INT-1658 去掉组件内硬编码） */
const LLM_OPTIONS = getLlmJudgeOptions()

export function DimensionParamCard({
  dimension,
  params,
  onChange,
  onRemove,
}: {
  dimension: Dimension
  params: DimensionParamValue
  onChange: (patch: Partial<DimensionParamValue>) => void
  onRemove: () => void
}) {
  const llmJudge = dimension.resultType === 'llm_judge'
  // 默认值：维度自身 llmJudgeConfig 优先，缺省取后端候选集首项
  const [model, setModel] = useState(
    params.model ?? dimension.llmJudgeConfig?.model ?? LLM_OPTIONS.models[0] ?? ''
  )
  const [prompt, setPrompt] = useState(
    params.promptTemplate ??
      dimension.llmJudgeConfig?.promptTemplate ??
      LLM_OPTIONS.promptTemplates[0] ??
      ''
  )

  // 存量值可能不在后端候选集：并入选项保证回显（否则 Select 显示空白）
  const modelOptions = withCurrentOption(LLM_OPTIONS.models, model)
  const promptOptions = withCurrentOption(LLM_OPTIONS.promptTemplates, prompt)

  const commit = (patch: Partial<DimensionParamValue>) => {
    onChange(patch)
    if (patch.model) setModel(patch.model)
    if (patch.promptTemplate) setPrompt(patch.promptTemplate)
  }

  return (
    <div className='bg-background ring-foreground/10 rounded-lg p-3 ring-1'>
      <div className='flex items-center gap-2'>
        <SlidersHorizontal aria-hidden='true' className='text-muted-foreground size-4' />
        <span className='text-sm font-medium'>{dimension.name}</span>
        {llmJudge && (
          <Badge variant='outline' className='gap-1 rounded-md px-1.5 text-[11px]'>
            LLM Judge
          </Badge>
        )}
        <Button
          type='button'
          variant='ghost'
          size='icon-sm'
          aria-label={`移除维度 ${dimension.name}`}
          className='hover:text-destructive ms-auto size-7'
          onClick={onRemove}
        >
          ✕
        </Button>
      </div>
      <div className='mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label className='text-sm'>权重</Label>
          <Input
            type='number'
            min={0}
            max={100}
            step={1}
            value={params.weight}
            onChange={(e) => commit({ weight: Number(e.target.value) })}
            className='h-8'
          />
        </div>
        {!llmJudge ? (
          <div className='space-y-1.5'>
            <Label className='text-sm'>阈值</Label>
            <Input
              type='number'
              min={0}
              max={100}
              step={1}
              value={params.threshold}
              onChange={(e) => commit({ threshold: Number(e.target.value) })}
              className='h-8'
            />
          </div>
        ) : (
          <>
            <div className='space-y-1.5'>
              <Label className='text-sm'>模型</Label>
              <Select
                value={model}
                onValueChange={(v) => commit({ model: v ?? undefined })}
                items={modelOptions.map((m) => ({ value: m, label: m }))}
              >
                <SelectTrigger size='sm' className='h-8 w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-1.5'>
              <Label className='text-sm'>Prompt 模板</Label>
              <Select
                value={prompt}
                onValueChange={(v) => commit({ promptTemplate: v ?? undefined })}
                items={promptOptions.map((t) => ({ value: t, label: t }))}
              >
                <SelectTrigger size='sm' className='h-8 w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {promptOptions.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
