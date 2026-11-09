/**
 * HTML 快照导出静态化单测（INT-2418）：只覆盖克隆清理 / 用例分页标记 / 文档组装这些纯 DOM 逻辑，
 * 打包与网络抓取留给 build + 15173 实测（jsdom 无真实样式表与 canvas 位图）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildReportHtmlDocument,
  buildStaticClone,
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
    expect(clone.querySelector('aside')).toBeNull()
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
