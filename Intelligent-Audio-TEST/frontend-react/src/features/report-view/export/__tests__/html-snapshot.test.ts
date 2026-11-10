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
  sanitizeFileName,
} from '../html-snapshot'

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
            <div class="rounded-xl border p-3" data-export-hide>
              <input id="keyword" />
            </div>
            <div class="space-y-2" data-export-case-list>
              ${Array.from({ length: caseCount })
                .map(
                  (_, index) => `
                <div data-export-case data-export-case-name="用例 ${index}" data-export-case-id="case-${index}">
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

  it('用例分页：超过一页的卡片默认隐藏，并插入搜索/分页工具条', () => {
    const root = mountReportDom(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    const { clone, caseCount } = buildStaticClone(root)
    expect(caseCount).toBe(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    expect(clone.getAttribute('data-export-case-total')).toBe(String(caseCount))
    const cards = Array.from(clone.querySelectorAll<HTMLElement>('[data-export-case]'))
    expect(cards).toHaveLength(HTML_EXPORT_CASE_PAGE_SIZE + 3)
    expect(cards[0].style.display).toBe('')
    expect(cards[HTML_EXPORT_CASE_PAGE_SIZE].style.display).toBe('none')
    expect(clone.querySelector('[data-export-case-toolbar]')).not.toBeNull()
    expect(clone.querySelector('#export-case-search')).not.toBeNull()
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
            <div data-export-show="case-1-round:round:1">第一轮数据</div>
            <div data-export-show="case-1-round:round:2">第二轮数据</div>
            <button id="action-detail">详情</button>
          </div>
        </div>
      </section>`
    document.body.appendChild(root)
    const { clone } = buildStaticClone(root)
    const tabs = clone.querySelectorAll('[role="tab"]')
    expect(tabs).toHaveLength(2)
    expect(clone.querySelector('[data-export-show="case-1-round:round:2"]')).not.toBeNull()
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

  it('无 Collapsible 的分区（h3 + 内容）包出可折叠面板', () => {
    const root = document.createElement('div')
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
    root.remove()
  })
})
