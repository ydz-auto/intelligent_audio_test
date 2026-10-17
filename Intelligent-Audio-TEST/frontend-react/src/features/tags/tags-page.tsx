/**
 * 标签管理页（11_用例域.md §4.2：左分类树 + 右标签表，lg 双列，SectionPageLayout 装配）。
 * 工作台壳（AppHeader+AppSidebar）由 AuthenticatedLayout 提供，本组件只出内容。
 * 交互：分类树 300ms 防抖搜索 + 滚动触底追加；选中分类后右表按 categoryId 过滤；
 * 「未分类」视图（null）= 现实现口径展示全量标签 + 所属分类列可见；标签/分类表单弹窗 §5.4。
 * RBAC：写权限缺失时写钮禁用 + Tooltip「无 {code} 权限」（基座 §9.2 规则 3）。
 */
import { Link } from '@tanstack/react-router'
import { Pencil, Plus, Search, Tags, Trash2 } from 'lucide-react'
import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
} from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useTagCategories,
  useTagMutations,
  useTags,
} from '@/application/tags/useTags'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { TagCategory, TagItem } from '@/domain/models/testTag'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  SCROLL_LOAD_MORE_THRESHOLD,
  TAG_LIST_PAGE_SIZE,
  TAG_SEARCH_DEBOUNCE_MS,
  UNCATEGORIZED_COLOR,
} from '@/features/tags/constants'
import {
  TagCategoryDialog,
  TagEditDialog,
} from '@/features/tags/tag-mutate-dialog'
import {
  TagConfirmDialog,
  type TagConfirmState,
} from '@/features/tags/tag-confirms'

/** 300ms 防抖搜索状态：返回 [输入值, 变更回调, 已提交值]（§4.2 300ms） */
function useDebouncedSearch(initial = '') {
  const [value, setValue] = useState(initial)
  const [committed, setCommitted] = useState(initial)
  const timerRef = useRef<number | null>(null)

  const handleChange = useCallback((next: string) => {
    setValue(next)
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(
      () => setCommitted(next.trim()),
      TAG_SEARCH_DEBOUNCE_MS
    )
  }, [])

  return [value, handleChange, committed] as const
}

/** 写权限禁用包装：无权限时按钮置灰 + Tooltip「无 {code} 权限」（基座 §9.2 规则 3） */
function PermissionButton({
  allowed,
  code,
  className,
  ...props
}: ComponentProps<typeof Button> & {
  allowed: boolean
  code: string
}) {
  const button = <Button disabled={!allowed} className={className} {...props} />
  if (allowed) return button
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span tabIndex={0} className='inline-flex cursor-not-allowed'>
            {button}
          </span>
        }
      />
      <TooltipContent>无 {code} 权限</TooltipContent>
    </Tooltip>
  )
}

/* ───────────────────────── 主页面装配 ───────────────────────── */

export function TagManagementPage() {
  const { hasPermission } = usePermissions()
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(
    null
  )
  const [confirmPending, setConfirmPending] = useState(false)

  // 标签/分类 mutation（invalidate ['tags'] 前缀，三页联动刷新）
  const {
    createTagMutation,
    updateTagMutation,
    deleteTagMutation,
    createCategoryMutation,
    updateCategoryMutation,
    deleteCategoryMutation,
  } = useTagMutations()

  // 搜索（防抖提交值驱动 query；输入值受控随提交同步）
  const [categoryInput, handleCategorySearch, categoryKeyword] = useDebouncedSearch()
  const [tagInput, handleTagSearch, tagKeyword] = useDebouncedSearch()

  // 弹窗状态
  const [tagDialog, setTagDialog] = useState<{
    open: boolean
    tag: TagItem | null
  }>({ open: false, tag: null })
  const [categoryDialog, setCategoryDialog] = useState<{
    open: boolean
    category: TagCategory | null
  }>({ open: false, category: null })
  const [confirm, setConfirm] = useState<TagConfirmState | null>(null)

  // 全量（未分类计数对账 + Select 选项 + 新建分类排序）
  const allCategories = useTagCategories()
  const allTags = useTags(null, '')
  // 左树 / 右表（防抖 keyword 过滤）
  const categoriesQuery = useTagCategories(categoryKeyword)
  const tagsQuery = useTags(selectedCategoryId, tagKeyword)

  const categories = categoriesQuery.data ?? []
  const tags = tagsQuery.data ?? []

  /** 未分类计数（现实现口径：总标签数 − Σ分类计数，兜底 0） */
  const uncategorizedCount = useMemo(() => {
    const sum =
      allCategories.data?.reduce((acc, c) => acc + c.tagCount, 0) ?? 0
    return Math.max(0, (allTags.data?.length ?? 0) - sum)
  }, [allCategories.data, allTags.data])

  const currentCategoryName = useMemo(() => {
    if (selectedCategoryId === null) return '未分类'
    const cat = allCategories.data?.find((c) => c.id === selectedCategoryId)
    return cat ? cat.name : '未分类'
  }, [selectedCategoryId, allCategories.data])

  /** 新建分类默认排序 = 末位 + 1（现 openCategoryModal 口径） */
  const nextSortOrder = (allCategories.data?.length ?? 0) + 1

  const handleConfirm = async (state: TagConfirmState) => {
    if (confirmPending) return
    setConfirmPending(true)
    try {
      if (state.kind === 'delete-tag') {
        // DELETE /api/v1/tags/{id}?cascade=false（软删不级联）
        await deleteTagMutation.mutateAsync(state.id!)
        toast.success('标签删除成功')
      } else {
        // DELETE /api/v1/tags/categories/{id}（空分类才可删）
        await deleteCategoryMutation.mutateAsync(state.id!)
        toast.success('分类删除成功')
        // 选中分类被删时回到未分类视图（现实现口径）
        if (state.id != null && selectedCategoryId === state.id) {
          setSelectedCategoryId(null)
        }
      }
    } catch (err) {
      const message =
        err instanceof ApiError ? err.userMessage : '删除失败，请稍后重试'
      toast.error(message)
    } finally {
      setConfirmPending(false)
      setConfirm(null)
    }
  }

  const selectCategory = (id: number | null) => setSelectedCategoryId(id)

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Breadcrumb>
          <nav aria-label='面包屑' className='text-sm'>
            <ol className='flex flex-wrap items-center gap-1.5'>
              <li>
                <Link
                  to='/dashboard'
                  className='text-muted-foreground hover:text-foreground transition-colors'
                >
                  工作台
                </Link>
              </li>
              <li aria-hidden='true' className='text-muted-foreground/50'>
                /
              </li>
              <li aria-current='page' className='text-foreground font-medium'>
                标签管理
              </li>
            </ol>
          </nav>
        </SectionPageLayout.Breadcrumb>

        <SectionPageLayout.Title>标签管理</SectionPageLayout.Title>
        <SectionPageLayout.Actions>
          <p className='text-muted-foreground mr-auto text-sm'>
            管理标签分类和标签，用于用例筛选和报告统计
          </p>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='grid h-full min-h-0 auto-rows-min gap-3 lg:auto-rows-fr lg:grid-cols-[minmax(280px,320px)_minmax(0,1fr)]'>
            <CategoryTreeCard
              categories={categories}
              loading={categoriesQuery.isLoading}
              total={categoriesQuery.data?.length ?? 0}
              uncategorizedCount={uncategorizedCount}
              selectedCategoryId={selectedCategoryId}
              onSelect={selectCategory}
              searchValue={categoryInput}
              onSearch={handleCategorySearch}
              canCreate={hasPermission('tag:create')}
              canUpdate={hasPermission('tag:update')}
              canDelete={hasPermission('tag:delete')}
              onCreate={() => setCategoryDialog({ open: true, category: null })}
              onEdit={(cat) => setCategoryDialog({ open: true, category: cat })}
              onDelete={(cat) =>
                setConfirm({
                  kind: 'delete-category',
                  name: cat.name,
                  id: cat.id,
                })
              }
            />

            <TagTableCard
              tags={tags}
              loading={tagsQuery.isLoading}
              total={tags.length}
              currentCategoryName={currentCategoryName}
              showCategoryColumn={selectedCategoryId === null}
              categoryId={selectedCategoryId}
              keyword={tagKeyword}
              searchValue={tagInput}
              onSearch={handleTagSearch}
              canCreate={hasPermission('tag:create')}
              canUpdate={hasPermission('tag:update')}
              canDelete={hasPermission('tag:delete')}
              onCreate={() => setTagDialog({ open: true, tag: null })}
              onEdit={(tag) => setTagDialog({ open: true, tag })}
              onDelete={(tag) =>
                setConfirm({ kind: 'delete-tag', name: tag.name, id: tag.id })
              }
            />
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§5.4 + §4.2 删除确认） */}
      <TagEditDialog
        open={tagDialog.open}
        onOpenChange={(open) => {
          if (!open) setTagDialog({ open: false, tag: null })
          else setTagDialog((prev) => ({ ...prev, open: true }))
        }}
        tag={tagDialog.tag}
        categories={allCategories.data ?? []}
        presetCategoryId={selectedCategoryId}
        onSubmit={async (draft, id) => {
          if (id != null) await updateTagMutation.mutateAsync({ id, draft })
          else await createTagMutation.mutateAsync(draft)
        }}
      />
      <TagCategoryDialog
        open={categoryDialog.open}
        onOpenChange={(open) => {
          if (!open) setCategoryDialog({ open: false, category: null })
          else setCategoryDialog((prev) => ({ ...prev, open: true }))
        }}
        category={categoryDialog.category}
        nextSortOrder={nextSortOrder}
        onSubmit={async (draft, id) => {
          if (id != null)
            await updateCategoryMutation.mutateAsync({ id, draft })
          else await createCategoryMutation.mutateAsync(draft)
        }}
      />
      <TagConfirmDialog
        open={confirm != null}
        onOpenChange={(open) => !open && setConfirm(null)}
        state={confirm}
        pending={confirmPending}
        onConfirm={handleConfirm}
      />
    </>
  )
}

/* ───────────────────────── 左列：分类树 ───────────────────────── */

function CategoryTreeCard({
  categories,
  loading,
  total,
  uncategorizedCount,
  selectedCategoryId,
  onSelect,
  searchValue,
  onSearch,
  canCreate,
  canUpdate,
  canDelete,
  onCreate,
  onEdit,
  onDelete,
}: {
  categories: TagCategory[]
  loading: boolean
  total: number
  uncategorizedCount: number
  selectedCategoryId: number | null
  onSelect: (id: number | null) => void
  searchValue: string
  onSearch: (keyword: string) => void
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  onCreate: () => void
  onEdit: (cat: TagCategory) => void
  onDelete: (cat: TagCategory) => void
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [visibleCount, setVisibleCount] = useState(TAG_LIST_PAGE_SIZE)

  const visible = useMemo(
    () => categories.slice(0, visibleCount),
    [categories, visibleCount]
  )
  const hasMore = visibleCount < categories.length

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el || !hasMore) return
    if (
      el.scrollHeight - el.scrollTop - el.clientHeight <
      SCROLL_LOAD_MORE_THRESHOLD
    ) {
      setVisibleCount((prev) => prev + TAG_LIST_PAGE_SIZE)
    }
  }, [hasMore])

  // 数据变化（搜索/加载）时重置到首屏（React 渲染期调整派生状态官方模式）
  const listKey = `${total}|${uncategorizedCount}`
  const prevListKeyRef = useRef(listKey)
  if (prevListKeyRef.current !== listKey) {
    prevListKeyRef.current = listKey
    setVisibleCount(TAG_LIST_PAGE_SIZE)
  }

  return (
    <Card size='sm' className='min-h-0 gap-0'>
      <CardHeader className='px-3 pt-3 sm:px-4'>
        <CardTitle className='flex flex-wrap items-center gap-2'>
          <span className='flex items-center gap-1.5'>
            <Tags aria-hidden='true' className='text-muted-foreground size-4' />
            标签分类
          </span>
          <span className='text-muted-foreground text-xs font-normal tabular-nums'>
            共 {total} 个
          </span>
        </CardTitle>
        <CardAction>
          <PermissionButton
            allowed={canCreate}
            code='tag:create'
            variant='outline'
            size='sm'
            className='h-7 gap-1.5'
            onClick={onCreate}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新建
          </PermissionButton>
        </CardAction>
      </CardHeader>
      <CardContent className='px-3 pb-2 sm:px-4'>
        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
          />
          <Input
            aria-label='搜索分类'
            value={searchValue}
            onChange={(e) => onSearch(e.target.value)}
            placeholder='搜索分类...'
            className='h-8 pl-8'
          />
        </div>
      </CardContent>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className='min-h-0 flex-1 overflow-y-auto px-1.5 pb-2'
      >
        {loading ? (
          <div className='space-y-1 px-1.5 py-1'>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className='h-8 w-full rounded-md' />
            ))}
          </div>
        ) : (
          <div className='space-y-0.5'>
            {visible.map((cat) => {
              const active = selectedCategoryId === cat.id
              const deleteBlocked = (cat.tagCount ?? 0) > 0
              return (
                <div
                  key={cat.id}
                  className={cn(
                    'hover:bg-accent group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                    active && 'bg-accent'
                  )}
                >
                  <button
                    type='button'
                    onClick={() => onSelect(cat.id)}
                    className='flex min-w-0 flex-1 items-center gap-2 text-start'
                  >
                    <span
                      aria-hidden='true'
                      className='size-2 shrink-0 rounded-full'
                      style={{
                        backgroundColor: cat.color ?? UNCATEGORIZED_COLOR,
                      }}
                    />
                    <span className='min-w-0 flex-1 truncate'>
                      {cat.name}
                    </span>
                    <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 text-xs tabular-nums'>
                      {cat.tagCount}
                    </span>
                  </button>
                  {active && (
                    <span className='flex shrink-0 items-center gap-0.5'>
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            !canUpdate ? (
                              <span
                                tabIndex={0}
                                className='inline-flex cursor-not-allowed'
                              >
                                <Button
                                  variant='ghost'
                                  size='icon-sm'
                                  aria-label={`编辑分类 ${cat.name}`}
                                  disabled={!canUpdate}
                                  onClick={() => onEdit(cat)}
                                >
                                  <Pencil
                                    aria-hidden='true'
                                    className='size-3.5'
                                  />
                                </Button>
                              </span>
                            ) : (
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                aria-label={`编辑分类 ${cat.name}`}
                                onClick={() => onEdit(cat)}
                              >
                                <Pencil
                                  aria-hidden='true'
                                  className='size-3.5'
                                />
                              </Button>
                            )
                          }
                        />
                        <TooltipContent>
                          {canUpdate ? '编辑分类' : '无 tag:update 权限'}
                        </TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            !canDelete || deleteBlocked ? (
                              <span
                                tabIndex={0}
                                className='inline-flex cursor-not-allowed'
                              >
                                <Button
                                  variant='ghost'
                                  size='icon-sm'
                                  className='text-destructive'
                                  aria-label={`删除分类 ${cat.name}`}
                                  disabled={!canDelete || deleteBlocked}
                                  onClick={() => onDelete(cat)}
                                >
                                  <Trash2
                                    aria-hidden='true'
                                    className='size-3.5'
                                  />
                                </Button>
                              </span>
                            ) : (
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                className='text-destructive'
                                aria-label={`删除分类 ${cat.name}`}
                                onClick={() => onDelete(cat)}
                              >
                                <Trash2
                                  aria-hidden='true'
                                  className='size-3.5'
                                />
                              </Button>
                            )
                          }
                        />
                        <TooltipContent>
                          {deleteBlocked
                            ? `该分类下还有 ${cat.tagCount} 个标签，请先移除或迁移标签`
                            : canDelete
                              ? '删除分类'
                              : '无 tag:delete 权限'}
                        </TooltipContent>
                      </Tooltip>
                    </span>
                  )}
                </div>
              )
            })}

            {/* 未分类固定尾项（#94a3b8 色点，§4.2） */}
            <div
              className={cn(
                'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                selectedCategoryId === null && 'bg-accent'
              )}
            >
              <button
                type='button'
                onClick={() => onSelect(null)}
                className='flex min-w-0 flex-1 items-center gap-2 text-start'
              >
                <span
                  aria-hidden='true'
                  className='size-2 shrink-0 rounded-full'
                  style={{ backgroundColor: UNCATEGORIZED_COLOR }}
                />
                <span className='min-w-0 flex-1 truncate'>未分类</span>
                <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 text-xs tabular-nums'>
                  {uncategorizedCount}
                </span>
              </button>
            </div>

            <p className='text-muted-foreground px-2 py-1.5 text-xs'>
              {hasMore
                ? '加载中...'
                : total > 0 || uncategorizedCount > 0
                  ? '已加载全部'
                  : ''}
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}

/* ───────────────────────── 右列：标签表 ───────────────────────── */

function TagTableCard({
  tags,
  loading,
  total,
  currentCategoryName,
  showCategoryColumn,
  categoryId,
  keyword,
  searchValue,
  onSearch,
  canCreate,
  canUpdate,
  canDelete,
  onCreate,
  onEdit,
  onDelete,
}: {
  tags: TagItem[]
  loading: boolean
  total: number
  currentCategoryName: string
  showCategoryColumn: boolean
  categoryId: number | null
  keyword: string
  searchValue: string
  onSearch: (keyword: string) => void
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  onCreate: () => void
  onEdit: (tag: TagItem) => void
  onDelete: (tag: TagItem) => void
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [visibleCount, setVisibleCount] = useState(TAG_LIST_PAGE_SIZE)

  const visible = useMemo(() => tags.slice(0, visibleCount), [tags, visibleCount])
  const hasMore = visibleCount < tags.length
  const isEmpty = !loading && tags.length === 0

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el || !hasMore) return
    if (
      el.scrollHeight - el.scrollTop - el.clientHeight <
      SCROLL_LOAD_MORE_THRESHOLD
    ) {
      setVisibleCount((prev) => prev + TAG_LIST_PAGE_SIZE)
    }
  }, [hasMore])

  // 数据变化（分类切换/搜索）时重置到首屏
  const listKey = `${categoryId}|${keyword}`
  const prevListKeyRef = useRef(listKey)
  if (prevListKeyRef.current !== listKey) {
    prevListKeyRef.current = listKey
    setVisibleCount(TAG_LIST_PAGE_SIZE)
  }

  return (
    <Card size='sm' className='min-h-0 gap-0'>
      <CardHeader className='px-3 pt-3 sm:px-4'>
        <CardTitle className='flex flex-wrap items-center gap-2'>
          <span className='truncate'>{currentCategoryName}</span>
          <span className='text-muted-foreground text-xs font-normal tabular-nums'>
            共 {total} 个标签
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className='px-3 pb-2 sm:px-4'>
        <div className='flex items-center gap-2'>
          <div className='relative min-w-0 flex-1'>
            <Search
              aria-hidden='true'
              className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
            />
            <Input
              aria-label='搜索标签'
              value={searchValue}
              onChange={(e) => onSearch(e.target.value)}
              placeholder='搜索标签...'
              className='h-8 pl-8'
            />
          </div>
          <PermissionButton
            allowed={canCreate}
            code='tag:create'
            variant='outline'
            size='sm'
            className='h-8 shrink-0 gap-1.5'
            onClick={onCreate}
          >
            <Plus aria-hidden='true' className='size-3.5' />
            新建标签
          </PermissionButton>
        </div>
      </CardContent>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className='min-h-0 flex-1 overflow-y-auto px-3 pb-3 sm:px-4'
      >
        {loading ? (
          <div className='rounded-xl border'>
            <Skeleton className='h-10 w-full rounded-none border-b' />
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className='h-11 w-full rounded-none border-b' />
            ))}
          </div>
        ) : isEmpty ? (
          <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
            <Empty className='h-72'>
              <EmptyMedia variant='icon'>
                <Tags aria-hidden='true' className='size-4' />
              </EmptyMedia>
              <EmptyHeader>
                <EmptyTitle>
                  {keyword ? '没有找到匹配的标签' : '暂无标签'}
                </EmptyTitle>
                <EmptyDescription>
                  {keyword
                    ? '调整搜索关键词后重试'
                    : '点击「新建标签」创建第一个标签，用于用例筛选'}
                </EmptyDescription>
              </EmptyHeader>
              {!keyword && (
                <EmptyContent>
                  <PermissionButton
                    allowed={canCreate}
                    code='tag:create'
                    variant='outline'
                    size='sm'
                    onClick={onCreate}
                  >
                    <Plus aria-hidden='true' className='size-3.5' />
                    创建第一个标签
                  </PermissionButton>
                </EmptyContent>
              )}
            </Empty>
          </div>
        ) : (
          <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
            <div className='overflow-x-auto'>
              <table className='w-full min-w-0 text-[13px]'>
                <thead>
                  <tr className='bg-[var(--table-header)] text-xs'>
                    <th className='px-3 py-2 text-left font-medium'>标签</th>
                    {showCategoryColumn && (
                      <th className='px-3 py-2 text-left font-medium'>
                        所属分类
                      </th>
                    )}
                    <th className='px-3 py-2 text-left font-medium'>描述</th>
                    <th className='w-20 px-3 py-2 text-right font-medium'>
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((tag) => {
                    const color = tag.color ?? UNCATEGORIZED_COLOR
                    return (
                      <tr
                        key={tag.id}
                        className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'
                      >
                        <td className='px-3 py-2'>
                          <div className='flex min-w-0 items-center gap-2'>
                            <span
                              aria-hidden='true'
                              className='size-2 shrink-0 rounded-full'
                              style={{ backgroundColor: color }}
                            />
                            <span
                              className='min-w-0 truncate font-medium'
                              title={tag.name}
                            >
                              {tag.name}
                            </span>
                          </div>
                        </td>
                        {showCategoryColumn && (
                          <td className='px-3 py-2'>
                            <span
                              className='inline-flex h-5 items-center rounded-md border border-border bg-muted/50 px-1.5 text-xs'
                              style={
                                tag.categoryName
                                  ? {
                                      color,
                                      borderColor: `${color}40`,
                                      backgroundColor: `${color}1a`,
                                    }
                                  : undefined
                              }
                            >
                              {tag.categoryName ?? '未分类'}
                            </span>
                          </td>
                        )}
                        <td className='max-w-56 px-3 py-2'>
                          <p
                            className='text-muted-foreground truncate'
                            title={tag.description ?? ''}
                          >
                            {tag.description ?? '—'}
                          </p>
                        </td>
                        <td className='px-3 py-2'>
                          <div className='flex items-center justify-end gap-0.5'>
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <Button
                                    variant='ghost'
                                    size='icon-sm'
                                    aria-label={`编辑标签 ${tag.name}`}
                                    disabled={!canUpdate}
                                    onClick={() => onEdit(tag)}
                                  />
                                }
                              >
                                <Pencil aria-hidden='true' className='size-3.5' />
                              </TooltipTrigger>
                              <TooltipContent>
                                {canUpdate
                                  ? '编辑标签'
                                  : '无 tag:update 权限'}
                              </TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <Button
                                    variant='ghost'
                                    size='icon-sm'
                                    className='text-destructive'
                                    aria-label={`删除标签 ${tag.name}`}
                                    disabled={!canDelete}
                                    onClick={() => onDelete(tag)}
                                  />
                                }
                              >
                                <Trash2 aria-hidden='true' className='size-3.5' />
                              </TooltipTrigger>
                              <TooltipContent>
                                {canDelete ? '删除标签' : '无 tag:delete 权限'}
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className='text-muted-foreground px-3 py-2 text-xs tabular-nums'>
              {hasMore ? '加载中...' : `已加载全部 ${total} 个标签`}
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}
