/**
 * 批量 HTML 导出组装单测（INT-2419）：只覆盖子目录去重 / zip 结构 / 清单页这些纯逻辑。
 * 「每份产物与单份导出一致」由共用 `captureReportHtmlSnapshot` 保证，DOM 层断言见 html-snapshot.test.ts。
 */
import JSZip from 'jszip'
import { describe, expect, it } from 'vitest'

import {
  BATCH_CSS_DIR,
  BATCH_CSS_FILE,
  BATCH_INDEX_FILE,
  BATCH_REPORT_FILE,
  batchExportFileName,
  buildBatchIndexHtml,
  buildBatchReportZip,
  MAX_BATCH_DIR_NAME_LENGTH,
  uniqueReportDirName,
  type BatchHtmlEntry,
} from '../batch-html-snapshot'

function entry(dir: string, reportName = dir): BatchHtmlEntry {
  return { dir, reportName, html: `<html>${dir}</html>`, css: `/* ${dir} */` }
}

describe('uniqueReportDirName', () => {
  it('同名报告追加全角序号，不覆盖已有目录', () => {
    const used = new Set<string>()
    expect(uniqueReportDirName('月度报告', used)).toBe('月度报告')
    expect(uniqueReportDirName('月度报告', used)).toBe('月度报告（2）')
    expect(uniqueReportDirName('月度报告', used)).toBe('月度报告（3）')
    expect(used.size).toBe(3)
  })

  it('剔除非法文件名字符，空名兜底 report', () => {
    expect(uniqueReportDirName('报告/2026:11*?', new Set())).toBe('报告202611')
    expect(uniqueReportDirName('   ', new Set())).toBe('report')
  })

  it('超长名截断后仍留出序号后缀的位置，且不撞名', () => {
    const used = new Set<string>()
    const long = '报告'.repeat(60)
    const first = uniqueReportDirName(long, used)
    const second = uniqueReportDirName(long, used)
    expect(first.length).toBeLessThanOrEqual(MAX_BATCH_DIR_NAME_LENGTH)
    expect(second.length).toBeLessThanOrEqual(MAX_BATCH_DIR_NAME_LENGTH)
    expect(second.endsWith('（2）')).toBe(true)
    expect(second).not.toBe(first)
  })
})

describe('buildBatchIndexHtml', () => {
  it('列报告清单与相对链接，file:// 可直接点进各份', () => {
    const html = buildBatchIndexHtml(
      [entry('报告A'), entry('报告B（2）', '报告B')],
      new Date('2026-11-09T08:00:00Z')
    )
    expect(html).toContain('共 2 份')
    expect(html).toContain('href="报告A/report.html"')
    expect(html).toContain('href="报告B（2）/report.html"')
    expect(html).toContain('>报告B</a>')
  })

  it('报告名做 HTML 转义', () => {
    const html = buildBatchIndexHtml([entry('a', '<报告&>')], new Date())
    expect(html).toContain('&lt;报告&amp;&gt;')
    expect(html).not.toContain('><报告&><')
  })
})

describe('buildBatchReportZip', () => {
  it('每份一个子目录（report.html + css/report.css），根目录 index.html', async () => {
    const { blob, fileName } = await buildBatchReportZip(
      [entry('报告A'), entry('报告B')],
      { exportedAt: new Date('2026-11-09T08:00:00Z') }
    )
    expect(fileName).toMatch(/^报告批量导出-\d{8}-\d{6}\.zip$/)

    const zip = await JSZip.loadAsync(new Uint8Array(await blob.arrayBuffer()))
    const names = Object.keys(zip.files)
    expect(names).toContain('报告A/' + BATCH_REPORT_FILE)
    expect(names).toContain('报告A/' + BATCH_CSS_DIR + '/' + BATCH_CSS_FILE)
    expect(names).toContain('报告B/' + BATCH_REPORT_FILE)
    expect(names).toContain(BATCH_INDEX_FILE)

    const reportHtml = await zip.file('报告A/' + BATCH_REPORT_FILE)!.async('string')
    expect(reportHtml).toContain('<html>报告A</html>')
    const reportCss = await zip.file('报告A/' + BATCH_CSS_DIR + '/' + BATCH_CSS_FILE)!.async('string')
    expect(reportCss).toContain('/* 报告A */')
    const index = await zip.file(BATCH_INDEX_FILE)!.async('string')
    expect(index).toContain('href="报告B/report.html"')
  })

  it('同名子目录由调用方去重后互不覆盖', async () => {
    const used = new Set<string>()
    const dirs = ['同名', '同名'].map((name) => uniqueReportDirName(name, used))
    const { blob } = await buildBatchReportZip(dirs.map((dir, i) => entry(dir, `同名${i}`)))
    const zip = await JSZip.loadAsync(new Uint8Array(await blob.arrayBuffer()))
    const htmlA = await zip.file(dirs[0] + '/' + BATCH_REPORT_FILE)!.async('string')
    const htmlB = await zip.file(dirs[1] + '/' + BATCH_REPORT_FILE)!.async('string')
    expect(htmlA).toContain(dirs[0])
    expect(htmlB).toContain(dirs[1])
    expect(htmlA).not.toBe(htmlB)
  })

  it('文件名可指定（批量导出名）', async () => {
    const { fileName } = await buildBatchReportZip([entry('A')], { batchName: '挑选合并/导出' })
    expect(fileName).toBe('挑选合并导出.zip')
  })
})

describe('batchExportFileName', () => {
  it('按时间戳生成，零填充', () => {
    expect(batchExportFileName(new Date(2026, 0, 2, 3, 4, 5))).toBe('报告批量导出-20260102-030405.zip')
  })
})
