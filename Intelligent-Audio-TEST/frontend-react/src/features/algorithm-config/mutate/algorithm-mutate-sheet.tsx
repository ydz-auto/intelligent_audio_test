/**
 * §6 算法编辑模态窗（mutate sheet；ModelMutateDrawer 母版，sm:max-w-[900px]）。
 * 分节 Tabs：基本信息/参数配置/参考参数/参数映射/评估维度；RHF+zod + useFieldArray；
 * 脏态离开守卫（formState.isDirty → ConfirmDialog）；保存聚合提交 POST/PUT /algorithm/definitions。
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { useAlgorithmAutoSave } from '@/application/algorithm-config/useAlgorithmAutoSave'
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import type { AlgorithmDefinition, AlgorithmGroup } from '@/domain/models/algorithmConfig'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'
import {
  cloneFormValues,
  emptyFormValues,
  toFormValues,
  toSaveInput,
} from '@/features/algorithm-config/mutate/form-converters'
import {
  algorithmEditFormSchema,
  algorithmFormSchema,
} from '@/features/algorithm-config/mutate/algorithm-form-schema'
import { BasicInfoSection } from '@/features/algorithm-config/mutate/basic-info-section'
import { ParamsSection } from '@/features/algorithm-config/mutate/params-section'
import { ReferenceParamsSection } from '@/features/algorithm-config/mutate/reference-params-section'
import { MappingsSection } from '@/features/algorithm-config/mutate/mappings-section'
import { DimensionsSection } from '@/features/algorithm-config/mutate/dimensions-section'
import { AUTO_SAVE_MESSAGES } from '@/features/algorithm-config/constants'

export type AlgorithmMutateSheetProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: MutateMode
  algorithm: AlgorithmDefinition | null
  groups: AlgorithmGroup[]
  dimensionOptions: Array<{ id: number; name: string }>
}

const MODE_TITLES: Record<MutateMode, string> = {
  create: '新建算法',
  edit: '编辑算法',
  clone: '复制算法',
}

export function AlgorithmMutateSheet(props: AlgorithmMutateSheetProps) {
  const { save } = useAlgorithmMutations()
  const groupMutations = useAlgorithmGroupMutations()
  const [dirtyConfirmOpen, setDirtyConfirmOpen] = useState(false)

  const defaultValues = useMemo(() => {
    if (!props.open) return undefined
    if (props.mode === 'create') return emptyFormValues()
    if (props.mode === 'clone' && props.algorithm) return cloneFormValues(props.algorithm)
    if (props.mode === 'edit' && props.algorithm) return toFormValues(props.algorithm)
    return emptyFormValues()
  }, [props.open, props.mode, props.algorithm])

  // 新建态走 §6.2 正则 schema；编辑/复制态代码为主键禁用不可改，用后端契约口径 schema
  // （无正则，仅必填+长度，见 algorithm-form-schema.ts 顶部说明）
  const schema = props.mode === 'create' ? algorithmFormSchema : algorithmEditFormSchema

  const form = useForm<AlgorithmFormValues>({
    // mode:'onChange'：字段错误随输入即时显示（§6.2/6.3 行级校验文案）
    mode: 'onChange',
    resolver: zodResolver(schema),
    defaultValues: emptyFormValues(),
    values: defaultValues,
  })

  // 保存可用性/自动保存校验直接对全量表单值实时计算，不依赖 formState.isValid：
  // RHF 的 setValue / useFieldArray 变更不会自动重算 isValid（onSubmit 模式须提交后才算，
  // onChange 模式也只对 register 的原生输入生效），导致「选分组/切状态/选参数类型」等
  // setValue 交互后保存按钮仍恒禁用（INT-508 P1 死锁）。同一 zod schema safeParse 覆盖全部变更路径。
  // §6.1a 30s 自动保存编排同层挂载（首次变脏启动/变更重置/校验不过暂停/归零聚合提交）。
  const autoSave = useAlgorithmAutoSave({
    open: props.open,
    form,
    mode: props.mode,
    schema,
    save,
  })
  const isFormValid = autoSave.isFormValid

  // 关闭 Sheet 时重置表单，避免下次打开残留旧值
  useEffect(() => {
    if (!props.open) form.reset(emptyFormValues())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open])

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      if (form.formState.isDirty && !save.isPending) {
        setDirtyConfirmOpen(true)
        return
      }
      props.onOpenChange(false)
      return
    }
    props.onOpenChange(true)
  }

  const handleSave = form.handleSubmit(async (values) => {
    const isNew = props.mode === 'create' || props.mode === 'clone'
    try {
      await save.mutateAsync({ ...toSaveInput(values), isNew })
      toast.success(isNew ? '算法已创建' : '算法已保存')
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    }
  })

  const handleCreateGroup = async (name: string) => {
    const group = await groupMutations.create.mutateAsync({
      name,
      description: '',
      icon: '',
      displayOrder: 0,
    })
    return group.id
  }

  return (
    <>
      <Sheet open={props.open} onOpenChange={handleOpenChange}>
        <SheetContent
          side='right'
          className='gap-0 sm:max-w-[900px]'
        >
          <SheetHeader className='pb-3'>
            <SheetTitle>{MODE_TITLES[props.mode]}</SheetTitle>
            <SheetDescription>
              管理算法定义、参数与映射关系
            </SheetDescription>
          </SheetHeader>

          <form
            id='algorithm-mutate-form'
            onSubmit={handleSave}
            className='flex min-h-0 flex-1 flex-col gap-4 px-4'
          >
            <Tabs defaultValue='basic' className='flex min-h-0 flex-1 flex-col'>
              <TabsList variant='line' className='w-full justify-start'>
                <TabsTrigger value='basic'>基本信息</TabsTrigger>
                <TabsTrigger value='params'>参数配置</TabsTrigger>
                <TabsTrigger value='reference'>参考参数</TabsTrigger>
                <TabsTrigger value='mappings'>参数映射</TabsTrigger>
                <TabsTrigger value='dimensions'>评估维度</TabsTrigger>
              </TabsList>

              <TabsContent value='basic' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <BasicInfoSection
                  form={form}
                  groups={props.groups}
                  mode={props.mode}
                  onCreateGroup={handleCreateGroup}
                />
              </TabsContent>
              <TabsContent value='params' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <ParamsSection form={form} />
              </TabsContent>
              <TabsContent value='reference' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <ReferenceParamsSection form={form} />
              </TabsContent>
              <TabsContent value='mappings' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <MappingsSection form={form} dimensionOptions={props.dimensionOptions} />
              </TabsContent>
              <TabsContent value='dimensions' className='min-h-0 flex-1 overflow-y-auto pb-4'>
                <DimensionsSection form={form} dimensionOptions={props.dimensionOptions} />
              </TabsContent>
            </Tabs>
          </form>

          <SheetFooter className='border-t px-4 py-3'>
            <div className='flex items-center justify-between gap-4'>
              {/* §6.1a 自动保存提醒（左端）：倒计时/校验不过 Alert，不可手动关闭 */}
              <div className='flex min-w-0 items-center gap-2'>
                {autoSave.isValidationBlocked ? (
                  <Alert variant='destructive' className='py-1.5'>
                    <AlertDescription className='text-sm'>
                      {AUTO_SAVE_MESSAGES.validationBlocked}
                    </AlertDescription>
                  </Alert>
                ) : autoSave.isActive ? (
                  <span className='text-muted-foreground text-xs font-mono tabular-nums'>
                    {AUTO_SAVE_MESSAGES.countdown(autoSave.secondsLeft)}
                  </span>
                ) : null}
              </div>
              <div className='flex shrink-0 items-center gap-2'>
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
                  form='algorithm-mutate-form'
                  disabled={save.isPending || !isFormValid}
                >
                  {save.isPending ? '保存中…' : '保存'}
                </Button>
              </div>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      {/* 脏态离开守卫（§6.1，model-mutate-drawer 同款） */}
      <AlertDialog open={dirtyConfirmOpen} onOpenChange={setDirtyConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>有未保存的更改</AlertDialogTitle>
            <AlertDialogDescription>
              当前表单有未保存的更改，确定要离开吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={save.isPending}>留在当前页</AlertDialogCancel>
            <AlertDialogAction
              variant='destructive'
              disabled={save.isPending}
              onClick={() => {
                setDirtyConfirmOpen(false)
                form.reset(emptyFormValues())
                props.onOpenChange(false)
              }}
            >
              离开并丢弃
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
