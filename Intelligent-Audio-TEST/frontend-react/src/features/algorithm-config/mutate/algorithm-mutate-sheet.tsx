/**
 * §6 算法编辑 Sheet（INT-591 编辑结构降维核心：ModelMutateDrawer 母版）。
 * 宽度：≥sm 92vw、上限 1400px——映射表 7 列 + 大量分组时 900px 太窄。
 * 去五 Tab 顶层切换改单页滚动布局：基本信息（§6.3）→ 统一参数表 + 作用域 chips（§6.4）
 * → 高级配置折叠区默认收起（§6.5）。保存=草稿/发布双态（§6.2）：
 * - footer 左端草稿状态区三形态（「将在 {n} 秒后自动保存草稿」/「正在保存草稿…」/「上次保存 HH:mm:ss」）
 *   + 校验不过暂停 Alert + 乐观锁冲突 inline Alert（§6.2a）；
 * - footer 右端 [取消][保存草稿][发布]；发布冲突 AlertDialog + 刷新丢弃路径。
 * 脏态离开守卫按 lastSaved 草稿快照判定（form.reset 后 isDirty 归零，不再误弹）。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'

import {
  useAlgorithmDraft,
} from '@/application/algorithm-config/useAlgorithmDraft'
import {
  useAlgorithmPublish,
} from '@/application/algorithm-config/useAlgorithmPublish'
import {
  useAlgorithmGroupMutations,
  useAlgorithmMutations,
} from '@/application/algorithm-config/useAlgorithmDefinitions'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import type { AlgorithmDefinition, AlgorithmGroup } from '@/domain/models/algorithmConfig'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'
import {
  cloneFormValues,
  emptyFormValues,
  toFormValues,
} from '@/features/algorithm-config/mutate/form-converters'
import {
  algorithmDraftFormSchema,
  algorithmEditFormSchema,
  algorithmFormSchema,
} from '@/features/algorithm-config/mutate/algorithm-form-schema'
import { BasicInfoSection } from '@/features/algorithm-config/mutate/basic-info-section'
import { ParamsTable } from '@/features/algorithm-config/mutate/params-table'
import { AdvancedConfigCollapsible } from '@/features/algorithm-config/mutate/advanced-config-collapsible'
import { DRAFT_MESSAGES } from '@/features/algorithm-config/constants'
import {
  fetchAlgorithmDetail,
  fetchAlgorithmDraft,
  publishAlgorithm,
  saveAlgorithmDraft,
} from '@/infrastructure/api/algorithm-config-api'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import type { AlgorithmOption } from './annotation-code-select'

export type AlgorithmMutateSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: MutateMode
  algorithm: AlgorithmDefinition | null
  groups: AlgorithmGroup[]
  /** 算法列表（标注代码下拉选项：标注代码=算法类型） */
  algorithmOptions: AlgorithmOption[]
  /** 评估维度全量（含子维度；映射/关联维度按 分组/主维度/子维度 展示） */
  dimensions: Dimension[]
  /** 评估维度分类（分类分组组头） */
  categories: EvaluationCategory[]
}

const MODE_TITLES: Record<MutateMode, string> = {
  create: '新建算法',
  edit: '编辑算法',
  clone: '复制算法',
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function AlgorithmMutateSheet(props: AlgorithmMutateSheetProps) {
  const { invalidate } = useAlgorithmMutations()
  const groupMutations = useAlgorithmGroupMutations()
  const [dirtyConfirmOpen, setDirtyConfirmOpen] = useState(false)
  const [draftRefreshConfirmOpen, setDraftRefreshConfirmOpen] = useState(false)
  // 编辑态「存在未发布的草稿」横幅（§6.2/INT-589）：初始取列表 has_draft（后端返回后启用），
  // 打开时经草稿恢复接口实证覆盖；空 {} = 无草稿 → 横幅不渲染
  const [hasUnpublishedDraft, setHasUnpublishedDraft] = useState(
    () => props.mode === 'edit' && Boolean(props.algorithm?.hasDraft)
  )

  const defaultValues = useMemo(() => {
    if (!props.open) return undefined
    if (props.mode === 'create') return emptyFormValues()
    if (props.mode === 'clone' && props.algorithm) return cloneFormValues(props.algorithm)
    if (props.mode === 'edit' && props.algorithm) return toFormValues(props.algorithm)
    return emptyFormValues()
  }, [props.open, props.mode, props.algorithm])

  // 发布严格 schema：新建态走 §6.2 正则；编辑/复制态代码为主键禁用不可改（后端契约口径）
  const publishSchema =
    props.mode === 'create' ? algorithmFormSchema : algorithmEditFormSchema

  const form = useForm<AlgorithmFormValues>({
    // mode:'onChange'：字段错误随输入即时显示（§6.2/6.6 行级校验文案）
    mode: 'onChange',
    resolver: zodResolver(publishSchema),
    defaultValues: emptyFormValues(),
    values: defaultValues,
  })

  // 编辑态重拉最新发布版（§6.2a 乐观锁刷新；create/clone 无刷新源）
  const refetchLatest = useMemo(() => {
    if (props.mode !== 'edit') return undefined
    return () =>
      fetchAlgorithmDetail(form.getValues('type')).then((detail) => detail)
  }, [props.mode, form])

  const draft = useAlgorithmDraft({
    open: props.open,
    form,
    mode: props.mode,
    schema: algorithmDraftFormSchema,
    saveDraft: saveAlgorithmDraft,
    refetchLatest,
  })

  const publish = useAlgorithmPublish({
    open: props.open,
    form,
    mode: props.mode,
    schema: publishSchema,
    publish: publishAlgorithm,
    refetchLatest,
    onPublished: () => {
      invalidate()
      props.onOpenChange(false)
    },
  })

  // 关闭 Sheet 时重置表单，避免下次打开残留旧值
  useEffect(() => {
    if (!props.open) {
      form.reset(emptyFormValues())
      draft.cancelPendingSave()
      setHasUnpublishedDraft(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open])

  // 编辑态打开先读草稿（§6.2/INT-589）：有草稿 → 恢复草稿预填 + 头部 Alert；空 {} = 无草稿 → 发布版预填。
  // create/clone 不读草稿；草稿接口不可达时保持发布版预填、不阻断编辑（横幅不渲染）
  useEffect(() => {
    if (!props.open || props.mode !== 'edit' || !props.algorithm) return
    const algorithmType = props.algorithm.type
    let cancelled = false
    void (async () => {
      try {
        const draft = await fetchAlgorithmDraft(algorithmType)
        if (cancelled) return
        if (draft) {
          form.reset(toFormValues(draft))
          setHasUnpublishedDraft(true)
        } else {
          setHasUnpublishedDraft(false)
        }
      } catch {
        setHasUnpublishedDraft(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open, props.mode, props.algorithm])

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      if (form.formState.isDirty && !publish.isPublishing && !draft.isSavingDraft) {
        setDirtyConfirmOpen(true)
        return
      }
      draft.cancelPendingSave()
      props.onOpenChange(false)
      return
    }
    props.onOpenChange(true)
  }

  const handlePublish = async () => {
    draft.cancelPendingSave()
    await publish.publishNow()
  }

  const handleCreateGroup = async (name: string) => {
    const group = await groupMutations.create.mutateAsync({
      name,
      description: '',
      icon: '',
      displayOrder: 0,
    })
    return group.id
  }

  // 参数表容器 focusout → 失焦防抖草稿保存（§6.2 保留旧习惯；relatedTarget 仍在表内则跳过）
  const handleParamsBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    const related = e.relatedTarget as Node | null
    if (related && e.currentTarget.contains(related)) return
    draft.scheduleBlurSave()
  }

  return (
    <>
      <Sheet open={props.open} onOpenChange={handleOpenChange}>
        <SheetContent
          side='right'
          className='gap-0 sm:w-[92vw] sm:max-w-[1400px]'
        >
          <SheetHeader className='pb-3'>
            <SheetTitle>{MODE_TITLES[props.mode]}</SheetTitle>
            <SheetDescription>
              管理算法定义、参数与映射关系
            </SheetDescription>
          </SheetHeader>

          {/* INT-591 降维核心：单页滚动三区块（基本信息 → 参数表 → 高级配置折叠） */}
          <form
            id='algorithm-mutate-form'
            onSubmit={(e) => {
              e.preventDefault()
              void handlePublish()
            }}
            className='flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 pb-6'
          >
            {hasUnpublishedDraft && (
              <div className='border-warning/40 bg-warning/10 text-warning rounded-lg border px-3 py-2 text-sm'>
                {DRAFT_MESSAGES.hasUnpublishedDraft}
              </div>
            )}

            {publish.publishError && (
              <Alert variant='destructive'>
                <AlertDescription className='text-sm'>
                  {publish.publishError}
                </AlertDescription>
              </Alert>
            )}

            <div className='space-y-5'>
              <BasicInfoSection
                form={form}
                groups={props.groups}
                mode={props.mode}
                onCreateGroup={handleCreateGroup}
              />

              {/* 统一参数表 + 作用域 chips（§6.4） */}
              <div onBlur={handleParamsBlur}>
                <ParamsTable form={form} algorithmOptions={props.algorithmOptions} />
              </div>

              {/* 高级配置折叠区（§6.5 默认收起） */}
              <AdvancedConfigCollapsible
                form={form}
                algorithmOptions={props.algorithmOptions}
                dimensions={props.dimensions}
                categories={props.categories}
              />
            </div>
          </form>

          <SheetFooter className='border-t px-4 py-3'>
            <div className='flex items-center justify-between gap-4'>
              {/* §6.2 footer 左端草稿状态区 */}
              <div className='flex min-w-0 items-center gap-2'>
                {draft.draftConflict ? (
                  <div className='border-warning/40 bg-warning/10 text-warning flex flex-wrap items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm'>
                    <span>{DRAFT_MESSAGES.conflict}</span>
                    <Button
                      size='xs'
                      variant='outline'
                      type='button'
                      onClick={draft.clearConflict}
                    >
                      {DRAFT_MESSAGES.continueEdit}
                    </Button>
                    <Button
                      size='xs'
                      type='button'
                      onClick={() => setDraftRefreshConfirmOpen(true)}
                    >
                      {DRAFT_MESSAGES.refresh}
                    </Button>
                  </div>
                ) : draft.isSavingDraft ? (
                  <span className='text-muted-foreground inline-flex items-center gap-1.5 text-xs'>
                    <Spinner size={13} />
                    {DRAFT_MESSAGES.saving}
                  </span>
                ) : draft.isValidationBlocked ? (
                  <Alert variant='destructive' className='py-1.5'>
                    <AlertDescription className='text-sm'>
                      {DRAFT_MESSAGES.validationBlocked}
                    </AlertDescription>
                  </Alert>
                ) : (
                  <span className='text-muted-foreground inline-flex items-center gap-2 text-xs'>
                    {draft.lastSavedAt && (
                      <span className='font-mono tabular-nums'>
                        {DRAFT_MESSAGES.lastSaved(formatTime(draft.lastSavedAt))}
                      </span>
                    )}
                    {draft.isActive && (
                      <span className='font-mono tabular-nums'>
                        {DRAFT_MESSAGES.countdown(draft.secondsLeft)}
                      </span>
                    )}
                  </span>
                )}
              </div>

              <div className='flex shrink-0 items-center gap-2'>
                <Button
                  variant='outline'
                  type='button'
                  disabled={publish.isPublishing || draft.isSavingDraft}
                  onClick={() => handleOpenChange(false)}
                >
                  取消
                </Button>
                {!draft.draftConflict && (
                  <Button
                    variant='outline'
                    type='button'
                    disabled={
                      draft.isSavingDraft ||
                      publish.isPublishing ||
                      !draft.isFormValid ||
                      !form.formState.isDirty
                    }
                    onClick={() => void draft.saveDraftNow()}
                  >
                    {draft.isSavingDraft ? '保存中…' : '保存草稿'}
                  </Button>
                )}
                <Button
                  type='submit'
                  form='algorithm-mutate-form'
                  disabled={publish.isPublishing || draft.isSavingDraft || !publish.isFormValid}
                >
                  {publish.isPublishing ? (
                    <>
                      <Spinner size={14} />
                      发布中…
                    </>
                  ) : (
                    '发布'
                  )}
                </Button>
              </div>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {/* 脏态离开守卫（§6.1，model-mutate-drawer 同款；按 lastSaved 草稿快照判定） */}
      <AlertDialog open={dirtyConfirmOpen} onOpenChange={setDirtyConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>有未保存的更改</AlertDialogTitle>
            <AlertDialogDescription>
              当前表单有未保存的更改，确定要离开吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={publish.isPublishing || draft.isSavingDraft}>
              留在当前页
            </AlertDialogCancel>
            <AlertDialogAction
              variant='destructive'
              disabled={publish.isPublishing || draft.isSavingDraft}
              onClick={() => {
                setDirtyConfirmOpen(false)
                draft.cancelPendingSave()
                form.reset(emptyFormValues())
                props.onOpenChange(false)
              }}
            >
              离开并丢弃
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* §6.2a 草稿冲突「立即刷新」确认（刷新将丢弃当前草稿） */}
      <AlertDialog open={draftRefreshConfirmOpen} onOpenChange={setDraftRefreshConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>刷新草稿</AlertDialogTitle>
            <AlertDialogDescription>{DRAFT_MESSAGES.refreshConfirm}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDraftRefreshConfirmOpen(false)
                void draft.refreshLatest()
              }}
            >
              确定刷新
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* §6.2a 发布冲突 AlertDialog */}
      <AlertDialog open={publish.publishConflict} onOpenChange={publish.clearConflict}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>发布冲突</AlertDialogTitle>
            <AlertDialogDescription>
              发布冲突：该算法已被他人修改。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={publish.clearConflict}>继续编辑</AlertDialogCancel>
            <AlertDialogAction
              variant='destructive'
              onClick={() => void publish.refreshAndDiscard()}
            >
              刷新并丢弃我的更改
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
