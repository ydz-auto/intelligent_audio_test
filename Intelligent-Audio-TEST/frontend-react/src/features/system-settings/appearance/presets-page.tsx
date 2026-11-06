/**
 * 主题预设分区（interfaces 层，INT-347 §4.6 母版 A 变体：卡片单选组）：
 * THEME_PRESETS 十预设全量色卡（swatch 双色渐变，照 config-drawer 实测），
 * 选中态 primary 描边 + CircleCheck 角标；下方预览小字「主色 · 次色」；
 * 即时生效（与导航栏右上角主题切换入口共用 useThemeCustomization），无保存按钮。
 */
import { Radio as RadioPrimitive } from '@base-ui/react/radio'
import { RadioGroup as Radio } from '@base-ui/react/radio-group'
import { CircleCheck } from 'lucide-react'
import { toast } from 'sonner'

import { useThemeCustomization } from '@/context/theme-customization-provider'
import { THEME_PRESETS, type ThemePreset } from '@/lib/theme-customization'
import { cn } from '@/lib/utils'

const Item = RadioPrimitive.Root

export function ThemePresetsPage() {
  const { customization, setPreset } = useThemeCustomization()

  const handleChange = (value: string) => {
    const preset = value as ThemePreset
    setPreset(preset)
    toast.success('外观设置已保存')
  }

  return (
    <div className='flex flex-col gap-4'>
      <p className='text-muted-foreground text-sm'>选择站点的配色预设，即刻全局生效</p>
      <Radio
        value={customization.preset}
        onValueChange={handleChange}
        className='grid w-full grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5'
        aria-label='选择颜色预设'
      >
        {THEME_PRESETS.map((preset) => (
          <Item
            key={preset.value}
            value={preset.value}
            className='group flex flex-col items-stretch outline-none'
            aria-label={preset.name}
          >
            <div
              className={cn(
                'ring-border relative h-16 rounded-lg ring-[1px] transition',
                'group-data-checked:ring-primary group-data-checked:shadow-md',
                'group-focus-visible:ring-2',
                'group-hover:ring-primary/60'
              )}
            >
              <div
                aria-hidden='true'
                className='absolute inset-0 rounded-lg'
                style={{
                  background: `linear-gradient(135deg, ${preset.swatches[0]} 0%, ${preset.swatches[1] ?? preset.swatches[0]} 100%)`,
                }}
              />
              <CircleCheck
                className={cn(
                  'fill-primary absolute top-0 right-0 z-10 size-5 translate-x-1/2 -translate-y-1/2 stroke-white',
                  'group-data-unchecked:hidden'
                )}
                aria-hidden='true'
              />
            </div>
            <div className='mt-1.5 truncate text-center text-xs font-medium'>
              {preset.name}
            </div>
            <div className='text-muted-foreground truncate px-1 text-center font-mono text-[10px]'>
              主色 {preset.swatches[0].replace('oklch(', '')} · 次色 {preset.swatches[1]?.replace('oklch(', '') ?? '—'}
            </div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}
