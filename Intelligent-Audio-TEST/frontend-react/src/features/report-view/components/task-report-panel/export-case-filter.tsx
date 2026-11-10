/**
 * 导出产物里的「具体用例」筛选面板（INT-2434 二轮）。
 *
 * 负责人反馈导出 HTML「筛选功能不完整」——上一版产物只剩一个关键词搜索框，页面上的
 * 用例分组 / 用例标签 / 评估维度 / 排序全部消失。导出没有后端，筛选改在产物内做纯 DOM 过滤：
 * 这里用原生 `input` / `select` / `details` 渲染面板（克隆时由 `html-snapshot` 保留，
 * 交互由产物内联脚本接管），选项与页面筛选卡同源（分组 / 标签两级 / 维度三级）。
 *
 * 只在导出态渲染；页面常规态仍用原筛选卡（服务端筛选）。
 */
import type {
  DimensionTreeSection,
  TagTreeSection,
} from '@/application/report-view/use-report-filter-taxonomy'

export interface ExportCaseFilterProps {
  /** 用例分组（分类）选项与命中数 */
  groups: { name: string; count: number }[]
  /** 标签两级树（分类 → 标签） */
  tagSections: TagTreeSection[]
  /** 标签 → 用例数 */
  tagCounts: Record<string, number>
  /** 评估维度三级树（分类 → 主维度 → 子维度） */
  dimensionSections: DimensionTreeSection[]
  /** 「按评估维度」排序可选的维度名 */
  metricNames: string[]
  /** 用例总数（未筛选） */
  total: number
}

const CONTROL_CLASS =
  'h-7 rounded-md border border-[#d1d5db] bg-white px-2 text-xs text-[#111827]'

const CHECK_ROW_CLASS =
  'flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs text-[#374151] hover:bg-[#f1f5f9]'

export function ExportCaseFilterPanel({
  groups,
  tagSections,
  tagCounts,
  dimensionSections,
  metricNames,
  total,
}: ExportCaseFilterProps) {
  const tagCount = tagSections.reduce((sum, section) => sum + section.tags.length, 0)
  const dimensionCount = dimensionSections.reduce(
    (sum, section) =>
      sum + section.groups.reduce((inner, group) => inner + 1 + group.subs.length, 0),
    0
  )

  return (
    <div
      data-export-filter-panel=''
      data-export-filter-total={String(total)}
      className='space-y-2 rounded-xl border border-[#e5e7eb] bg-[#f8fafc] p-3'
    >
      {/* 关键词 + 排序（与页面筛选卡同一组字段） */}
      <div className='flex flex-wrap items-end gap-2'>
        <label className='flex flex-col gap-1 text-xs text-[#6b7280]'>
          用例名称
          <input
            id='export-case-search'
            type='search'
            data-export-filter-keyword=''
            placeholder='输入用例ID、名称或描述关键词'
            autoComplete='off'
            className={CONTROL_CLASS}
            style={{ width: 240 }}
          />
        </label>
        <label className='flex flex-col gap-1 text-xs text-[#6b7280]'>
          排序方式
          <select data-export-filter-sort='' className={CONTROL_CLASS} defaultValue=''>
            <option value=''>保持页面顺序</option>
            <option value='name'>按名称</option>
            <option value='testcaseid'>按创建时间</option>
            <option value='metric'>按评估维度</option>
          </select>
        </label>
        <label className='flex flex-col gap-1 text-xs text-[#6b7280]'>
          评估维度
          <select data-export-filter-sort-metric='' className={CONTROL_CLASS}>
            {metricNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className='flex flex-col gap-1 text-xs text-[#6b7280]'>
          排序方向
          <select data-export-filter-sort-order='' className={CONTROL_CLASS} defaultValue='asc'>
            <option value='asc'>升序</option>
            <option value='desc'>降序</option>
          </select>
        </label>
        <button
          type='button'
          data-export-filter-reset=''
          className='h-7 rounded-md border border-[#d1d5db] bg-white px-2.5 text-xs text-[#374151]'
        >
          重置筛选
        </button>
        <span
          data-export-filter-count=''
          className='ms-auto self-center text-xs text-[#6b7280]'
        >
          共 {total} 个用例
        </span>
      </div>

      {/* 用例分组（分类）多选 */}
      <div className='border-t border-[#e5e7eb] pt-2'>
        <span className='text-xs font-medium text-[#6b7280]'>用例分组</span>
        <div className='mt-1 flex flex-wrap gap-x-3 gap-y-1'>
          {groups.length === 0 ? (
            <span className='text-xs text-[#9ca3af]'>无分组</span>
          ) : (
            groups.map((group) => (
              <label key={group.name} className={CHECK_ROW_CLASS}>
                <input type='checkbox' data-export-filter-group={group.name} />
                <span>{group.name}</span>
                <span className='text-[#9ca3af]'>{group.count}</span>
              </label>
            ))
          )}
        </div>
      </div>

      {/* 用例标签（分类 → 标签两级） */}
      <details className='border-t border-[#e5e7eb] pt-2'>
        <summary className='cursor-pointer text-xs font-medium text-[#6b7280]'>
          用例标签（{tagCount}）
        </summary>
        <div className='mt-1 space-y-1'>
          {tagSections.map((section) => (
            <div key={section.key}>
              <p className='text-[11px] text-[#9ca3af]'>{section.name}</p>
              <div className='flex flex-wrap gap-x-3 gap-y-1'>
                {section.tags.map((tag) => (
                  <label key={tag} className={CHECK_ROW_CLASS}>
                    <input type='checkbox' data-export-filter-tag={tag} />
                    <span>{tag}</span>
                    <span className='text-[#9ca3af]'>{tagCounts[tag] ?? 0}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </details>

      {/* 评估维度（分类 → 主维度 → 子维度三级） */}
      <details className='border-t border-[#e5e7eb] pt-2'>
        <summary className='cursor-pointer text-xs font-medium text-[#6b7280]'>
          评估维度（{dimensionCount}）
        </summary>
        <div className='mt-1 space-y-1'>
          {dimensionSections.map((section) => (
            <div key={section.key}>
              <p className='text-[11px] text-[#9ca3af]'>{section.name}</p>
              {section.groups.map((group) => (
                <div key={`${section.key}:${group.main}`} className='ms-2'>
                  <label className={CHECK_ROW_CLASS}>
                    <input type='checkbox' data-export-filter-metric={group.main} />
                    <span>{group.main}</span>
                  </label>
                  {group.subs.map((sub) => (
                    <label key={sub} className={`${CHECK_ROW_CLASS} ms-4`}>
                      <input type='checkbox' data-export-filter-metric={sub} />
                      <span className='ps-1'>{sub}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>
    </div>
  )
}
