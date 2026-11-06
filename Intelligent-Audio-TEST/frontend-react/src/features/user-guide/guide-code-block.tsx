import { Fragment, useEffect, useState, type CSSProperties } from 'react'
import type { HighlighterCore, ThemedTokenWithVariants } from 'shiki/core'

import { CodeBlockFrame } from '@/components/ai-elements/code-block'
import { CopyButton } from '@/components/copy-button'

/**
 * 手册代码块（07_文档.md §7 照 newAPI guide-code-block.tsx）。
 * shiki core 懒加载单例，仅装手册用到的语言（bash/json/powershell/python/toml）
 * + github-light/github-dark 双主题；未支持语言不高亮但照常展示与复制；
 * chunk 加载失败静默回退原文。
 */
const guideLanguages = new Set(['bash', 'json', 'powershell', 'python', 'toml'])
let highlighterPromise: Promise<HighlighterCore> | undefined

type HighlightedCode = {
  code: string
  language: string
  lines: Array<{
    offset: number
    breakBefore: string
    tokens: ThemedTokenWithVariants[]
  }>
}

export function GuideCodeBlock(props: { code: string; language: string }) {
  const [highlighted, setHighlighted] = useState<HighlightedCode | null>(null)

  useEffect(() => {
    if (!guideLanguages.has(props.language)) return
    let cancelled = false
    // Share the grammar engine across examples and load only the manual's languages.
    highlighterPromise ??= Promise.all([
      import('shiki/core'),
      import('shiki/engine/javascript'),
    ]).then(([core, engine]) =>
      core.createHighlighterCore({
        engine: engine.createJavaScriptRegexEngine(),
        langs: [
          () => import('shiki/langs/bash.mjs'),
          () => import('shiki/langs/json.mjs'),
          () => import('shiki/langs/powershell.mjs'),
          () => import('shiki/langs/python.mjs'),
          () => import('shiki/langs/toml.mjs'),
        ],
        themes: [
          () => import('shiki/themes/github-light.mjs'),
          () => import('shiki/themes/github-dark.mjs'),
        ],
      })
    )
    void highlighterPromise
      .then((highlighter) => {
        if (cancelled) return
        const tokens = highlighter.codeToTokensWithThemes(props.code, {
          lang: props.language,
          themes: { light: 'github-light', dark: 'github-dark' },
        })
        const lineBreaks = props.code.match(/\r\n|\r|\n/g) ?? []
        let offset = 0
        const lines = tokens.map((line, index) => {
          const lineOffset = offset
          offset += line.reduce(
            (length, token) => length + token.content.length,
            0
          )
          offset += lineBreaks[index]?.length ?? 0
          return {
            offset: lineOffset,
            breakBefore: index > 0 ? lineBreaks[index - 1] : '',
            tokens: line,
          }
        })
        setHighlighted({ code: props.code, language: props.language, lines })
      })
      .catch(() => {
        // The original code stays readable and copyable if a chunk fails to load.
        highlighterPromise = undefined
      })
    return () => {
      cancelled = true
    }
  }, [props.code, props.language])

  const lines =
    highlighted?.code === props.code && highlighted.language === props.language
      ? highlighted.lines
      : undefined

  return (
    <CodeBlockFrame
      className='guide-code-block my-6 rounded-xl shadow-none'
      showToolbar
      title={props.language}
      endActions={
        <CopyButton
          value={props.code}
          aria-label='复制代码'
          size='sm'
          className='h-8'
          tooltip='复制代码'
          successTooltip='已复制！'
        >
          复制代码
        </CopyButton>
      }
    >
      <pre
        tabIndex={0}
        aria-label={props.language}
        className='focus-visible:outline-ring my-0! overflow-x-auto rounded-none! border-0! bg-transparent! p-5! [overflow-wrap:normal] whitespace-pre focus-visible:outline-2 focus-visible:-outline-offset-2'
      >
        <code className='shiki'>
          {lines
            ? lines.map((line) => (
                <Fragment key={line.offset}>
                  {line.breakBefore}
                  {line.tokens.map((token) => (
                    <span
                      key={token.offset}
                      style={
                        {
                          '--shiki-light': token.variants.light.color,
                          '--shiki-dark': token.variants.dark.color,
                        } as CSSProperties
                      }
                    >
                      {token.content}
                    </span>
                  ))}
                </Fragment>
              ))
            : props.code}
        </code>
      </pre>
    </CodeBlockFrame>
  )
}
