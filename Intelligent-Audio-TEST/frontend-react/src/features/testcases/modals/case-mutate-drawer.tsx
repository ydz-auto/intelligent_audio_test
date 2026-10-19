/**
 * 新增/编辑用例抽屉（11_用例域.md §5.1，Sheet `sm:max-w-[1280px]`，testcase:create/update）。
 * 单栏纵向分节（节间 border-b）：基本信息（双列栅格）/标签（TagInput chips + 已有标签建议）/
 * 描述/关联算法/轮次配置（左 RoundNav 180px + 右步骤区横向锚点 Tabs line：
 * 算法参数→音频列表→噪声与干扰→评估维度→参考参数，五步全字段表单）/
 * 【评估配置·默认折叠】评估策略节（§5.1.3 折叠节，默认收起：三模式 RadioGroup + 引用摘要卡 +
 * 用例级覆盖区 + 新建策略内联表单）——INT-592 拆分「用例主体」与「评估配置」两层，
 * 原 §5.1.1 全局背景噪声 / §5.1.2 整体评估维度两常驻节移入策略节（抽屉瘦身一半），
 * GlobalNoiseEditor/OverallEvaluationEditor 改为受控策略字段编辑器。
 * INT-486 用例不分类型口径：头部类型切换（API/E2E）移除——正式类型维度=关联算法。
 * 轮次载荷形态对照 api_gateway/schemas/testcase.py TestCaseConfig.rounds 实测（mock 桩，
 * 接线后替换为 application/testcases mutations）；保存时策略节序列化为 config.evaluationStrategy
 * （serializeEvaluationStrategy，含存量直载字段，§5.1.3 契约）。
 * ⚠️ 实施注意②：addRound 已有轮次时复制上一轮 evaluation（RoundConfigEditor.vue:252-254），
 * 「新轮次默认关闭」严格仅首轮成立——本卡等价移植保持复制行为、不额外重置 enabled。
 */
import { Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import { MOCK_CASE_DIMENSIONS } from '@/infrastructure/mock/testcases-mock'
import {
  RoundNav,
  newRoundEvaluation,
  type RoundDraft,
  type RoundEvaluationDraft,
} from '@/features/testcases/modals/round-config/round-nav'
import { AlgorithmParamsStep } from '@/features/testcases/modals/round-config/algo-params-step'
import { AudioListStep } from '@/features/testcases/modals/round-config/audio-list-step'
import { NoiseInterferenceStep } from '@/features/testcases/modals/round-config/noise-interference-step'
import { EvaluationStep } from '@/features/testcases/modals/round-config/evaluation-step'
import { ReferenceStep } from '@/features/testcases/modals/round-config/reference-step'
import {
  EvaluationStrategyEditor,
  serializeEvaluationStrategy,
  type EvaluationStrategyEditorValue,
} from '@/features/testcases/modals/strategy/evaluation-strategy-editor'
import { useEvaluationStrategies } from '@/application/testcases/useEvaluationStrategies'

const STEPS = ['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'] as const

/** 迷你标签输入（§5.2.1 TagInput 语义：回车/逗号添加 + 已有标签建议区） */
function CaseTagInput({
  value,
  onChange,
  available,
}: {
  value: string[]
  onChange: (next: string[]) => void
  available: TagItem[]
}) {
  const [draft, setDraft] = useState('')

  const add = (name: string) => {
    const trimmed = name.trim()
    if (!trimmed || value.includes(trimmed)) return
    onChange([...value, trimmed])
  }

  const suggestions = available.filter(
    (t) => !value.includes(t.name) && t.name.includes(draft.trim())
  )

  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-center gap-1.5 rounded-lg border p-2'>
        {value.map((name) => (
          <Badge key={name} variant='secondary' className='gap-1 rounded-md px-1.5'>
            {name}
            <button
              type='button'
              aria-label={`移除标签 ${name}`}
              className='hover:text-destructive text-muted-foreground'
              onClick={() => onChange(value.filter((v) => v !== name))}
            >
              ✕
            </button>
          </Badge>
        ))}
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault()
              add(draft)
              setDraft('')
            }
          }}
          placeholder='输入标签，按回车或逗号添加'
          className='h-7 w-full min-w-40 border-none shadow-none focus-visible:ring-0 sm:w-56'
        />
      </div>
      {suggestions.length > 0 && (
        <div className='flex flex-wrap gap-1.5'>
          {suggestions.slice(0, 8).map((tag) => (
            <button
              key={tag.id}
              type='button'
              className='hover:bg-accent flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs transition-colors'
              onClick={() => {
                add(tag.name)
                setDraft('')
              }}
              style={{ color: tag.color ?? undefined }}
            >
              <span
                aria-hidden='true'
                className='size-1.5 rounded-full'
                style={{ backgroundColor: tag.color ?? '#94a3b8' }}
              />
              {tag.name}
              <span className='text-muted-foreground text-[10px]'>
                {tag.categoryName}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function CaseMutateDrawer({
  open,
  onOpenChange,
  caseItem,
  groups,
  tags,
  presetGroupId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem: TestCaseListItem | null
  groups: TestCaseGroup[]
  tags: TagItem[]
  /** 新建态预填分组（分组视图「新增用例到此分组」入口；编辑态忽略） */
  presetGroupId?: string | null
}) {
  const isEdit = caseItem != null
  const strategiesQuery = useEvaluationStrategies()
  const strategies = strategiesQuery.data ?? []
  const [step, setStep] = useState<(typeof STEPS)[number]>('算法参数')
  const [nameValue, setNameValue] = useState(caseItem?.name ?? '')
  const [tagValue, setTagValue] = useState<string[]>(caseItem?.tags ?? [])
  const [groupValue, setGroupValue] = useState(caseItem?.groupId ?? presetGroupId ?? '')
  const [newGroupName, setNewGroupName] = useState('')
  const [algorithmType, setAlgorithmType] = useState(caseItem?.algorithmType ?? '')
  const { options: algorithmOptions, isLoading: loadingAlgorithms } =
    useAlgorithmOptions()
  const [rounds, setRounds] = useState<RoundDraft[]>([
    {
      number: 1,
      audioCount: 2,
      dimensionCount: 1,
      evaluation: { enabled: true, selectedIds: [1], params: { 1: { weight: 50, threshold: 80 } } },
    },
    {
      number: 2,
      audioCount: 1,
      dimensionCount: 2,
      evaluation: {
        enabled: true,
        selectedIds: [1, 11],
        params: { 1: { weight: 50, threshold: 80 }, 11: { weight: 50, threshold: 80 } },
      },
    },
  ])
  const [activeRound, setActiveRound] = useState(1)
  /** 评估策略节值（§5.1.3；保存时序列化为 config.evaluationStrategy / 存量直载字段） */
  const [strategyValue, setStrategyValue] = useState<EvaluationStrategyEditorValue | null>(null)

  const groupOptions = [
    ...groups.map((g) => ({ value: g.id, label: g.name })),
    { value: '__new__', label: '+ 新建分组' },
  ]

  const nextRoundNumber = () =>
    rounds.length ? Math.max(...rounds.map((r) => r.number)) + 1 : 1

  const addRound = () => {
    const number = nextRoundNumber()
    setRounds((prev) => {
      // ⚠️ 实施注意②：已有轮次时复制上一轮 evaluation（含 enabled），不额外重置
      const src = prev.length > 0 ? prev[prev.length - 1].evaluation : null
      const evaluation: RoundEvaluationDraft = src
        ? {
            ...src,
            selectedIds: [...src.selectedIds],
            params: { ...src.params },
          }
        : newRoundEvaluation()
      return [...prev, { number, audioCount: 0, dimensionCount: 0, evaluation }]
    })
    setActiveRound(number)
  }

  const copyRound = () => {
    const src = rounds.find((r) => r.number === activeRound)
    if (!src) return
    const number = nextRoundNumber()
    setRounds((prev) => [
      ...prev,
      {
        ...src,
        number,
        evaluation: {
          ...src.evaluation,
          selectedIds: [...src.evaluation.selectedIds],
          params: { ...src.evaluation.params },
        },
      },
    ])
    setActiveRound(number)
  }

  const deleteRound = (number: number) => {
    setRounds((prev) => {
      const next = prev.filter((r) => r.number !== number)
      if (activeRound === number) setActiveRound(next[0]?.number ?? 1)
      return next
    })
  }

  const updateEvaluation = (number: number | undefined, evaluation: RoundEvaluationDraft) => {
    if (number == null) return
    setRounds((prev) =>
      prev.map((r) =>
        r.number === number
          ? { ...r, evaluation, dimensionCount: evaluation.selectedIds.length }
          : r
      )
    )
  }

  const activeRoundDraft = rounds.find((r) => r.number === activeRound) ?? rounds[0]

  // INT-588：自动生成需真实读写名称框。抽屉组件常驻渲染（弹窗群内，Sheet 内容关闭时才卸载），
  // useState 初始值在页面加载（caseItem=null）时已定格；打开时按 caseItem 回填名称/标签，
  // 编辑态原名与既有标签不丢（等价 defaultValue 装载时机的行为）。
  useEffect(() => {
    if (open) {
      setNameValue(caseItem?.name ?? '')
      setTagValue(caseItem?.tags ?? [])
    }
  }, [open, caseItem])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='w-full sm:max-w-[1280px]'>
        <SheetHeader className='border-b'>
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div>
              <SheetTitle>{isEdit ? '编辑测试用例' : '新增测试用例'}</SheetTitle>
              <SheetDescription>
                {isEdit
                  ? `正在编辑「${caseItem?.name}」，配置分组、标签与关联算法`
                  : '配置用例名称、分组、标签与关联算法'}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <ScrollArea className='min-h-0 flex-1'>
          <div className='space-y-6 p-4'>
            {/* 基本信息（双列栅格） */}
            <section className='grid gap-x-6 gap-y-4 sm:grid-cols-2'>
              <div className='space-y-1.5'>
                <Label htmlFor='case-name'>用例名称 *</Label>
                <div className='flex gap-2'>
                  <Input
                    id='case-name'
                    value={nameValue}
                    onChange={(e) => setNameValue(e.target.value)}
                    placeholder='请输入用例名称'
                    className='h-8'
                  />
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='h-8 shrink-0 gap-1'
                    onClick={() => {
                      if (tagValue.length === 0) {
                        toast.warning('请先添加标签后再自动生成名称')
                        return
                      }
                      const generated = [...tagValue]
                        .sort((a, b) => a.localeCompare(b, 'zh-CN'))
                        .join('-')
                      setNameValue(generated)
                      toast.success(`已按标签升序自动生成名称「${generated}」`)
                    }}
                  >
                    <Sparkles aria-hidden='true' className='size-3.5' />
                    自动生成
                  </Button>
                </div>
              </div>
              <div className='space-y-1.5'>
                <Label>所属分组</Label>
                <Select
                  value={groupValue}
                  onValueChange={(v) => setGroupValue(v ?? '')}
                >
                  <SelectTrigger size='sm' className='h-8 w-full'>
                    <SelectValue placeholder='请选择分组' />
                  </SelectTrigger>
                  <SelectContent>
                    {groupOptions.map((g) => (
                      <SelectItem key={g.value} value={g.value}>
                        {g.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {groupValue === '__new__' && (
                  <Input
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder='输入新分组名称'
                    className='mt-1.5 h-8'
                    aria-label='新分组名称'
                  />
                )}
              </div>
            </section>

            {/* 标签 */}
            <section className='border-border/60 border-t pt-4'>
              <Label className='mb-2'>标签</Label>
              <CaseTagInput value={tagValue} onChange={setTagValue} available={tags} />
            </section>

            {/* 描述 */}
            <section className='border-border/60 border-t pt-4'>
              <Label htmlFor='case-desc' className='mb-2'>
                描述
              </Label>
              <Textarea
                id='case-desc'
                rows={2}
                defaultValue={caseItem?.description ?? ''}
                placeholder='补充用例描述（可选）'
              />
            </section>

            {/* 关联算法 */}
            <section className='border-border/60 border-t pt-4'>
              <Label className='mb-2'>关联算法</Label>
              {loadingAlgorithms ? (
                <div className='flex h-8 w-full items-center gap-2 rounded-md border px-3 text-sm text-muted-foreground sm:w-80'>
                  <Spinner className='size-3.5' />
                  加载算法列表...
                </div>
              ) : (
                <Select value={algorithmType} onValueChange={(v) => setAlgorithmType(v ?? '')}>
                  <SelectTrigger size='sm' className='h-8 w-full sm:w-80'>
                    <SelectValue placeholder='请选择算法' />
                  </SelectTrigger>
                  <SelectContent>
                    {algorithmOptions.map((a) => (
                      <SelectItem key={a.value} value={a.value}>
                        {a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <p className='text-muted-foreground mt-1 text-xs'>
                算法类型决定「算法参数/评估维度」步骤的可用字段与维度过滤。
              </p>
            </section>

            {/* 轮次配置 */}
            <section className='border-border/60 border-t pt-4'>
              <Label className='mb-2 text-base font-medium'>轮次配置</Label>
              <div className='overflow-hidden rounded-lg border'>
                <div className='flex min-h-96 flex-col sm:flex-row'>
                  <RoundNav
                    rounds={rounds}
                    activeRound={activeRound}
                    onSelect={setActiveRound}
                    onAdd={addRound}
                    onCopy={copyRound}
                    onDelete={deleteRound}
                  />
                  {/* 右：步骤区横向锚点 Tabs line */}
                  <div className='min-h-96 flex-1'>
                    <div className='border-border/60 border-b px-3 pt-2'>
                      <Tabs value={step} onValueChange={(v) => setStep(v as (typeof STEPS)[number])}>
                        <TabsList variant='line' className='max-w-full flex-wrap justify-start'>
                          {STEPS.map((s) => (
                            <TabsTrigger key={s} value={s} className='px-2.5'>
                              {s}
                            </TabsTrigger>
                          ))}
                        </TabsList>
                      </Tabs>
                    </div>
                    <div className='px-3 py-3'>
                      <StepBody
                        step={step}
                        activeRound={activeRoundDraft}
                        algorithmType={algorithmType}
                        onEvaluationChange={(evaluation) =>
                          updateEvaluation(activeRoundDraft?.number, evaluation)
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* 评估配置 · 默认折叠「进阶」区（§5.1.3 评估策略节，INT-592 瘦身核心） */}
            <section className='border-border/60 border-t pt-4'>
              <EvaluationStrategyEditor
                key={isEdit && caseItem ? caseItem.id : 'create'}
                dimensions={MOCK_CASE_DIMENSIONS}
                algorithmType={algorithmType}
                onChange={setStrategyValue}
              />
            </section>
          </div>
        </ScrollArea>

        <SheetFooter className='border-t'>
          <div className='flex justify-end gap-2'>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              onClick={() => {
                // 评估策略节 → 用例保存载荷（config.evaluationStrategy / 存量直载字段，§5.1.3 契约）
                const payload = serializeEvaluationStrategy(strategyValue)
                const reference = strategies.find(
                  (s) => String(s.id) === String(strategyValue?.strategyId)
                )
                const overrideCount =
                  (strategyValue?.overrides?.dimensions != null ? 1 : 0) +
                  (strategyValue?.overrides?.backgroundNoise != null ? 1 : 0)
                const summary =
                  strategyValue?.mode === 'reference'
                    ? reference
                      ? overrideCount > 0
                        ? `评估策略：已引用「${reference.name}」并覆盖 ${overrideCount} 项`
                        : `评估策略：已引用「${reference.name}」`
                      : '评估策略：已选择引用模式（待选择策略）'
                    : strategyValue?.mode === 'create'
                      ? `评估策略：内联配置（整体维度 ${payload.dimensions.length} 项 · 噪声 ${payload.backgroundNoise ? '已配置' : '未配置'}）`
                      : '评估策略：未配置'
                // eslint-disable-next-line no-console
                console.log('[CaseMutateDrawer] config payload', payload)
                toast.success(
                  isEdit ? '更新测试用例成功' : '添加测试用例成功',
                  { description: summary }
                )
                onOpenChange(false)
              }}
            >
              保存
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function StepBody({
  step,
  activeRound,
  algorithmType,
  onEvaluationChange,
}: {
  step: (typeof STEPS)[number]
  activeRound: RoundDraft | undefined
  algorithmType: string
  onEvaluationChange: (evaluation: RoundEvaluationDraft) => void
}) {
  switch (step) {
    case '算法参数':
      return <AlgorithmParamsStep algorithmType={algorithmType || null} />
    case '音频列表':
      return <AudioListStep presetCount={activeRound?.audioCount || 1} />
    case '噪声与干扰':
      return <NoiseInterferenceStep />
    case '评估维度':
      return (
        <EvaluationStep
          dimensions={MOCK_CASE_DIMENSIONS}
          algorithmType={algorithmType || null}
          value={activeRound?.evaluation ?? newRoundEvaluation()}
          onChange={onEvaluationChange}
        />
      )
    case '参考参数':
      return <ReferenceStep generated={activeRound !== undefined && activeRound.audioCount > 0} />
  }
}
