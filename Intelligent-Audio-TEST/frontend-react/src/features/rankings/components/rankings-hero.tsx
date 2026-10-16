/**
 * 排行榜 Hero（对位 newAPI rankings-hero.tsx）：标题 + 说明 + 类别维度下划线页签。
 * 周期维度待后端立项（ReadModel 无时间维度），下划线页签位挂「类别维度」
 * （全部/asr/voice_llm/tts/translation，category 参数真实存在）。
 * 页签切换不重置其他筛选（URL search 合并写入，照 newAPI navigate 模式）。
 */
import { useNavigate } from '@tanstack/react-router'
import { useCallback } from 'react'

import { cn } from '@/lib/utils'

const CATEGORY_TABS: ReadonlyArray<{
  value: string
  label: string
  srSelected: string
}> = [
  { value: '', label: '全部', srSelected: '全部，当前已选中' },
  { value: 'asr', label: '语音识别', srSelected: '语音识别，当前已选中' },
  { value: 'voice_llm', label: '语音对话', srSelected: '语音对话，当前已选中' },
  { value: 'tts', label: '语音合成', srSelected: '语音合成，当前已选中' },
  { value: 'translation', label: '翻译', srSelected: '翻译，当前已选中' },
]

export function RankingsHero(props: { category: string }) {
  const navigate = useNavigate()
  const handleSelect = useCallback(
    (category: string) => {
      void navigate({
        to: '/rankings',
        search: (prev) => ({ ...prev, category }),
      })
    },
    [navigate]
  )

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-col gap-2'>
        <h1 className='text-[clamp(1.75rem,4vw,2.5rem)] leading-[1.15] font-bold tracking-tight'>
          排行榜
        </h1>
        <p className='text-muted-foreground/80 max-w-2xl text-sm leading-6'>
          多个厂商模型/APP/API 在同一标准化环境、同一测试集与指标下同时实测，按指标与场景生成名次，横向看清业界水平。
        </p>
      </div>

      <div
        role='tablist'
        aria-label='指标类别'
        className='border-border/60 flex items-center gap-1 overflow-x-auto border-b'
      >
        {CATEGORY_TABS.map((tab) => {
          const active = props.category === tab.value
          return (
            <button
              key={tab.value}
              type='button'
              role='tab'
              aria-selected={active}
              onClick={() => handleSelect(tab.value)}
              className={cn(
                'relative -mb-px rounded-sm px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                active
                  ? 'text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <span className='sr-only'>{active ? tab.srSelected : tab.label}</span>
              <span aria-hidden='true'>{tab.label}</span>
              <span
                aria-hidden='true'
                className={cn(
                  'bg-foreground absolute inset-x-0 bottom-0 h-[2px] transition-opacity',
                  active ? 'opacity-100' : 'opacity-0'
                )}
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}
