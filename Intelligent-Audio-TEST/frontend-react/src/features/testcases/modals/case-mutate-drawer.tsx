/**
 * 新增/编辑用例抽屉（11_用例域.md §5.1，Sheet `sm:max-w-[1280px]`，testcase:create/update）。
 * 单栏纵向分节（节间 border-b）：基本信息（双列栅格）/标签（CaseTagCombobox：TagInput chips +
 * GET /tags/names 建议下拉 + 「新建」创建项，INT-1591 §5.1）/
 * 描述/轮次配置（关联算法不在抽屉内选择，新建跟随顶部全局算法选择器、编辑取用例自身值；
 * 左 RoundNav 180px + 右步骤区横向锚点 Tabs line：
 * 算法参数→音频列表→噪声与干扰→评估维度→参考参数，五步全字段表单）/
 * 评估配置=两个用例级独立节：全局背景噪声 + 整体评估维度，直载 config.background_noise /
 * config.dimensions（评估策略复用已下线，保存时显式 strategy_id='' 清存量引用）。
 * INT-486 用例不分类型口径：头部类型切换（API/E2E）移除——正式类型维度=关联算法。
 * ⚠️ 实施注意②：addRound 已有轮次时复制上一轮 evaluation（RoundConfigEditor.vue:252-254），
 * 「新轮次默认关闭」严格仅首轮成立——本卡等价移植保持复制行为、不额外重置 enabled。
 * INT-877/INT-996 合流：轮次草稿（RoundDraft）同时携带 audios（音频回填/保存 P1-1）+
 * algorithmParams（独立列）+ noise（segment 级噪声段）；评估维度选项接真实接口
 * （P2-1/P2-2），新选维度补 name（P3-3）。
 */
import { useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
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
import { useAlgorithmLabels } from '@/application/hooks/use-algorithm-options'
import {
  useAlgorithmDimensions,
  useEvaluationCategories,
} from '@/application/evaluation/use-dimensions'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type {
  TestCaseBackgroundNoiseItem,
  TestCaseDimensionItem,
} from '@/domain/models/evaluationStrategy'
import {
  createTestCase,
  updateTestCase,
  type TestCaseMutatePayload,
} from '@/infrastructure/api/testcases-api'
import { CaseTagCombobox } from '@/features/testcases/modals/case-tag-combobox'
import {
  RoundNav,
  newRoundEvaluation,
  emptyRoundNoise,
  type RoundAlgorithmParamItem,
  type RoundAudioDraft,
  type RoundDraft,
  type RoundEvaluationDraft,
  type RoundNoiseDraft,
} from '@/features/testcases/modals/round-config/round-nav'
import {
  defaultRounds,
  roundsFromConfig,
  roundsToConfig,
} from '@/domain/lib/testcase-round-config'
import { AlgorithmParamsStep } from '@/features/testcases/modals/round-config/algo-params-step'
import { AudioListStep } from '@/features/testcases/modals/round-config/audio-list-step'
import { NoiseInterferenceStep } from '@/features/testcases/modals/round-config/noise-interference-step'
import { serializeVoiceprint } from '@/features/testcases/modals/round-config/round-noise-codec'
import {
  globalNoiseFromDto,
  serializeGlobalNoise,
} from '@/features/testcases/modals/round-config/round-noise-codec'
import { EvaluationStep } from '@/features/testcases/modals/round-config/evaluation-step'
import { GlobalNoiseEditor } from '@/features/testcases/modals/round-config/global-noise-editor'
import { OverallEvaluationEditor } from '@/features/testcases/modals/round-config/overall-evaluation-editor'
import {
  ReferenceStep,
  referencePathForRound,
} from '@/features/testcases/modals/round-config/reference-step'

const STEPS = ['算法参数', '音频列表', '噪声与干扰', '评估维度', '参考参数'] as const

/**
 * 存量 config → 抽屉两个独立节的初始值（编辑回填）。
 * 整体评估维度 = config.dimensions；全局背景噪声 = config.background_noise。
 * 引用过评估策略的存量用例在保存时已由后端物化进这两个字段，这里直读即可。
 */
function resolveCaseEvaluationState(config: Record<string, unknown> | null | undefined): {
  overallDims: TestCaseDimensionItem[]
  globalNoise: TestCaseBackgroundNoiseItem | null
} {
  return {
    overallDims: (Array.isArray(config?.dimensions)
      ? config.dimensions
      : []) as TestCaseDimensionItem[],
    globalNoise: globalNoiseFromDto(
      config?.background_noise as Record<string, unknown> | null | undefined
    ),
  }
}

export function CaseMutateDrawer({
  open,
  onOpenChange,
  caseItem,
  groups,
  presetGroupId,
  defaultAlgorithmType,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem: TestCaseListItem | null
  groups: TestCaseGroup[]
  /** 新建态预填分组（分组视图「新增用例到此分组」入口；编辑态忽略） */
  presetGroupId?: string | null
  /** 新建态关联算法来源=页面全局算法选择器（编辑态以用例自身 algorithmType 为准） */
  defaultAlgorithmType?: string | null
}) {
  const isEdit = caseItem != null
  const queryClient = useQueryClient()
  /** 当前关联算法类型（新建取页面全局算法选择器，编辑取用例值；决定可用维度收敛） */
  const [algorithmType, setAlgorithmType] = useState(
    caseItem?.algorithmType ?? defaultAlgorithmType ?? ''
  )
  /**
   * 维度云唯一数据源：options 端点按 algorithmType 服务端收敛，并下发 parent_dimension_id /
   * category_id，主/子层级与分类组头一次取全（列表端点不下发 associated_algorithms，
   * 客户端再过滤会恒空）。
   */
  const dimensionsQuery = useAlgorithmDimensions(algorithmType || null)
  const dimensions = dimensionsQuery.data
  const categoriesQuery = useEvaluationCategories()
  const categories = categoriesQuery.data ?? []
  /** 维度 id → name（roundsToConfig 新选维度补 name；INT-877 P3-3） */
  const dimNameById = useMemo(
    () => new Map(dimensions.map((d) => [Number(d.id), d.name])),
    [dimensions]
  )
  const [step, setStep] = useState<(typeof STEPS)[number]>('算法参数')
  const [nameValue, setNameValue] = useState(caseItem?.name ?? '')
  const [tagValue, setTagValue] = useState<string[]>(caseItem?.tags ?? [])
  const [groupValue, setGroupValue] = useState(caseItem?.groupId ?? presetGroupId ?? '')
  const [newGroupName, setNewGroupName] = useState('')
  const [descriptionValue, setDescriptionValue] = useState(caseItem?.description ?? '')
  /** 算法类型码 → 中文名（评估维度提示条用真实选项，INT-1687；口径统一走 useAlgorithmLabels） */
  const algorithmLabels = useAlgorithmLabels()
  const [rounds, setRounds] = useState<RoundDraft[]>(defaultRounds())
  const [activeRound, setActiveRound] = useState(1)
  /** 整体评估维度独立节（config.dimensions 内联承载） */
  const [overallDims, setOverallDims] = useState<TestCaseDimensionItem[]>([])
  /** 全局背景噪声独立节（config.background_noise 内联承载） */
  const [globalNoise, setGlobalNoise] = useState<TestCaseBackgroundNoiseItem | null>(null)

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
      return [
        ...prev,
        {
          number,
          audioCount: 0,
          dimensionCount: 0,
          evaluation,
          audios: [],
          algorithmParams: [],
          noise: emptyRoundNoise(),
        },
      ]
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
        // 复制当前轮次：音频草稿深拷贝 + 独立行身份（编辑互不串扰）
        audios: src.audios.map((a, i) => ({
          ...a,
          id: `round-${number}-audio-${i}`,
        })),
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

  /** 音频列表步骤受控回写（INT-877 P1-1：变更并入轮次草稿，保存序列化到 config.rounds[].audios） */
  const updateAudios = (number: number | undefined, audios: RoundAudioDraft[]) => {
    if (number == null) return
    setRounds((prev) =>
      prev.map((r) => (r.number === number ? { ...r, audios, audioCount: audios.length } : r))
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
   * config.rounds 由轮次草稿序列化并与原始轮次合并（音频 P1-1 + 评估 + INT-996 噪声段）；
   * 评估策略节仅在用户操作过时改写。
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
      rounds: roundsToConfig(rounds, originalRounds, dimNameById),
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

    // 两个独立节直载用例配置（整体评估维度 + 全局背景噪声）
    config.dimensions = overallDims
    config.background_noise = globalNoise ? serializeGlobalNoise(globalNoise) : null
    delete config.evaluationStrategy

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
      // 后端契约：strategy_id='' 清引用（保留本次写入的 config 快照），
      // 避免存量用例残留的评估策略在保存时反向覆盖本节编辑值。
      strategyId: '',
    }

    try {
      if (isEdit && caseItem) {
        await updateTestCase(caseItem.id, payload)
      } else {
        await createTestCase(payload)
      }
      toast.success(isEdit ? '更新测试用例成功' : '添加测试用例成功')
      onOpenChange(false)
      void queryClient.invalidateQueries({ queryKey: ['testcases'] })
      // 新建标签名（「新建「{词}」」落 chip）后建议候选同步刷新
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
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
    setAlgorithmType(caseItem?.algorithmType ?? defaultAlgorithmType ?? '')
    setDescriptionValue(caseItem?.description ?? '')
    setRounds(caseItem ? roundsFromConfig(caseItem.config, caseItem.algorithmParams) : defaultRounds())
    setActiveRound(1)
    setStep('算法参数')
    setNewGroupName('')
    // 两个独立节按存量 config 回填（整体评估维度 / 全局背景噪声）
    const resolved = resolveCaseEvaluationState(caseItem?.config)
    setOverallDims(resolved.overallDims)
    setGlobalNoise(resolved.globalNoise)
  }, [open, caseItem, presetGroupId, defaultAlgorithmType])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='w-full sm:max-w-[1280px]'>
        <SheetHeader className='border-b'>
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div>
              <SheetTitle>{isEdit ? '编辑测试用例' : '新增测试用例'}</SheetTitle>
              <SheetDescription>
                {isEdit
                  ? `正在编辑「${caseItem?.name}」，配置分组、标签与轮次`
                  : '配置用例名称、分组与标签（关联算法跟随顶部全局算法选择器）'}
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
              <CaseTagCombobox value={tagValue} onChange={setTagValue} />
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

            {/* 轮次配置（关联算法不再在抽屉内选择，跟随顶部全局算法选择器） */}
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
                    <div className='px-3 py-3' data-testid='case-step-body'>
                      <StepBody
                        step={step}
                        caseId={caseItem?.id ?? null}
                        caseReferenceParams={caseItem?.referenceParams}
                        activeRound={activeRoundDraft}
                        algorithmType={algorithmType}
                        algorithmLabels={algorithmLabels}
                        dimensions={dimensions}
                        categories={categories}
                        onEvaluationChange={(evaluation) =>
                          updateEvaluation(activeRoundDraft?.number, evaluation)
                        }
                        onAudiosChange={(audios) =>
                          updateAudios(activeRoundDraft?.number, audios)
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

            {/* 全局背景噪声（用例级独立常驻节，置于整体评估维度之前） */}
            <section className='border-border/60 border-t pt-4'>
              <GlobalNoiseEditor
                key={isEdit && caseItem ? `noise-${caseItem.id}` : 'noise-create'}
                value={globalNoise}
                onChange={setGlobalNoise}
              />
            </section>

            {/* 整体评估维度（用例级独立常驻节） */}
            <section className='border-border/60 border-t pt-4'>
              <OverallEvaluationEditor
                key={isEdit && caseItem ? `dims-${caseItem.id}` : 'dims-create'}
                dimensions={dimensions}
                categories={categories}
                algorithmType={algorithmType}
                value={overallDims}
                onChange={setOverallDims}
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
  caseId,
  caseReferenceParams,
  activeRound,
  algorithmType,
  algorithmLabels,
  dimensions,
  categories,
  onEvaluationChange,
  onAudiosChange,
  onAlgorithmParamsChange,
  onNoiseChange,
}: {
  step: (typeof STEPS)[number]
  /** 当前用例 id（编辑态；参考参数步骤按用例+轮次读写真实文件） */
  caseId: string | null
  /** 用例参考参数独立列（[{round_number, reference_params_path}]；路径行真实值兜底） */
  caseReferenceParams: unknown
  activeRound: RoundDraft | undefined
  algorithmType: string
  /** 算法类型码 → 中文名（真实 /algorithm/options；评估提示条用） */
  algorithmLabels?: Record<string, string>
  dimensions: Dimension[]
  categories: EvaluationCategory[]
  onEvaluationChange: (evaluation: RoundEvaluationDraft) => void
  onAudiosChange: (audios: RoundAudioDraft[]) => void
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
      return <AudioListStep value={activeRound?.audios ?? []} onChange={onAudiosChange} />
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
          dimensions={dimensions}
          categories={categories}
          algorithmType={algorithmType || null}
          algorithmLabels={algorithmLabels}
          value={activeRound?.evaluation ?? newRoundEvaluation()}
          onChange={onEvaluationChange}
        />
      )
    case '参考参数':
      return (
        <ReferenceStep
          caseId={caseId}
          roundNumber={activeRound?.number ?? 1}
          generated={activeRound !== undefined && activeRound.audioCount > 0}
          pathFallback={referencePathForRound(
            caseReferenceParams,
            activeRound?.number ?? 1
          )}
        />
      )
  }
}
