/*
KaTeX 按需加载（INT-1274）：文档 / 关于页的 Markdown 渲染原先静态引入 katex
（katex.min.js 约 271 kB raw + katex.min.css 及 19 组字体），但站内手册与关于正文
都不含公式，每个文档页都要下载这份用不到的代码。改成：正文出现数学定界符时才
动态加载 katex 与它的样式表，没有公式的页面一个字节都不下载。
*/

type KatexModule = typeof import('katex')

/**
 * 与 markdown.tsx 里自定义 tokenizer 口径一致：块级 `$$` 行、行内 `$$…$$`、
 * 围栏 ```math / ```katex / ```latex、以及 `\\(…\\)` / `\\[…\\]` 写法。
 * 宁可多判（多下载一次 katex），不能漏判（公式不渲染）。
 */
const mathSyntaxPattern = /\$\$|```[ \t]*(?:math|katex|latex)\b|\\\(|\\\[/

let katexModule: KatexModule | null = null
let pending: Promise<KatexModule | null> | null = null

export function hasMathSyntax(content: string): boolean {
  return mathSyntaxPattern.test(content)
}

export function isKatexLoaded(): boolean {
  return katexModule !== null
}

/** 已加载则同步返回，未加载返回 null——渲染器据此退化为纯文本公式。 */
export function getKatex(): KatexModule | null {
  return katexModule
}

/** 加载失败只影响公式渲染，不得让文档页整体报错。 */
export function loadKatex(): Promise<KatexModule | null> {
  if (katexModule) {
    return Promise.resolve(katexModule)
  }

  pending ??= Promise.all([
    import('katex'),
    import('katex/dist/katex.min.css'),
  ])
    .then(([module]) => {
      // katex 的 ESM 入口同时挂 default 与命名导出，取哪份都带 renderToString。
      const resolved = ((module as unknown as { default?: KatexModule })
        .default ?? module) as KatexModule
      katexModule = resolved

      return resolved
    })
    .catch(() => {
      pending = null

      return null
    })

  return pending
}
