/**
 * HTML 快照导出静态化单测（INT-2418）：只覆盖克隆清理 / 用例分页标记 / 文档组装这些纯 DOM 逻辑，
 * 打包与网络抓取留给 build + 15173 实测（jsdom 无真实样式表与 canvas 位图）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildReportHtmlDocument,
  buildStaticClone,
  captureReportHtmlSnapshot,
  HTML_EXPORT_CASE_PAGE_SIZE,
  REPORT_EXPORT_SCRIPT,
  sanitizeFileName,
} from '../html-snapshot'
import { exportShowMarker } from '../export-markers'

function mountReportDom(caseCount: number): HTMLElement {
  const root = document.createElement('div')
  root.className = 'report-view-container'
  root.innerHTML = `
    <div class="content">
      <header>
        <button id="action-save">保存</button>
        <button id="action-publish">发布</button>
      </header>
      <aside class="nav">右导航</aside>
      <section id="report-specific-cases">
        <div data-slot="collapsible">
          <button data-slot="collapsible-trigger">具体用例</button>
          <div data-slot="collapsible-panel">
            <div data-export-filter-panel="">
              <input id="export-case-search" type="search" data-export-filter-keyword="" />
              <select data-export-filter-sort="">
                <option value="">保持页面顺序</option>
                <option value="name">按名称</option>
              </select>
              <select data-export-filter-sort-order="">
                <option value="asc">升序</option>
                <option value="desc">降序</option>
              </select>
              <label><input type="checkbox" data-export-filter-group="话轮接管" />话轮接管</label>
              <label><input type="checkbox" data-export-filter-group="别的组" />别的组</label>
              <label><input type="checkbox" data-export-filter-tag="标签A" />标签A</label>
              <label><input type="checkbox" data-export-filter-metric="接管率" />接管率</label>
              <label><input type="checkbox" data-export-filter-metric="不存在的维度" />不存在的维度</label>
              <button type="button" data-export-filter-reset="">重置筛选</button>
            </div>
            <div class="rounded-xl border p-3" data-export-hide>
              <button id="page-only-filter">页面筛选</button>
            </div>
            <div class="space-y-2" data-export-case-list>
              <div data-export-group="">
                <div class="group-header"><span data-export-group-count="">1 个用例</span></div>
                ${Array.from({ length: caseCount })
                  .map(
                    (_, index) => `
                <div data-export-case data-export-case-name="用例 ${index}" data-export-case-id="case-${index}"
                     data-export-case-category="话轮接管" data-export-case-tags='["标签A"]'
                     data-export-case-metrics='["接管率"]' data-export-case-metric-values='{"接管率":${index}}'>
                  <div class="case-card">
                    <button aria-label="展开详情" id="toggle-${index}">v</button>
                    <button id="detail-${index}">详情</button>
                    <div data-export-case-detail hidden>detail ${index}</div>
                  </div>
                </div>`
                  )
                  .join('')}
              </div>
            </div>
          </div>
        </div>
      </section>
      <div class="print:hidden sticky">底部操作条 <button>导出</button></div>
      <div data-export-cases-ready="true"></div>
    </div>`
  document.body.appendChild(root)
  return root
}

describe('buildStaticClone', () => {
  it('清掉导航/操作条/筛选卡，只保留折叠触发器与用例展开按钮', () => {
    const root = mountReportDom(3)
    const { clone } = buildStaticClone(root)
    // 页面上的右导航 aside 整块清掉；产物自己的目录右栏（data-export-toc-aside）是重建的
    expect(clone.querySelector('aside:not([data-export-toc-aside])')).toBeNull()
    expect(clone.querySelector('.print\\:hidden')).toBeNull()
    expect(clone.querySelector('[data-export-hide]')).toBeNull()
    expect(clone.querySelector('[data-export-cases-ready]')).toBeNull()
    expect(clone.querySelector('#action-save')).toBeNull()
    expect(clone.querySelector('#action-publish')).toBeNull()
    expect(clone.querySelector('#detail-0')).toBeNull()
    expect(clone.querySelector('[data-slot="collapsible-trigger"]')).not.toBeNull()
    expect(clone.querySelector('#toggle-0')).not.toBeNull()
    root.remove()
  })

  it('用例分页：超过一页的卡片默认隐藏，并插入分页/展开工具条（筛选面板由页面渲染保留）', () => {
    const root = mountReportDom(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    const { clone, caseCount } = buildStaticClone(root)
    expect(caseCount).toBe(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    expect(clone.getAttribute('data-export-case-total')).toBe(String(caseCount))
    const cards = Array.from(clone.querySelectorAll<HTMLElement>('[data-export-case]'))
    expect(cards).toHaveLength(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    expect(cards[0].style.display).toBe('')
    expect(cards[HTML_EXPORT_CASE_PAGE_SIZE].style.display).toBe('none')
    expect(clone.querySelector('[data-export-case-toolbar]')).not.toBeNull()
    expect(clone.querySelector('#export-case-expand-all')).not.toBeNull()
    expect(clone.querySelector('#export-case-collapse-all')).not.toBeNull()
    // 关键词输入在导出态筛选面板里（不再是工具条里临时拼的搜索框）
    expect(clone.querySelector('[data-export-filter-panel] #export-case-search')).not.toBeNull()
    root.remove()
  })

  it('导出态筛选面板整块保留（原生控件由产物脚本接管），页面操作控件仍剪（INT-2434 二轮）', () => {
    const root = mountReportDom(2)
    const { clone } = buildStaticClone(root)
    const panel = clone.querySelector('[data-export-filter-panel]')
    expect(panel).not.toBeNull()
    expect(panel!.querySelector('#export-case-search')).not.toBeNull()
    expect(panel!.querySelector('[data-export-filter-sort]')).not.toBeNull()
    expect(panel!.querySelector('[data-export-filter-group="话轮接管"]')).not.toBeNull()
    expect(panel!.querySelector('[data-export-filter-reset]')).not.toBeNull()
    // 页面筛选卡（data-export-hide）与它的按钮照旧剪掉
    expect(clone.querySelector('[data-export-hide]')).toBeNull()
    expect(clone.querySelector('#page-only-filter')).toBeNull()
    root.remove()
  })

  it('用例卡保留筛选事实（分组 / 标签 / 维度 / 维度值）与分组头计数位（INT-2434 二轮）', () => {
    const root = mountReportDom(2)
    const { clone } = buildStaticClone(root)
    const card = clone.querySelector('[data-export-case]')!
    expect(card.getAttribute('data-export-case-category')).toBe('话轮接管')
    expect(card.getAttribute('data-export-case-tags')).toBe('["标签A"]')
    expect(card.getAttribute('data-export-case-metrics')).toBe('["接管率"]')
    expect(card.getAttribute('data-export-case-metric-values')).toBe('{"接管率":0}')
    expect(clone.querySelector('[data-export-group]')).not.toBeNull()
    expect(clone.querySelector('[data-export-group-count]')).not.toBeNull()
    root.remove()
  })

  it('用例详情默认折叠、展开按钮交给导出脚本接管', () => {
    const root = mountReportDom(2)
    const { clone } = buildStaticClone(root)
    const detail = clone.querySelector('[data-export-case-detail]')
    expect(detail?.hasAttribute('hidden')).toBe(true)
    expect(clone.querySelector('#toggle-0')?.getAttribute('data-export-case-toggle')).toBe('')
    root.remove()
  })

  it('用例展开入口补可见文字（INT-2434：原按钮只有图标，产物里看不出可点）', () => {
    const root = mountReportDom(2)
    const { clone } = buildStaticClone(root)
    const label = clone.querySelector('#toggle-0 [data-export-case-toggle-label]')
    expect(label?.textContent).toBe('展开详情')
    root.remove()
  })

  it('导出内 Tab 按钮保留（轮次 / 维度 / 目标），普通操作按钮仍剪掉（INT-2434）', () => {
    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `
      <section id="report-specific-cases">
        <div data-export-case data-export-case-name="用例" data-export-case-id="c1">
          <button aria-label="展开详情">v</button>
          <div data-export-case-detail hidden>
            <div role="tablist" aria-label="轮次切换">
              <button role="tab" data-export-tab="case-1-round:round:1" aria-selected="true">第 1 轮</button>
              <button role="tab" data-export-tab="case-1-round:round:2" aria-selected="false">第 2 轮</button>
            </div>
            <div data-export-show='["case-1-round:round:1"]'>第一轮数据</div>
            <div data-export-show='["case-1-round:round:2"]'>第二轮数据</div>
            <button id="action-detail">详情</button>
          </div>
        </div>
      </section>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const tabs = clone.querySelectorAll('[role="tab"]')
    expect(tabs).toHaveLength(2)
    expect(
      Array.from(clone.querySelectorAll('[data-export-show]')).map((el) =>
        el.getAttribute('data-export-show')
      )
    ).toEqual(['["case-1-round:round:1"]', '["case-1-round:round:2"]'])
    expect(clone.querySelector('#action-detail')).toBeNull()
    root.remove()
  })

  it('按产物内分区重建「本页目录」，锚点与 section id 一一对应（INT-2434）', () => {
    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `
      <div class="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
        <main class="min-w-0 space-y-6">
          <section id="report-overview"><h3>总览</h3><div>统计</div></section>
          <section id="report-resource-stats">
            <div data-slot="collapsible">
              <button data-slot="collapsible-trigger">设备与 API</button>
              <div data-slot="collapsible-panel">内容</div>
            </div>
          </section>
          <section id="report-specific-cases">
            <div data-slot="collapsible">
              <button data-slot="collapsible-trigger">具体用例</button>
              <div data-slot="collapsible-panel">内容</div>
            </div>
          </section>
        </main>
        <aside class="print:hidden"><nav aria-label="本页目录"><button>总览</button></nav></aside>
      </div>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const nav = clone.querySelector('nav[aria-label="本页目录"]')
    expect(nav).not.toBeNull()
    const hrefs = Array.from(nav!.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['#report-overview', '#report-resource-stats', '#report-specific-cases'])
    // 每个锚点都能在产物里找到对应分区
    for (const href of hrefs) {
      expect(clone.querySelector(href as string)).not.toBeNull()
    }
    expect(nav!.textContent).toContain('总览')
    expect(nav!.textContent).toContain('具体用例')
    // 文案取报告页同一份目录定义（不是分区标题里的统计）
    expect(Array.from(nav!.querySelectorAll('a')).map((a) => a.textContent)).toEqual([
      '总览',
      '设备与API',
      '具体用例',
    ])
    // 视口固定的右栏：目录在正文右栏 aside 里（不是页顶横条），宿主标成两栏布局
    const aside = nav!.closest('aside[data-export-toc-aside]')
    expect(aside).not.toBeNull()
    const host = clone.querySelector('[data-export-layout]')
    expect(host).not.toBeNull()
    expect(host!.querySelector(':scope > main')).not.toBeNull()
    expect(host!.lastElementChild).toBe(aside)
    // 阅读进度条 + 每个分节一个锚点
    expect(nav!.querySelector('[data-export-toc-progress]')).not.toBeNull()
    expect(nav!.querySelectorAll('[data-export-toc-list] li')).toHaveLength(3)
    root.remove()
  })

  it('未登记在页面目录里的分区回退到标题文案（INT-2434）', () => {
    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `<section id="report-custom-block"><h3>自定义区块</h3><div>内容</div></section>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const links = Array.from(clone.querySelectorAll('[data-export-toc-link]'))
    expect(links.map((a) => a.textContent)).toEqual(['自定义区块'])
    root.remove()
  })

  it('文字即内容的按钮解包为文本（表头资源名 / 分组名 / 卡片标题），操作按钮仍删除', () => {
    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `
      <section id="report-case-category">
        <button data-export-keep-text>准确率 对比（单位：%）</button>
        <table>
          <thead>
            <tr>
              <th>分组</th>
              <th><button data-export-keep-text title="点击重命名资源">9-pura90小艺-1.0.0</button></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><button data-export-keep-text title="点击重命名分组">主流程</button></td>
              <td>90.0%</td>
            </tr>
          </tbody>
        </table>
        <button id="action-save">保存</button>
      </section>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const headers = clone.querySelectorAll('th')
    expect(headers[1].querySelector('button')).toBeNull()
    expect(headers[1].textContent?.trim()).toBe('9-pura90小艺-1.0.0')
    const firstCell = clone.querySelector('tbody td')
    expect(firstCell?.querySelector('button')).toBeNull()
    expect(firstCell?.textContent?.trim()).toBe('主流程')
    expect(clone.textContent).toContain('准确率 对比（单位：%）')
    expect(clone.querySelector('#action-save')).toBeNull()
    root.remove()
  })

  it('无 Collapsible 的分区（h3 + 内容）包出可折叠面板', () => {    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `<section id="report-overview"><h3>总览</h3><div class="body">统计</div></section>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const panel = clone.querySelector('[data-export-section-panel]')
    expect(panel).not.toBeNull()
    expect(panel?.querySelector('.body')).not.toBeNull()
    expect(clone.querySelector('[data-export-section-header]')).not.toBeNull()
    root.remove()
  })
})

describe('sanitizeFileName', () => {
  it('剔除非法字符并兜底 report', () => {
    expect(sanitizeFileName('报告/2026:11*?.zip')).toBe('报告202611.zip')
    expect(sanitizeFileName('   ')).toBe('report')
    expect(sanitizeFileName(undefined)).toBe('report')
  })
})

describe('buildReportHtmlDocument', () => {
  it('外链 css、内联交互脚本、导出时间戳齐全', () => {
    const root = mountReportDom(1)
    const { clone } = buildStaticClone(root)
    const html = buildReportHtmlDocument({
      clone,
      reportName: '测试<报告>',
      exportedAt: new Date('2026-11-09T08:00:00Z'),
    })
    expect(html).toContain('<link rel="stylesheet" href="css/report.css">')
    expect(html).toContain('测试&lt;报告&gt;')
    expect(html).toContain('data-export-case-toolbar')
    // 交互脚本内联（file:// 下不加载外部脚本）
    expect(html).toContain('export-case-search')
    expect(html).not.toContain('<script src=')
    root.remove()
  })
})

describe('captureReportHtmlSnapshot', () => {
  it('产出 report.html / css / 用例数片段（单份与批量共用同一管线，INT-2419）', async () => {
    const root = mountReportDom(2)
    const parts = await captureReportHtmlSnapshot(root, { fileName: '报告A' })
    expect(parts.caseCount).toBe(2)
    expect(parts.html).toContain('data-export-case-total="2"')
    expect(parts.html).toContain('<title>报告A - 报告导出</title>')
    // 导出 reset 与文档级样式都在同一份 css 里（主题变量取自 :root 计算值，jsdom 无自定义属性，实测在 15173 覆盖）
    expect(parts.css).toContain('#report-export-root')
    expect(parts.css).toContain('[data-export-case-toolbar]')
    // 导出内筛选面板样式 + 长字段取消截断（INT-2434 二轮）
    expect(parts.css).toContain('[data-export-filter-panel]')
    expect(parts.css).toContain('[data-export-case-detail] .line-clamp-2')
    root.remove()
  })
})

describe('REPORT_EXPORT_SCRIPT（产物内交互，INT-2434 二轮）', () => {
  function mountAndRun(caseCount: number): HTMLElement {
    const root = mountReportDom(caseCount)
    const { clone } = buildStaticClone(root)
    // 原页面 DOM 不留在文档里：断言只看产物克隆
    root.remove()
    document.body.appendChild(clone)
    new Function(REPORT_EXPORT_SCRIPT)()
    return clone
  }

  function visibleCards(): HTMLElement[] {
    return Array.from(document.querySelectorAll<HTMLElement>('[data-export-case]')).filter(
      (card) => card.style.display !== 'none'
    )
  }

  it('关键词检索命中名称 / ID（默认每页条数内全显示）', () => {
    const clone = mountAndRun(3)
    expect(visibleCards()).toHaveLength(3)
    const input = document.getElementById('export-case-search') as HTMLInputElement
    input.value = '用例 1'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    expect(visibleCards()).toHaveLength(1)
    expect(visibleCards()[0].getAttribute('data-export-case-name')).toBe('用例 1')
    clone.remove()
  })

  it('分组 / 标签 / 维度多选过滤，分组头计数与空组隐藏联动', () => {
    const clone = mountAndRun(3)
    const tick = (selector: string) => {
      const input = clone.querySelector<HTMLInputElement>(selector)!
      input.checked = true
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }
    // 不存在的分组 → 全部过滤掉，所在分组整块隐藏
    tick('[data-export-filter-group="别的组"]')
    expect(visibleCards()).toHaveLength(0)
    expect((clone.querySelector('[data-export-group]') as HTMLElement).style.display).toBe('none')
    // 选中有卡的分组 → 恢复，计数位同步
    const group = clone.querySelector<HTMLInputElement>('[data-export-filter-group="话轮接管"]')!
    group.checked = true
    group.dispatchEvent(new Event('change', { bubbles: true }))
    expect(visibleCards()).toHaveLength(3)
    expect(clone.querySelector('[data-export-group-count]')?.textContent).toBe('3 个用例')
    // 标签 / 维度任一命中即保留（卡片标签 = 标签A，维度 = 接管率）
    tick('[data-export-filter-tag="标签A"]')
    expect(visibleCards()).toHaveLength(3)
    tick('[data-export-filter-metric="不存在的维度"]')
    expect(visibleCards()).toHaveLength(0)
    clone.remove()
  })

  it('「全部展开 / 收起详情」与按名称排序', () => {
    const clone = mountAndRun(3)
    ;(document.getElementById('export-case-expand-all') as HTMLButtonElement).click()
    const details = Array.from(clone.querySelectorAll('[data-export-case-detail]'))
    expect(details.every((detail) => !detail.hasAttribute('hidden'))).toBe(true)
    ;(document.getElementById('export-case-collapse-all') as HTMLButtonElement).click()
    expect(details.every((detail) => detail.hasAttribute('hidden'))).toBe(true)

    const sort = clone.querySelector<HTMLSelectElement>('[data-export-filter-sort]')!
    sort.value = 'name'
    sort.dispatchEvent(new Event('change', { bubbles: true }))
    const order = Array.from(clone.querySelectorAll('[data-export-case]')).map((card) =>
      card.getAttribute('data-export-case-name')
    )
    expect(order).toEqual(['用例 0', '用例 1', '用例 2'])
    const orderSelect = clone.querySelector<HTMLSelectElement>('[data-export-filter-sort-order]')!
    orderSelect.value = 'desc'
    orderSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(
      Array.from(clone.querySelectorAll('[data-export-case]')).map((card) =>
        card.getAttribute('data-export-case-name')
      )
    ).toEqual(['用例 2', '用例 1', '用例 0'])
    clone.remove()
  })
})

/** 两个分组的产物 DOM：第一组超过一页，第二组只有 3 张（负责人 08:44 的「打断与恢复」形态） */
function mountGroupedReportDom(): HTMLElement {
  const card = (group: string, index: number) => `
    <div data-export-case data-export-case-name="${group} 用例 ${index}" data-export-case-id="${group}-${index}"
         data-export-case-category="${group}" data-export-case-tags='[]'
         data-export-case-metrics='[]' data-export-case-metric-values='{}'>
      <div class="case-card">
        <button aria-label="展开详情">v</button>
        <div data-export-case-detail hidden>detail</div>
      </div>
    </div>`
  const group = (name: string, count: number) => `
    <div data-export-group="">
      <button type="button" data-export-group-toggle="" aria-expanded="true">
        <div class="header">
          <span data-export-group-count="">${count} 个用例</span>
          <span data-export-group-caret="">▾</span>
        </div>
      </button>
      <div class="space-y-2" data-export-group-body="">
        ${Array.from({ length: count }, (_, i) => card(name, i)).join('')}
      </div>
    </div>`

  const root = document.createElement('div')
  root.className = 'report-view-container'
  root.innerHTML = `
    <section id="report-specific-cases">
      <div data-slot="collapsible">
        <button data-slot="collapsible-trigger">具体用例</button>
        <div data-slot="collapsible-panel">
          <div data-export-filter-panel="">
            <input id="export-case-search" type="search" data-export-filter-keyword="" />
          </div>
          <div class="space-y-2" data-export-case-list>
            ${group('话轮接管', HTML_EXPORT_CASE_PAGE_SIZE + 2)}
            ${group('打断与恢复', 3)}
          </div>
        </div>
      </div>
    </section>
    <div data-export-cases-ready="true"></div>`
  document.body.appendChild(root)
  return root
}

describe('分组展开 / 收起与分组内分页（INT-2434 三轮）', () => {
  function mountAndRunGrouped(): HTMLElement {
    const root = mountGroupedReportDom()
    const { clone } = buildStaticClone(root)
    root.remove()
    document.body.appendChild(clone)
    new Function(REPORT_EXPORT_SCRIPT)()
    return clone
  }

  function groupById(clone: HTMLElement, name: string): HTMLElement {
    return Array.from(clone.querySelectorAll<HTMLElement>('[data-export-group]')).find(
      (wrapper) => wrapper.querySelector('[data-export-case]')?.getAttribute('data-export-case-category') === name
    )!
  }

  function visibleCardsIn(wrapper: HTMLElement): HTMLElement[] {
    return Array.from(wrapper.querySelectorAll<HTMLElement>('[data-export-case]')).filter(
      (card) => card.style.display !== 'none'
    )
  }

  it('分组头是保留的白名单按钮（aria-expanded + 展开箭头）', () => {
    const clone = mountAndRunGrouped()
    const toggle = clone.querySelector('[data-export-group-toggle]')
    expect(toggle).not.toBeNull()
    expect(toggle!.getAttribute('aria-expanded')).toBe('true')
    expect(clone.querySelector('[data-export-group-caret]')).not.toBeNull()
    expect(clone.querySelector('[data-export-group-body]')).not.toBeNull()
    clone.remove()
  })

  it('分组内分页：第二组不再只剩组头，第一页就有自己的卡片', () => {
    const clone = mountAndRunGrouped()
    const first = groupById(clone, '话轮接管')
    const second = groupById(clone, '打断与恢复')
    // 第一组 12 张：本页 10 张；第二组 3 张：本页 3 张（旧全局分页下这里是 0 张）
    expect(visibleCardsIn(first)).toHaveLength(HTML_EXPORT_CASE_PAGE_SIZE)
    expect(visibleCardsIn(second)).toHaveLength(3)
    expect(second.style.display).not.toBe('none')
    clone.remove()
  })

  it('组头可点开 / 收起：折叠后本组卡片不可见，再点恢复', () => {
    const clone = mountAndRunGrouped()
    const second = groupById(clone, '打断与恢复')
    const toggle = second.querySelector<HTMLButtonElement>('[data-export-group-toggle]')!
    const body = second.querySelector<HTMLElement>('[data-export-group-body]')!

    toggle.click()
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(body.style.display).toBe('none')
    expect(second.querySelector('[data-export-group-caret]')?.textContent).toBe('▸')
    // 折叠中的组仍保留组头（否则点不开）：组块本身不隐藏
    expect(second.style.display).not.toBe('none')

    toggle.click()
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(body.style.display).toBe('')
    expect(visibleCardsIn(second)).toHaveLength(3)
    clone.remove()
  })

  it('翻到第二页：各组按自己的第 2 页显示，不足一页的组隐藏组头', () => {
    const clone = mountAndRunGrouped()
    const first = groupById(clone, '话轮接管')
    const second = groupById(clone, '打断与恢复')
    ;(document.getElementById('export-case-next') as HTMLButtonElement).click()
    // 第一组 12 张 → 第 2 页剩 2 张；第二组只有 3 张 → 第 2 页无卡，组头隐藏
    expect(visibleCardsIn(first)).toHaveLength(2)
    expect(visibleCardsIn(second)).toHaveLength(0)
    expect(second.style.display).toBe('none')
    const info = document.getElementById('export-case-pageinfo')!
    expect(info.textContent).toContain('2 / 2')
    clone.remove()
  })
})

describe('目标 Tab：设备/API 展示名含空格（INT-2434 四轮 P2）', () => {
  /** 真实库里的 API 资源展示名自带空格（报告 421~426 的 `2-mock websocket 请求响应` 等） */
  function mountTargetDom(): HTMLElement {
    const root = document.createElement('div')
    root.className = 'report-view-container'
    root.innerHTML = `
      <section id="report-specific-cases">
        <div data-export-case data-export-case-name="用例" data-export-case-id="c1">
          <div role="tablist" aria-label="设备/API 目标切换">
            <button role="tab" data-export-tab="case-9-target:__all__" aria-selected="true">全部对比</button>
            <button role="tab" data-export-tab="case-9-target:1-mock http 单轮 dut" aria-selected="false">1-mock http 单轮 dut</button>
            <button role="tab" data-export-tab="case-9-target:2-mock websocket 请求响应" aria-selected="false">2-mock websocket 请求响应</button>
          </div>
          <div data-export-show='["case-9-target:1-mock http 单轮 dut"]'>A</div>
          <div data-export-show='["case-9-target:2-mock websocket 请求响应"]'>B</div>
        </div>
      </section>`
    document.body.appendChild(root)
    return root
  }

  it('点带空格的目标 Tab 后只显示该目标面板，其余隐藏', () => {
    const root = mountTargetDom()
    const { clone } = buildStaticClone(root)
    root.remove()
    document.body.appendChild(clone)
    new Function(REPORT_EXPORT_SCRIPT)()

    const panels = Array.from(clone.querySelectorAll<HTMLElement>('[data-export-show]'))
    expect(panels).toHaveLength(2)
    // 默认「全部对比」：两个目标面板都可见
    expect(panels.map((panel) => panel.style.display)).toEqual(['', ''])

    const buttons = Array.from(clone.querySelectorAll<HTMLButtonElement>('[data-export-tab]'))
    const second = buttons.find(
      (btn) => btn.getAttribute('data-export-tab') === 'case-9-target:2-mock websocket 请求响应'
    )!
    second.click()

    expect(second.getAttribute('aria-selected')).toBe('true')
    expect(panels[1].style.display).toBe('')
    expect(panels[0].style.display).toBe('none')

    // 切回「全部对比」：两个面板都恢复
    buttons[0].click()
    expect(panels.map((panel) => panel.style.display)).toEqual(['', ''])
    clone.remove()
  })
})

describe('exportShowMarker（导出态面板标记，INT-2434 四轮）', () => {
  it('输出 JSON 数组，展示名里的空格 / 冒号原样保留；无组前缀不落属性', () => {
    expect(exportShowMarker('case-x-target', '2-mock websocket 请求响应')).toBe(
      '["case-x-target:2-mock websocket 请求响应"]'
    )
    expect(exportShowMarker('case-x-dim', 1)).toBe('["case-x-dim:1"]')
    expect(exportShowMarker(undefined, 'pura90豆包-1.0.0')).toBeUndefined()
  })
})
