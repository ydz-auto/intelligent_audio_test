/**
 * 评估维度表单抽屉（features/evaluation/modals；11_用例域.md §5.5，Sheet sm:max-w-[900px]）。
 * 标题「新增评估维度｜编辑评估维度」；RHF+zod；分节 Tabs（基本信息/层级配置/结果配置/
 * API配置/关联算法）；子维度仅「基本信息/层级配置/结果配置」三节（API配置/关联算法仅主维度）。
 * 保存聚合提交 POST/PUT /evaluation/dimensions；成功 toast「评估维度添加成功｜更新成功」。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { useEvaluationMutations } from '@/application/evaluation/use-dimensions'
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

  const defaultValues = useMemo(() => {
    if (!open) return undefined
    if (mode === 'edit' && dimension) return toDimensionFormValues(dimension)
    const base = emptyDimensionFormValues()
    if (presetParentId != null) {
      base.dimensionType = 'sub'
      base.parentDimensionId = String(presetParentId)
    }
    if (presetCategoryId != null) {
      base.categoryId = String(presetCategoryId)
    }
    return base
  }, [open, mode, dimension, presetParentId, presetCategoryId])

  const form = useForm<DimensionFormValues>({
    resolver: zodResolver(dimensionFormSchema),
    defaultValues: emptyDimensionFormValues(),
    values: defaultValues,
  })

  // 关闭 Sheet 时重置表单，避免下次打开残留旧值
  useEffect(() => {
    if (!open) form.reset(emptyDimensionFormValues())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

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
      await save.mutateAsync(toDimensionSaveInput(values))
      toast.success(
        mode === 'edit' ? '评估维度更新成功' : '评估维度添加成功'
      )
      onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    }
  })

  const handleNewCategory = (_name: string) => {
    toast.success('分类添加成功')
  }

  const isSub = form.watch('dimensionType') === 'sub'
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
                categories={categories}
                onNewCategory={handleNewCategory}
              />
            </TabsContent>
            <TabsContent value='hierarchy' className='min-h-0 flex-1 overflow-y-auto pb-4'>
              <HierarchySection form={form} mainDimensions={mainDimensions} />
            </TabsContent>
            <TabsContent value='result' className='min-h-0 flex-1 overflow-y-auto pb-4'>
              <ResultSection form={form} />
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
          <div className='flex items-center justify-end gap-2'>
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
              disabled={save.isPending || !form.formState.isValid || !canManage}
            >
              {save.isPending ? '保存中…' : '保存'}
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
