/**
 * 导出态 DOM 标记契约（INT-2434）。
 *
 * 报告 HTML 快照是「克隆页面 DOM + 产物内脚本接管交互」，Tab 与面板靠属性配对：
 *   - `data-export-tab`  Tab 按钮，值 `<组>:<值>`；
 *   - `data-export-show` 面板要显示时命中的规格，**值是 JSON 字符串数组**。
 *
 * 为什么是 JSON 数组（INT-2434 四轮 P2）：旧契约用单个空格分隔多条规格，
 * 而设备/API 目标的「展示名」本身就带空格（真实数据如 `2-mock websocket 请求响应`），
 * 空格切分后第一段永远对不上 Tab 值 → 点目标 Tab 后面板全被隐藏。
 * JSON 里空格 / 冒号 / 引号都只是值的一部分，`JSON.parse` 出来原样比较即可。
 */
/** 生成面板的 `data-export-show`（未处于导出态 / 无组前缀时返回 undefined，不落属性）。 */
export function exportShowMarker(
  group: string | undefined,
  ...specs: Array<string | number>
): string | undefined {
  if (!group) return undefined
  return JSON.stringify(specs.map((spec) => `${group}:${spec}`))
}
