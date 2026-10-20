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
import { useQueryClient } from '@tanstack/react-query'
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
import type {
  CaseEvaluationStrategy,
  TestCaseBackgroundNoiseItem,
  TestCaseDimensionItem,
} from '@/domain/models/evaluationStrategy'
import { MOCK_CASE_DIMENSIONS, MOCK_EVALUATION_CATEGORIES } from '@/infrastructure/mock/testcases-mock'
import {
  createTestCase,
  updateTestCase,
  type TestCaseMutatePayload,
} from '@/infrastructure/api/testcases-api'
import {
  RoundNav,
  newRoundEvaluation,
  emptyRoundNoise,
  type RoundAlgorithmParamItem,
  type RoundDraft,
  type RoundEvaluationDraft,
  type RoundNoiseDraft,
} from '@/features/testcases/modals/round-config/round-nav'
import { AlgorithmParamsStep } from '@/features/testcases/modals/round-config/algo-params-step'
import { AudioListStep } from '@/features/testcases/modals/round-config/audio-list-step'
import { NoiseInterferenceStep } from '@/features/testcases/modals/round-config/noise-interference-step'
import {
  algorithmParamsForRound,
  applyNoiseToRound,
  noiseDraftFromRound,
  serializeVoiceprint,
} from '@/features/testcases/modals/round-config/round-noise-codec'
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

/** 新建态默认轮次（单轮空评估 + 空算法参数/噪声与干扰；rounds 由保存侧序列化为 config.rounds） */
function defaultRounds(): RoundDraft[] {
  return [
    {
      number: 1,
      audioCount: 0,
      dimensionCount: 0,
      evaluation: { enabled: true, selectedIds: [], params: {} },
      algorithmParams: [],
      noise: emptyRoundNoise(),
    },
  ]
}

/** 后端 config.rounds 单轮 → RoundDraft（编辑回填：轮次数 + 音频/维度摘要 + 评估内容 + INT-996 算法参数/噪声与干扰） */
function roundDraftFromConfig(
  raw: Record<string, unknown>,
  index: number,
  paramsForRound: RoundAlgorithmParamItem[]
): RoundDraft {
  const number = Number(raw.round_number ?? raw.roundNumber ?? index + 1)
  const audios = Array.isArray(raw.audios) ? (raw.audios as Array<Record<string, unknown>>) : []
  const evaluation =
    raw.evaluation && typeof raw.evaluation === 'object'
      ? (raw.evaluation as Record<string, unknown>)
      : null
  const dimensions = Array.isArray(evaluation?.dimensions)
    ? (evaluation.dimensions as Array<Record<string, unknown>>)
    : []
  const draft: RoundEvaluationDraft = {
    enabled: evaluation?.enabled !== false,
    selectedIds: dimensions
      .map((d) => Number(d.id))
      .filter((id) => Number.isFinite(id) && id !== 0),
    params: {},
  }
  for (const d of dimensions) {
    const id = Number(d.id)
    if (!Number.isFinite(id) || id === 0) continue
    const llm =
      d.llmJudgeConfig && typeof d.llmJudgeConfig === 'object'
        ? (d.llmJudgeConfig as Record<string, unknown>)
        : null
    draft.params[id] = {
      weight: Number(d.weight ?? 50),
      threshold: Number(d.threshold ?? 80),
      ...(llm?.model != null ? { model: String(llm.model) } : {}),
      ...(llm?.promptTemplate != null ? { promptTemplate: String(llm.promptTemplate) } : {}),
    }
  }
  return {
    number,
    audioCount: audios.length,
    dimensionCount: dimensions.length,
    evaluation: draft,
    algorithmParams: paramsForRound,
    noise: noiseDraftFromRound(raw, paramsForRound),
  }
}

/** 真实 config.rounds → RoundDraft[]（空/缺失回退默认轮次；INT-996 按轮读独立列 algorithmParams） */
function roundsFromConfig(
  config: Record<string, unknown> | null | undefined,
  algorithmParams: unknown
): RoundDraft[] {
  const rawRounds = Array.isArray(config?.rounds)
    ? (config.rounds as Array<Record<string, unknown>>)
    : []
  if (rawRounds.length === 0) return defaultRounds()
  return rawRounds.map((raw, i) =>
    roundDraftFromConfig(raw, i, algorithmParamsForRound(algorithmParams, Number(raw.round_number ?? raw.roundNumber ?? i + 1)))
  )
}

/** RoundDraft[] → 后端 config.rounds（合并原始轮次保留 audios 等；evaluation 序列化为 {enabled, dimensions}；
 *  INT-996 噪声与干扰写入 segment 级 audios[].background_noise/interferers） */
function roundsToConfig(
  drafts: RoundDraft[],
  originalRounds: Array<Record<string, unknown>> | null | undefined
): Array<Record<string, unknown>> {
  return drafts.map((draft) => {
    const orig =
      originalRounds?.find(
        (r) => Number(r.round_number ?? r.roundNumber) === draft.number
      ) ?? null
    // 原始单轮 evaluation（保留 name 等未在抽屉编辑的字段；INT-922 保存不得丢维度名）
    const origEval =
      orig?.evaluation && typeof orig.evaluation === 'object'
        ? (orig.evaluation as Record<string, unknown>)
        : null
    const origDims = Array.isArray(origEval?.dimensions)
      ? (origEval.dimensions as Array<Record<string, unknown>>)
      : []
    const base: Record<string, unknown> = { ...(orig ?? {}) }
    // 独立列字段/round 级 algorithmParams 由 CRUD 服务弹出，round 内不携带（INT-996 口径）
    delete base.algorithmParams
    delete base.algorithm_params
    return applyNoiseToRound(
      {
        ...base,
        round_number: draft.number,
        evaluation: {
          enabled: draft.evaluation.enabled,
          dimensions: draft.evaluation.selectedIds.map((id) => {
            const p = draft.evaluation.params[id]
            const origDim = origDims.find((d) => Number(d.id) === id) ?? null
            return {
              ...(origDim ?? {}),
              id,
              weight: p?.weight ?? Number(origDim?.weight ?? 50),
              threshold: p?.threshold ?? Number(origDim?.threshold ?? 80),
              ...(p?.model || p?.promptTemplate
                ? {
                    llmJudgeConfig: {
                      model: p?.model ?? '',
                      promptTemplate: p?.promptTemplate ?? '',
                    },
                  }
                : {}),
            }
          }),
        },
      },
      draft.noise
    )
  })
}

/**
 * 存量 config → 评估策略节初始值（编辑回填 §5.1.3；config 值内 snake_case 契约 →
 * camelCase Domain，editor 直接消费）。
 * - config.evaluationStrategy（引用态 {strategy_id, overrides}）→ initialValue；
 * - 存量直载 config.dimensions / config.background_noise → legacy 字段（无 strategy 时
 *   等价内联策略，映射「新建策略」模式并提示可另存为复用策略）。
 */
function strategyEditorInitial(
  config: Record<string, unknown> | null | undefined
): {
  initialValue: CaseEvaluationStrategy | null
  legacyDimensions: TestCaseDimensionItem[]
  legacyBackgroundNoise: TestCaseBackgroundNoiseItem | null
} {
  const rawStrategy = config?.evaluationStrategy as
    | { strategy_id?: string | null; overrides?: { dimensions?: TestCaseDimensionItem[]; background_noise?: TestCaseBackgroundNoiseItem | null } }
    | null
  const rawOverrides = rawStrategy?.overrides
  const overrides =
    rawOverrides != null &&
    (rawOverrides.dimensions != null || rawOverrides.background_noise != null)
      ? {
          ...(rawOverrides.dimensions != null ? { dimensions: rawOverrides.dimensions } : {}),
          ...(rawOverrides.background_noise != null
            ? { backgroundNoise: rawOverrides.background_noise }
            : {}),
        }
      : null
  return {
    initialValue: rawStrategy
      ? { strategyId: rawStrategy.strategy_id ?? null, ...(overrides ? { overrides } : {}) }
      : null,
    legacyDimensions: (Array.isArray(config?.dimensions)
      ? config.dimensions
      : []) as TestCaseDimensionItem[],
    legacyBackgroundNoise: (config?.background_noise ?? null) as TestCaseBackgroundNoiseItem | null,
  }
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
  const queryClient = useQueryClient()
  const strategiesQuery = useEvaluationStrategies()
  const strategies = strategiesQuery.data ?? []
  const [step, setStep] = useState<(typeof STEPS)[number]>('算法参数')
  const [nameValue, setNameValue] = useState(caseItem?.name ?? '')
  const [tagValue, setTagValue] = useState<string[]>(caseItem?.tags ?? [])
  const [groupValue, setGroupValue] = useState(caseItem?.groupId ?? presetGroupId ?? '')
  const [newGroupName, setNewGroupName] = useState('')
  const [algorithmType, setAlgorithmType] = useState(caseItem?.algorithmType ?? '')
  const [descriptionValue, setDescriptionValue] = useState(caseItem?.description ?? '')
  const { options: algorithmOptions, isLoading: loadingAlgorithms } =
    useAlgorithmOptions()
  const [rounds, setRounds] = useState<RoundDraft[]>(defaultRounds())
  const [activeRound, setActiveRound] = useState(1)
  /** 评估策略节值（§5.1.3；保存时序列化为 config.evaluationStrategy / 存量直载字段） */
  const [strategyValue, setStrategyValue] = useState<EvaluationStrategyEditorValue | null>(null)
  /** 编辑态评估策略节初始值（存量 config 回填；「未触碰」与「显式不使用」以此区分） */
  const { initialValue, legacyDimensions, legacyBackgroundNoise } = strategyEditorInitial(
    caseItem?.config
  )

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
      return [...prev, { number, audioCount: 0, dimensionCount: 0, evaluation, algorithmParams: [], noise: emptyRoundNoise() }]
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
        algorithmParams: [...src.algorithmParams],
        noise: {
          backgroundNoise: src.noise.backgroundNoise ? { ...src.noise.backgroundNoise, deviceIds: [...src.noise.backgroundNoise.deviceIds] } : null,
          voiceprint: { ...src.noise.voiceprint },
          interferers: src.noise.interferers.map((x) => ({ ...x })),
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

  /** INT-996 算法参数步骤：更新指定轮 algorithmParams（独立列 params） */
  const updateRoundAlgorithmParams = (number: number | undefined, params: RoundAlgorithmParamItem[]) => {
    if (number == null) return
    setRounds((prev) => prev.map((r) => (r.number === number ? { ...r, algorithmParams: params } : r)))
  }

  /** INT-996 噪声与干扰步骤：更新指定轮噪声草稿 */
  const updateRoundNoise = (number: number | undefined, noise: RoundNoiseDraft) => {
    if (number == null) return
    setRounds((prev) => prev.map((r) => (r.number === number ? { ...r, noise } : r)))
  }

  const activeRoundDraft = rounds.find((r) => r.number === activeRound) ?? rounds[0]

  /**
   * 保存（INT-922 P1-1：走真实 testcase create/update 写接口，对照 V9.7.10 Vue）。
   * config.rounds 由轮次草稿序列化并与原始轮次合并（保留未在抽屉编辑的
   * audios/background_noise 等结构）；评估策略节仅在用户操作过时改写。
   */
  const handleSave = async () => {
    if (!nameValue.trim()) {
      toast.error('请输入用例名称')
      return
    }
    if (groupValue === '__new__' && !newGroupName.trim()) {
      toast.error('请输入新分组名称')
      return
    }

    const originalRounds = Array.isArray(caseItem?.config?.rounds)
      ? (caseItem.config.rounds as Array<Record<string, unknown>>)
      : []
    const config: Record<string, unknown> = {
      ...(caseItem?.config ?? {}),
      rounds: roundsToConfig(rounds, originalRounds),
    }

    // INT-996 算法参数独立列 [{round_number, params:[{field_code, field_value}]}]：
    // 各轮草稿 params（含 DynamicForm 编辑 + 存量非专项字段）+ 声纹对象（enabled 才入列）
    const algorithmParams = rounds
      .map((r) => {
        const params = r.algorithmParams.filter((p) => p.field_code !== 'voiceprint')
        const vp = serializeVoiceprint(r.noise.voiceprint)
        if (vp) params.push({ field_code: 'voiceprint', field_value: vp })
        return { round_number: r.number, params }
      })
      .filter((e) => e.params.length > 0)

    // 评估策略节（§5.1.3 契约）：未触碰（strategyValue=null）保留存量字段；三模式改写如下
    const strategyPayload = serializeEvaluationStrategy(strategyValue)
    let strategyId: string | null | undefined
    let strategyOverrides: Record<string, unknown> | null | undefined
    if (strategyValue?.mode === 'reference') {
      strategyId = strategyValue.strategyId ?? null
      strategyOverrides = (strategyValue.overrides ?? null) as Record<string, unknown> | null
      // 引用态：清存量直载字段（策略写时物化到 config.dimensions/background_noise）
      delete config.dimensions
      delete config.background_noise
      delete config.evaluationStrategy
    } else if (strategyValue?.mode === 'create') {
      config.dimensions = strategyPayload.dimensions
      config.background_noise = strategyPayload.backgroundNoise
      delete config.evaluationStrategy
      // 后端契约：strategy_id=null 沿用既有引用；只有显式空字符串 '' 才清引用
      // （testcase_crud_service.py _resolve_strategy_config：None 沿用、'' 清引用并返空配置）。
      // INT-922 审计 P2：引用态用例显式「不使用」/「新建内联」必须发 ''，否则旧引用不清、
      // 旧策略物化回填覆盖内联编辑。
      strategyId = ''
      strategyOverrides = null
    } else if (strategyValue?.mode === 'none') {
      delete config.dimensions
      delete config.background_noise
      delete config.evaluationStrategy
      strategyId = ''
      strategyOverrides = null
    }

    const payload: TestCaseMutatePayload = {
      name: nameValue.trim(),
      description: descriptionValue || null,
      groupId: groupValue === '__new__' ? null : groupValue || null,
      ...(groupValue === '__new__' ? { group: newGroupName.trim() } : {}),
      tags: tagValue,
      algorithmType: algorithmType || null,
      config,
      // INT-996 返工：轮次草稿已含全量存量参数（roundsFromConfig→algorithmParamsForRound），
      // 空数组直接透传——回退取 caseItem.algorithmParams 会在禁用声纹（各轮 params 过滤后为 []）时
      // 重新带上存量 voiceprint，违反「enabled=false 不入列」（INT-996 验收打回 P2）。
      algorithmParams,
      referenceParams: caseItem?.referenceParams ?? undefined,
      ...(strategyValue ? { strategyId, strategyOverrides } : {}),
    }

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
          ? `评估策略：内联配置（整体维度 ${strategyPayload.dimensions.length} 项 · 噪声 ${strategyPayload.backgroundNoise ? '已配置' : '未配置'}）`
          : '评估策略：未配置'

    try {
      if (isEdit && caseItem) {
        await updateTestCase(caseItem.id, payload)
      } else {
        await createTestCase(payload)
      }
      toast.success(isEdit ? '更新测试用例成功' : '添加测试用例成功', {
        description: summary,
      })
      onOpenChange(false)
      void queryClient.invalidateQueries({ queryKey: ['testcases'] })
      // 新建分组时分组列表一并刷新（分组头行/筛选选项）
      if (groupValue === '__new__') {
        void queryClient.invalidateQueries({ queryKey: ['testcase-groups'] })
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '请稍后重试'
      toast.error(isEdit ? '更新测试用例失败' : '添加测试用例失败', {
        description: message,
      })
    }
  }

  // INT-588：自动生成需真实读写名称框。抽屉组件常驻渲染（弹窗群内，Sheet 内容关闭时才卸载），
  // useState 初始值在页面加载（caseItem=null）时已定格；打开时按 caseItem 全字段回填——
  // INT-922：所属分组/关联算法/轮次此前不回填（Select 显占位、轮次硬编码默认），
  // 编辑态原名与既有配置不丢（等价 defaultValue 装载时机的行为）。
  useEffect(() => {
    if (!open) return
    setNameValue(caseItem?.name ?? '')
    setTagValue(caseItem?.tags ?? [])
    setGroupValue(caseItem?.groupId ?? presetGroupId ?? '')
    setAlgorithmType(caseItem?.algorithmType ?? '')
    setDescriptionValue(caseItem?.description ?? '')
    setRounds(caseItem ? roundsFromConfig(caseItem.config, caseItem.algorithmParams) : defaultRounds())
    setActiveRound(1)
    setStep('算法参数')
    setNewGroupName('')
    // INT-922 审计 P1：评估策略节未触碰（strategyValue=null）时保存保留存量字段，
    // 否则 EvaluationStrategyEditor 挂载即 onChange 输出 mode='none' 会在保存时
    // 删除 config.dimensions / config.background_noise / config.evaluationStrategy
    setStrategyValue(null)
  }, [open, caseItem, presetGroupId])

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
                  // 声明式 items：编辑回填（程序设值）时闭合态下拉也能显示分组名而非原始 id
                  items={groupOptions.map((o) => ({ value: o.value, label: o.label }))}
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
                value={descriptionValue}
                onChange={(e) => setDescriptionValue(e.target.value)}
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
                <Select
                  value={algorithmType}
                  onValueChange={(v) => setAlgorithmType(v ?? '')}
                  // 声明式 items：编辑回填（程序设值）时闭合态下拉显示算法名而非原始类型码
                  items={algorithmOptions.map((a) => ({ value: a.value, label: a.name }))}
                >
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
                        onAlgorithmParamsChange={(params) =>
                          updateRoundAlgorithmParams(activeRoundDraft?.number, params)
                        }
                        onNoiseChange={(noise) =>
                          updateRoundNoise(activeRoundDraft?.number, noise)
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
                initialValue={initialValue}
                legacyDimensions={legacyDimensions}
                legacyBackgroundNoise={legacyBackgroundNoise}
                dimensions={MOCK_CASE_DIMENSIONS}
                categories={MOCK_EVALUATION_CATEGORIES}
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
            <Button onClick={() => void handleSave()}>
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
  onAlgorithmParamsChange,
  onNoiseChange,
}: {
  step: (typeof STEPS)[number]
  activeRound: RoundDraft | undefined
  algorithmType: string
  onEvaluationChange: (evaluation: RoundEvaluationDraft) => void
  onAlgorithmParamsChange: (params: RoundAlgorithmParamItem[]) => void
  onNoiseChange: (noise: RoundNoiseDraft) => void
}) {
  switch (step) {
    case '算法参数':
      return (
        <AlgorithmParamsStep
          algorithmType={algorithmType || null}
          value={activeRound?.algorithmParams ?? []}
          onChange={onAlgorithmParamsChange}
        />
      )
    case '音频列表':
      return <AudioListStep presetCount={activeRound?.audioCount || 1} />
    case '噪声与干扰':
      return (
        <NoiseInterferenceStep
          value={activeRound?.noise ?? emptyRoundNoise()}
          onChange={onNoiseChange}
        />
      )
    case '评估维度':
      return (
        <EvaluationStep
          dimensions={MOCK_CASE_DIMENSIONS}
          categories={MOCK_EVALUATION_CATEGORIES}
          algorithmType={algorithmType || null}
          value={activeRound?.evaluation ?? newRoundEvaluation()}
          onChange={onEvaluationChange}
        />
      )
    case '参考参数':
      return <ReferenceStep generated={activeRound !== undefined && activeRound.audioCount > 0} />
  }
}
