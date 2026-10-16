/**
 * 新增/编辑用例抽屉（11_用例域.md §5.1，Sheet `sm:max-w-[1280px]`，testcase:create/update）。
 * 头部类型切换（API / E2E，默认胶囊）+ 单栏纵向分节（节间 border-b）：
 * 基本信息（双列栅格）/标签（TagInput chips + 已有标签建议）/描述/关联算法/轮次配置
 * （左轮次导航 180px + 右步骤区横向锚点 Tabs line：算法参数→音频列表→噪声与干扰→评估维度→参考参数）。
 * 可视稿演示态：轮次步骤区为结构占位（完整字段随接线批次落地，§5.1 已列全）。
 */
import { Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
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
import { cn } from '@/lib/utils'
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'

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
  const [testType, setTestType] = useState<'api' | 'e2e'>(caseItem?.type ?? 'e2e')
  const [step, setStep] = useState<(typeof STEPS)[number]>('算法参数')
  const [tagValue, setTagValue] = useState<string[]>(caseItem?.tags ?? [])
  const [groupValue, setGroupValue] = useState(caseItem?.groupId ?? presetGroupId ?? '')
  const [newGroupName, setNewGroupName] = useState('')

  const groupOptions = [
    ...groups.map((g) => ({ value: g.id, label: g.name })),
    { value: '__new__', label: '+ 新建分组' },
  ]

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='w-full sm:max-w-[1280px]'>
        <SheetHeader className='border-b'>
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div>
              <SheetTitle>{isEdit ? '编辑测试用例' : '新增测试用例'}</SheetTitle>
              <SheetDescription>
                {isEdit
                  ? `正在编辑「${caseItem?.name}」，统一管理端到端测试用例和 API 测试用例`
                  : '统一管理端到端测试用例和 API 测试用例'}
              </SheetDescription>
            </div>
            {/* 头部类型切换（默认胶囊；编辑态锁定显示类型 Badge） */}
            {isEdit ? (
              <Badge variant='outline' className='gap-1 rounded-md px-1.5'>
                {caseItem?.type === 'api' ? 'API 测试' : '端到端测试'}
              </Badge>
            ) : (
              <Tabs value={testType} onValueChange={(v) => setTestType(v as 'api' | 'e2e')}>
                <TabsList variant='default'>
                  <TabsTrigger value='api'>API</TabsTrigger>
                  <TabsTrigger value='e2e'>E2E</TabsTrigger>
                </TabsList>
              </Tabs>
            )}
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
                    defaultValue={caseItem?.name ?? ''}
                    placeholder='请输入用例名称'
                    className='h-8'
                  />
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='h-8 shrink-0 gap-1'
                    onClick={() => toast.success('已按标签升序自动生成名称（演示）')}
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
              <Select defaultValue={caseItem?.algorithmType ?? ''}>
                <SelectTrigger size='sm' className='h-8 w-full sm:w-80'>
                  <SelectValue placeholder='请选择算法' />
                </SelectTrigger>
                <SelectContent>
                  {MOCK_ALGORITHMS.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </section>

            {/* 轮次配置 */}
            <section className='border-border/60 border-t pt-4'>
              <div className='mb-2 flex items-center justify-between'>
                <Label className='text-base font-medium'>轮次配置</Label>
                <div className='flex gap-2'>
                  <Button type='button' variant='ghost' size='sm' className='h-7 gap-1'>
                    <Plus aria-hidden='true' className='size-3.5' />
                    添加轮次
                  </Button>
                  <Button type='button' variant='ghost' size='sm' className='h-7 gap-1'>
                    复制当前轮次
                  </Button>
                </div>
              </div>
              <div className='rounded-lg border'>
                <div className='flex min-h-64 flex-col sm:flex-row'>
                  {/* 左：轮次导航（180px） */}
                  <div className='border-border/60 shrink-0 border-b p-2 sm:w-44 sm:border-r sm:border-b-0'>
                    <div className='space-y-1.5'>
                      {[1, 2].map((n) => (
                        <button
                          key={n}
                          type='button'
                          className={cn(
                            'hover:bg-accent flex w-full items-center justify-between rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                            n === 1 && 'bg-accent'
                          )}
                        >
                          <span className='font-medium'>第 {n} 轮</span>
                          <span className='text-muted-foreground text-xs'>
                            {n === 1 ? '2 音频·1 维度' : '1 音频·2 维度'}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                  {/* 右：步骤区横向锚点 Tabs line */}
                  <div className='min-h-64 flex-1'>
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
                      <StepPlaceholder step={step} />
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </ScrollArea>

        <SheetFooter className='border-t'>
          <div className='flex justify-end gap-2'>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button onClick={() => {
              toast.success(isEdit ? '更新测试用例成功' : '添加测试用例成功')
              onOpenChange(false)
            }}>
              保存
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function StepPlaceholder({ step }: { step: (typeof STEPS)[number] }) {
  const notes: Record<(typeof STEPS)[number], string> = {
    算法参数: '按算法 schema 渲染 DynamicForm；排除 voiceprint / interferers / audio_select 类型参数（归后两步）。',
    音频列表: '音频卡列表（拖拽排序 GripVertical）——音频文件 Combobox、播放设备、声压级 dB；工具栏排序/标签交错/设备交叉。',
    噪声与干扰: '（仅 E2E）背景噪声节 + 声纹注册配置节 + 干扰人配置节（干扰音频/播放设备/声压/开始延迟/循环播放）。',
    评估维度: '维度 chips 多选区（按当前算法过滤可用维度）+ 已选维度参数卡（权重 Slider + 阈值 + LLM Judge 配置）。',
    参考参数: '路径行 FolderOpen + 参考参数路径；未生成时空态「参考参数将在音频关联后自动生成」；编辑态 Textarea mono + 保存。',
  }
  return (
    <div className='flex items-center gap-3'>
      <span aria-hidden='true' className='text-2xl'>📋</span>
      <p className='text-muted-foreground text-xs leading-relaxed'>{notes[step]}</p>
    </div>
  )
}
