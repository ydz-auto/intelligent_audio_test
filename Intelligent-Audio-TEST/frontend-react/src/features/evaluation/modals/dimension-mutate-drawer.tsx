/**
 * 评估维度表单抽屉（features/evaluation/modals；11_用例域.md §5.5，Sheet sm:max-w-[900px]）。
 * 标题「新增评估维度｜编辑评估维度」；RHF+zod；分节 Tabs（基本信息/层级配置/结果配置/
 * API配置/关联算法）；子维度仅「基本信息/层级配置/结果配置」三节（API配置/关联算法仅主维度）。
 * 保存聚合提交 POST/PUT /evaluation/dimensions；成功 toast「评估维度添加成功｜更新成功」。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import {
  useEvaluationCategoryMutations,
  useEvaluationDimensionDetail,
  useEvaluationMutations,
} from '@/application/evaluation/use-dimensions'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  Dimension,
  EvaluationCategory,
} from '@/domain/models/evaluationDimension'
import type { MutateDrawerState } from '@/features/evaluation/types'
import {
  dimensionFormSchema,
  emptyDimensionFormValues,
  toDimensionFormValues,
  toDimensionSaveInput,
  type DimensionFormValues,
} from '@/features/evaluation/mutate/dimension-form-schema'
import { BasicInfoSection } from '@/features/evaluation/mutate/basic-info-section'
import { HierarchySection } from '@/features/evaluation/mutate/hierarchy-section'
import { ResultSection } from '@/features/evaluation/mutate/result-section'
import { ApiSection } from '@/features/evaluation/mutate/api-section'
import { AlgorithmSection } from '@/features/evaluation/mutate/algorithm-section'

/** 表单顶层字段 → 所属分节（错误摘要前缀，便于定位到对应 Tab；INT-1551） */
const FIELD_SECTION_LABELS: Record<string, string> = {
  name: '基本信息',
  description: '基本信息',
  evaluationType: '基本信息',
  categoryId: '基本信息',
  status: '基本信息',
  keywords: '基本信息',
  scoreUnit: '基本信息',
  dimensionType: '层级配置',
  parentDimensionId: '层级配置',
  resultType: '结果配置',
  resultMin: '结果配置',
  resultMax: '结果配置',
  decimalPlaces: '结果配置',
  weight: '结果配置',
  estimatedExecTime: '结果配置',
  rule: '结果配置',
  apiUrl: 'API配置',
  apiMethod: 'API配置',
  apiTimeout: 'API配置',
  apiHeaders: 'API配置',
  apiBodyTemplate: 'API配置',
  statisticMethod: 'API配置',
  aggDenominator: 'API配置',
  excludeRounds: 'API配置',
  requiredInputs: 'API配置',
  outputFields: 'API配置',
  apiEndpoints: 'API配置',
  associatedAlgorithms: '关联算法',
}

/** 校验错误摘要最多展示条数（超出后收尾为「等 N 处」） */
const VALIDATION_SUMMARY_MAX = 3

/** 新增态表单初值（含「添加子维度」预填的父维度 / 分类；INT-1660） */
function createFormValues(
  presetParentId?: number | null,
  presetCategoryId?: number | null
): DimensionFormValues {
  const base = emptyDimensionFormValues()
  if (presetParentId != null) {
    base.dimensionType = 'sub'
    base.parentDimensionId = String(presetParentId)
  }
  if (presetCategoryId != null) base.categoryId = String(presetCategoryId)
  return base
}

/** 校验问题 → 一行「分节：文案」摘要（去重、限条数；INT-1551） */
function summarizeValidationIssues(
  issues: ReadonlyArray<{ path: readonly PropertyKey[]; message: string }>
): string {
  const messages: string[] = []
  for (const issue of issues) {
    const section = FIELD_SECTION_LABELS[String(issue.path[0] ?? '')]
    const text = section ? `${section}：${issue.message}` : issue.message
    if (!messages.includes(text)) messages.push(text)
  }
  return messages.length > VALIDATION_SUMMARY_MAX
    ? `${messages.slice(0, VALIDATION_SUMMARY_MAX).join('；')} 等 ${messages.length} 处`
    : messages.join('；')
}

export function DimensionMutateDrawer({
  open,
  onOpenChange,
  mode,
  dimension,
  presetParentId,
  presetCategoryId,
  categories,
  mainDimensions,
  algorithmOptions,
  canManage,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: MutateDrawerState['mode']
  dimension: Dimension | null
  presetParentId?: number | null
  presetCategoryId?: number | null
  categories: EvaluationCategory[]
  mainDimensions: Dimension[]
  algorithmOptions: Array<{ value: string; label: string }>
  canManage: boolean
}) {
  const { save } = useEvaluationMutations()
  const { save: saveCategory } = useEvaluationCategoryMutations()
  // 抽屉内联新建的分类：POST 返回真实 id 后先本地并入选项，避免分类 query 重拉前的空标签
  const [createdCategories, setCreatedCategories] = useState<EvaluationCategory[]>([])
  const categoryOptions = useMemo(
    () => [
      ...categories,
      ...createdCategories.filter(
        (created) => !categories.some((cat) => cat.id === created.id)
      ),
    ],
    [categories, createdCategories]
  )
  // 编辑反填必须走详情（列表不下发 required_inputs/output_fields）：
  // 抽屉先以列表数据渲染基础字段，详情返回后再重同步全量配置
  const { data: detailDimension } = useEvaluationDimensionDetail(
    open && mode === 'edit' && dimension ? dimension.id : null
  )
  const effectiveDimension = detailDimension ?? dimension
  const dimensionId = dimension?.id ?? null

  const form = useForm<DimensionFormValues>({
    // mode:'onChange'：字段错误随输入即时显示（INT-1551：默认 onSubmit 下 errors 不产出，
    // 与「!isValid 禁用保存」叠加成无原因禁用死路）
    mode: 'onChange',
    resolver: zodResolver(dimensionFormSchema),
    defaultValues: emptyDimensionFormValues(),
  })

  // 打开 / 关闭 / 切换行时显式 reset：不用 useForm 的 values —— 它按深相等判重跳过同步，
  // 关闭时 form.reset(空值) 不更新其内部比对值，重开同一行（值深相等）同步被跳过 →
  // 空表 + 「维度名称不能为空」；换成另一行对象不同才生效（INT-1660，同 INT-1577）。
  useEffect(() => {
    if (!open) {
      form.reset(emptyDimensionFormValues())
      setCreatedCategories([])
      return
    }
    form.reset(
      mode === 'edit' && effectiveDimension
        ? toDimensionFormValues(effectiveDimension)
        : createFormValues(presetParentId, presetCategoryId)
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, dimensionId, presetParentId, presetCategoryId])

  // 详情到达后再同步一次：首次打开时以上一步用的是列表行（无 required_inputs /
  // output_fields），详情对象替换后必须重同步，故依赖 detailDimension 而不是行 id。
  useEffect(() => {
    if (!open || mode !== 'edit' || !detailDimension) return
    form.reset(toDimensionFormValues(detailDimension))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, detailDimension])

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      if (form.formState.isDirty && !save.isPending) {
        // 脏态离开：直接提示（视觉稿简化；不拦截）
        onOpenChange(false)
        return
      }
      onOpenChange(false)
      return
    }
    onOpenChange(true)
  }

  const handleSave = form.handleSubmit(async (values) => {
    try {
      // 编辑态必须携带 id：saveEvaluationDimension 凭 input.id 走 PUT /{id}，
      // 缺 id 会落入 POST 新建同名副本（INT-948）。复制路径不经本抽屉（onDuplicate 显式 copy- 前缀）。
      await save.mutateAsync(
        mode === 'edit' && effectiveDimension
          ? { ...toDimensionSaveInput(values), id: effectiveDimension.id }
          : toDimensionSaveInput(values)
      )
      toast.success(
        mode === 'edit' ? '评估维度更新成功' : '评估维度添加成功'
      )
      onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    }
  })

  const handleNewCategory = async (name: string): Promise<number> => {
    // 真实落库：POST /evaluation/categories（201 → data.id）；失败向上抛，由表单保留输入并提示
    const result = await saveCategory.mutateAsync({ name })
    const createdId = result.id
    if (createdId == null) {
      throw new Error('分类创建成功但未返回分类 id')
    }
    setCreatedCategories((prev) => [...prev, { id: createdId, name }])
    toast.success('分类添加成功')
    return createdId
  }

  const isSub = form.watch('dimensionType') === 'sub'
  // INT-1551：保存按钮的可用性与「为什么不能保存」同源——直接对当前表单值跑 schema，
  // 不依赖 RHF 提交后才产出的 errors（onSubmit 模式下 min≥max 这类跨字段校验不可见，
  // 与 !isValid 禁用叠加会形成无提示的禁用死路）。
  const validation = dimensionFormSchema.safeParse(form.watch())
  const isFormValid = validation.success
  const validationSummary = validation.success
    ? ''
    : summarizeValidationIssues(validation.error.issues)
  const tabs = isSub
    ? ['basic', 'hierarchy', 'result']
    : ['basic', 'hierarchy', 'result', 'api', 'algorithm']

  const tabLabels: Record<string, string> = {
    basic: '基本信息',
    hierarchy: '层级配置',
    result: '结果配置',
    api: 'API配置',
    algorithm: '关联算法',
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent side='right' className='gap-0 sm:max-w-[900px]'>
        <SheetHeader className='pb-3'>
          <SheetTitle>
            {mode === 'edit' ? '编辑评估维度' : '新增评估维度'}
          </SheetTitle>
          <SheetDescription>
            管理评估维度的基本信息、层级、结果评分规则与 API 配置
          </SheetDescription>
        </SheetHeader>

        <form
          id='dimension-mutate-form'
          onSubmit={handleSave}
          className='flex min-h-0 flex-1 flex-col gap-4 px-4'
        >
          <Tabs defaultValue={isSub ? 'basic' : 'basic'} className='flex min-h-0 flex-1 flex-col'>
            <TabsList variant='line' className='w-full justify-start'>
              {tabs.map((tab) => (
                <TabsTrigger key={tab} value={tab}>
                  {tabLabels[tab]}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value='basic' className='min-h-0 flex-1 overflow-y-auto pb-4'>
              <BasicInfoSection
                form={form}
                categories={categoryOptions}
                onNewCategory={handleNewCategory}
              />
            </TabsContent>
            <TabsContent value='hierarchy' className='min-h-0 flex-1 overflow-y-auto pb-4'>
              <HierarchySection form={form} mainDimensions={mainDimensions} />
            </TabsContent>
            <TabsContent value='result' className='min-h-0 flex-1 overflow-y-auto pb-4'>
              <ResultSection
                form={form}
                isLlmJudge={mode === 'edit' && effectiveDimension?.llmJudge === true}
              />
            </TabsContent>
            {!isSub && (
              <TabsContent value='api' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <ApiSection form={form} />
              </TabsContent>
            )}
            {!isSub && (
              <TabsContent value='algorithm' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <AlgorithmSection form={form} algorithmOptions={algorithmOptions} />
              </TabsContent>
            )}
          </Tabs>
        </form>

        <SheetFooter className='border-t px-4 py-3'>
          <div className='flex w-full items-center justify-between gap-3'>
            {!isFormValid && (
              <p
                className='text-muted-foreground min-w-0 text-xs'
                data-testid='dimension-form-validation-summary'
              >
                请先修正：{validationSummary}
              </p>
            )}
            <div className='ml-auto flex shrink-0 items-center gap-2'>
              <Button
                variant='outline'
                type='button'
                disabled={save.isPending}
                onClick={() => handleOpenChange(false)}
              >
                取消
              </Button>
              <Button
                type='submit'
                form='dimension-mutate-form'
                disabled={save.isPending || !isFormValid || !canManage}
              >
                {save.isPending ? '保存中…' : '保存'}
              </Button>
            </div>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
