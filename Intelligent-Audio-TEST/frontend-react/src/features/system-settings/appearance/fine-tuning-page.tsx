/**
 * 外观微调分区（interfaces 层，INT-347 §4.6 母版 A 开关/单选行）：
 * 四轴——深浅色（浅色/深色/跟随系统）/ 字体（自动/无衬线/衬线「Aa」预览）/
 * 圆角（默认/无/0.3/0.5/0.75/1.0）/ 内容版式（通栏/居中）；
 * 每节标题右侧「重置」按钮（≠默认值时显示）；即时生效无保存按钮，
 * 与导航栏右上角主题切换入口共用 useThemeCustomization/useTheme。
 */
import { Radio as RadioPrimitive } from '@base-ui/react/radio'
import { RadioGroup as Radio } from '@base-ui/react/radio-group'
import { CircleCheck, RotateCcw } from 'lucide-react'
import type { SVGProps } from 'react'
import { toast } from 'sonner'

import { IconThemeDark } from '@/assets/custom/icon-theme-dark'
import { IconThemeLight } from '@/assets/custom/icon-theme-light'
import { IconThemeSystem } from '@/assets/custom/icon-theme-system'
import { Button } from '@/components/ui/button'
import { useThemeCustomization } from '@/context/theme-customization-provider'
import { useTheme } from '@/context/theme-provider'
import {
  type ContentLayout,
  type ThemeFont,
  type ThemeRadius,
} from '@/lib/theme-customization'
import { cn } from '@/lib/utils'

import { SettingsCard } from '../components/settings-card'

const Item = RadioPrimitive.Root

function SectionHeader(props: { title: string; showReset: boolean; onReset: () => void }) {
  return (
    <div className='text-muted-foreground mb-2 flex items-center gap-2 text-sm font-semibold'>
      {props.title}
      {props.showReset && (
        <Button
          type='button'
          size='icon'
          variant='secondary'
          className='size-4'
          onClick={props.onReset}
          aria-label='重置此项'
        >
          <RotateCcw className='size-3' aria-hidden='true' />
        </Button>
      )}
    </div>
  )
}

function RadioCard(props: {
  label: string
  icon?: (iconProps: SVGProps<SVGSVGElement>) => React.ReactElement
  preview?: string
  radiusPreview?: string
  isTheme?: boolean
}) {
  return (
    <div
      className={cn(
        'ring-border relative h-12 rounded-md ring-[1px] transition',
        'group-data-checked:ring-primary group-data-checked:shadow-md',
        'group-focus-visible:ring-2',
        'group-hover:ring-primary/60'
      )}
    >
      <CircleCheck
        className={cn(
          'fill-primary absolute top-0 right-0 z-10 size-5 translate-x-1/2 -translate-y-1/2 stroke-white',
          'group-data-unchecked:hidden'
        )}
        aria-hidden='true'
      />
      {props.icon && (
        <props.icon
          className={cn(
            'stroke-primary fill-primary group-data-unchecked:stroke-muted-foreground group-data-unchecked:fill-muted-foreground',
            props.isTheme &&
              'group-data-unchecked:fill-background group-data-unchecked:stroke-muted-foreground'
          )}
          aria-hidden='true'
        />
      )}
      {props.preview && (
        <span
          aria-hidden='true'
          className='text-foreground absolute inset-0 flex items-center justify-center text-lg leading-none font-medium'
          style={{ fontFamily: props.preview }}
        >
          Aa
        </span>
      )}
      {props.radiusPreview && (
        <span
          aria-hidden='true'
          className='border-foreground/70 absolute top-2.5 left-2.5 size-3.5 border-t-[1.5px] border-l-[1.5px]'
          style={{ borderTopLeftRadius: props.radiusPreview }}
        />
      )}
    </div>
  )
}

export function AppearanceFineTuningPage() {
  const { defaultTheme, theme, setTheme } = useTheme()
  const { defaults, customization, setFont, setRadius, setContentLayout } =
    useThemeCustomization()

  const handleTheme = (value: string) => {
    setTheme(value as typeof defaultTheme)
    toast.success('外观设置已保存')
  }

  const handleFont = (value: string) => {
    setFont(value as ThemeFont)
    toast.success('外观设置已保存')
  }

  const handleRadius = (value: string) => {
    setRadius(value as ThemeRadius)
    toast.success('外观设置已保存')
  }

  const handleContentLayout = (value: string) => {
    setContentLayout(value as ContentLayout)
    toast.success('外观设置已保存')
  }

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      <SettingsCard title='深浅色'>
        <SectionHeader
          title='模式'
          showReset={theme !== defaultTheme}
          onReset={() => setTheme(defaultTheme)}
        />
        <Radio
          value={theme}
          onValueChange={handleTheme}
          className='grid w-full grid-cols-3 gap-4'
          aria-label='选择深浅色偏好'
        >
          {[
            { value: 'system', label: '跟随系统', icon: IconThemeSystem },
            { value: 'light', label: '浅色', icon: IconThemeLight },
            { value: 'dark', label: '深色', icon: IconThemeDark },
          ].map((item) => (
            <Item
              key={item.value}
              value={item.value}
              className='group flex flex-col items-stretch outline-none'
              aria-label={item.label}
            >
              <RadioCard label={item.label} icon={item.icon} isTheme />
              <div className='mt-1 text-center text-xs'>{item.label}</div>
            </Item>
          ))}
        </Radio>
      </SettingsCard>

      <SettingsCard title='字体'>
        <SectionHeader
          title='正文字体'
          showReset={customization.font !== defaults.font}
          onReset={() => setFont(defaults.font)}
        />
        <Radio
          value={customization.font}
          onValueChange={handleFont}
          className='grid w-full grid-cols-3 gap-4'
          aria-label='选择正文字体'
        >
          {[
            { value: 'default', label: '自动', preview: undefined },
            { value: 'sans', label: '无衬线', preview: 'var(--font-sans)' },
            { value: 'serif', label: '衬线', preview: 'var(--font-serif)' },
          ].map((option) => (
            <Item
              key={option.value}
              value={option.value}
              className='group flex flex-col items-stretch outline-none'
              aria-label={option.label}
            >
              <RadioCard
                label={option.label}
                preview={
                  option.preview ??
                  (customization.font === 'default'
                    ? 'var(--font-sans)'
                    : undefined)
                }
              />
              <div className='mt-1 text-center text-xs'>{option.label}</div>
            </Item>
          ))}
        </Radio>
      </SettingsCard>

      <SettingsCard title='圆角'>
        <SectionHeader
          title='控件圆角'
          showReset={customization.radius !== defaults.radius}
          onReset={() => setRadius(defaults.radius)}
        />
        <Radio
          value={customization.radius}
          onValueChange={handleRadius}
          className='grid w-full grid-cols-6 gap-2'
          aria-label='选择圆角'
        >
          {[
            { value: 'default', label: '默认', preview: '1rem' },
            { value: 'none', label: '无', preview: '0' },
            { value: 'sm', label: '0.3', preview: '0.3rem' },
            { value: 'md', label: '0.5', preview: '0.5rem' },
            { value: 'lg', label: '0.75', preview: '0.75rem' },
            { value: 'xl', label: '1.0', preview: '1rem' },
          ].map((option) => (
            <Item
              key={option.value}
              value={option.value}
              className='group flex flex-col items-stretch outline-none'
              aria-label={option.label}
            >
              <RadioCard
                label={option.label}
                radiusPreview={option.preview}
              />
              <div className='mt-1 text-center text-xs'>{option.label}</div>
            </Item>
          ))}
        </Radio>
      </SettingsCard>

      <SettingsCard title='内容版式'>
        <SectionHeader
          title='内容宽度'
          showReset={customization.contentLayout !== defaults.contentLayout}
          onReset={() => setContentLayout(defaults.contentLayout)}
        />
        <Radio
          value={customization.contentLayout}
          onValueChange={handleContentLayout}
          className='grid w-full grid-cols-2 gap-4'
          aria-label='选择内容宽度'
        >
          {[
            { value: 'full', label: '通栏' },
            { value: 'centered', label: '居中' },
          ].map((option) => (
            <Item
              key={option.value}
              value={option.value}
              className='group flex flex-col items-stretch outline-none'
              aria-label={option.label}
            >
              <div
                className={cn(
                  'ring-border relative h-12 rounded-md ring-[1px] transition',
                  'group-data-checked:ring-primary group-data-checked:shadow-md',
                  'group-focus-visible:ring-2',
                  'group-hover:ring-primary/60'
                )}
              >
                <CircleCheck
                  className={cn(
                    'fill-primary absolute top-0 right-0 z-10 size-5 translate-x-1/2 -translate-y-1/2 stroke-white',
                    'group-data-unchecked:hidden'
                  )}
                  aria-hidden='true'
                />
                <div aria-hidden='true' className='absolute inset-2 flex flex-col gap-1.5'>
                  <span className='bg-foreground/40 block h-1.5 w-full rounded-sm' />
                  <div
                    className={cn(
                      'flex flex-1 flex-col gap-1',
                      option.value === 'centered' ? 'mx-auto w-1/2' : 'w-full'
                    )}
                  >
                    <span className='bg-foreground/60 block h-[2px] w-full rounded-full' />
                    <span className='bg-foreground/60 block h-[2px] w-3/4 rounded-full' />
                  </div>
                </div>
              </div>
              <div className='mt-1 text-center text-xs'>{option.label}</div>
            </Item>
          ))}
        </Radio>
      </SettingsCard>
    </div>
  )
}
