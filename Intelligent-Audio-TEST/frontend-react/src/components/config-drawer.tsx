/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
import { Radio as RadioPrimitive } from '@base-ui/react/radio'
import { RadioGroup as Radio } from '@base-ui/react/radio-group'
import { CircleCheck, Palette, RotateCcw } from 'lucide-react'
import type { SVGProps } from 'react'

import { IconThemeDark } from '@/assets/custom/icon-theme-dark'
import { IconThemeLight } from '@/assets/custom/icon-theme-light'
import { IconThemeSystem } from '@/assets/custom/icon-theme-system'
import {
  sideDrawerContentClassName,
  sideDrawerFooterClassName,
  sideDrawerFormClassName,
  sideDrawerHeaderClassName,
} from '@/components/drawer-layout'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useThemeCustomization } from '@/context/theme-customization-provider'
import { useTheme } from '@/context/theme-provider'
import {
  type ContentLayout,
  THEME_PRESETS,
  type ThemeFont,
  type ThemePreset,
  type ThemeRadius,
  type ThemeScale,
} from '@/lib/theme-customization'
import { cn } from '@/lib/utils'

/**
 * 主题设置抽屉（照 newAPI config-drawer 裁剪为六节，文案全中文）：
 * 深浅色 / 颜色预设（10 预设全量）/ 字体 / 圆角 / 密度 / 内容宽度。
 * 去 newAPI 的侧栏样式/布局/站点方向三节（超出本平台规范范围）。
 */

const Item = RadioPrimitive.Root

export function ConfigDrawer() {
  const { resetTheme } = useTheme()
  const { resetCustomization } = useThemeCustomization()

  const handleReset = () => {
    resetTheme()
    resetCustomization()
  }

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button
            size='icon'
            variant='ghost'
            aria-label='打开主题设置'
            aria-describedby='config-drawer-description'
            className='max-md:hidden'
          />
        }
      >
        <Palette className='size-[1.2rem]' aria-hidden='true' />
      </SheetTrigger>
      <SheetContent className={sideDrawerContentClassName('sm:max-w-md')}>
        <SheetHeader className={sideDrawerHeaderClassName()}>
          <SheetTitle>外观设置</SheetTitle>
          <SheetDescription id='config-drawer-description'>
            调整外观与布局，按你的偏好展示。
          </SheetDescription>
        </SheetHeader>
        <div className={sideDrawerFormClassName()}>
          <ThemeConfig />
          <PresetConfig />
          <FontConfig />
          <RadiusConfig />
          <ScaleConfig />
          <ContentLayoutConfig />
        </div>
        <SheetFooter className={sideDrawerFooterClassName('grid-cols-1')}>
          <Button
            variant='destructive'
            onClick={handleReset}
            aria-label='重置全部设置为默认值'
          >
            重置
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function SectionTitle(props: {
  title: string
  showReset?: boolean
  onReset?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'text-muted-foreground mb-2 flex items-center gap-2 text-sm font-semibold',
        props.className
      )}
    >
      {props.title}
      {props.showReset && props.onReset && (
        <Button
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

function RadioGroupItem(props: {
  item: {
    value: string
    label: string
    icon: (props: SVGProps<SVGSVGElement>) => React.ReactElement
  }
  isTheme?: boolean
}) {
  const isTheme = props.isTheme ?? false
  return (
    <Item
      value={props.item.value}
      className={cn('group outline-none', 'transition duration-200 ease-in')}
      aria-label={`选择${props.item.label}`}
      aria-describedby={`${props.item.value}-description`}
    >
      <div
        className={cn(
          'ring-border relative rounded-md ring-[1px]',
          'group-data-checked:ring-primary group-data-checked:shadow-2xl',
          'group-focus-visible:ring-2'
        )}
        role='img'
        aria-hidden='false'
        aria-label={`${props.item.label} 预览`}
      >
        <CircleCheck
          className={cn(
            'fill-primary size-6 stroke-white',
            'group-data-unchecked:hidden',
            'absolute top-0 right-0 translate-x-1/2 -translate-y-1/2'
          )}
          aria-hidden='true'
        />
        <props.item.icon
          className={cn(
            !isTheme &&
              'stroke-primary fill-primary group-data-unchecked:stroke-muted-foreground group-data-unchecked:fill-muted-foreground'
          )}
          aria-hidden='true'
        />
      </div>
      <div
        className='mt-1 text-xs'
        id={`${props.item.value}-description`}
        aria-live='polite'
      >
        {props.item.label}
      </div>
    </Item>
  )
}

function ThemeConfig() {
  const { defaultTheme, theme, setTheme } = useTheme()
  return (
    <div>
      <SectionTitle
        title='深浅色'
        showReset={theme !== defaultTheme}
        onReset={() => setTheme(defaultTheme)}
      />
      <Radio
        value={theme}
        onValueChange={setTheme}
        className='grid w-full max-w-md grid-cols-3 gap-4'
        aria-label='选择深浅色偏好'
        aria-describedby='theme-description'
      >
        {[
          { value: 'system', label: '跟随系统', icon: IconThemeSystem },
          { value: 'light', label: '浅色', icon: IconThemeLight },
          { value: 'dark', label: '深色', icon: IconThemeDark },
        ].map((item) => (
          <RadioGroupItem key={item.value} item={item} isTheme />
        ))}
      </Radio>
      <div id='theme-description' className='sr-only'>
        选择跟随系统、浅色或深色模式
      </div>
    </div>
  )
}

function PresetConfig() {
  const { defaults, customization, setPreset } = useThemeCustomization()
  return (
    <div>
      <SectionTitle
        title='颜色预设'
        showReset={customization.preset !== defaults.preset}
        onReset={() => setPreset(defaults.preset)}
      />
      <Radio
        value={customization.preset}
        onValueChange={(v) => setPreset(v as ThemePreset)}
        className='grid w-full grid-cols-4 gap-3'
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
                'ring-border relative h-12 rounded-md ring-[1px] transition',
                'group-data-checked:ring-primary group-data-checked:shadow-md',
                'group-focus-visible:ring-2',
                'group-hover:ring-primary/60'
              )}
            >
              <div
                aria-hidden='true'
                className='absolute inset-0 rounded-md'
                style={{
                  background:
                    preset.value === 'default'
                      ? 'linear-gradient(135deg, oklch(0.68 0.2 25) 0%, oklch(0.8 0.17 85) 25%, oklch(0.72 0.18 155) 50%, oklch(0.66 0.19 245) 75%, oklch(0.68 0.2 315) 100%)'
                      : `linear-gradient(135deg, ${preset.swatches[0]} 0%, ${preset.swatches[1] ?? preset.swatches[0]} 100%)`,
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
            <div className='mt-1.5 truncate text-center text-xs'>
              {preset.name}
            </div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}

/**
 * 字体选项：每项以对应字体实时渲染「Aa」预览。
 * 「默认」不指定 fontFamily，继承当前生效的正文字体——
 * 让用户直接看到「默认」在当前预设下的实际效果。
 */
const FONT_OPTIONS: {
  value: ThemeFont
  label: string
  preview?: string
}[] = [
  { value: 'default', label: '默认', preview: undefined },
  { value: 'sans', label: '无衬线', preview: 'var(--font-sans)' },
  { value: 'serif', label: '衬线', preview: 'var(--font-serif)' },
]

function FontConfig() {
  const { defaults, customization, setFont } = useThemeCustomization()
  return (
    <div>
      <SectionTitle
        title='字体'
        showReset={customization.font !== defaults.font}
        onReset={() => setFont(defaults.font)}
      />
      <Radio
        value={customization.font}
        onValueChange={(v) => setFont(v as ThemeFont)}
        className='grid w-full grid-cols-3 gap-4'
        aria-label='选择正文字体'
      >
        {FONT_OPTIONS.map((option) => (
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
              <span
                aria-hidden='true'
                className='text-foreground absolute inset-0 flex items-center justify-center text-lg leading-none font-medium'
                style={
                  option.preview
                    ? { fontFamily: option.preview }
                    : // 「默认」瓦片跟随当前主题字体，预览即实际解析结果
                      { font: 'inherit', fontSize: '1.125rem' }
                }
              >
                Aa
              </span>
            </div>
            <div className='mt-1.5 text-center text-xs'>{option.label}</div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}

const RADIUS_OPTIONS: {
  value: ThemeRadius
  label: string
  // 视觉预览左上角使用的 CSS border-radius 值
  preview: string
}[] = [
  { value: 'default', label: '默认', preview: '1rem' },
  { value: 'none', label: '0', preview: '0' },
  { value: 'sm', label: '0.3', preview: '0.3rem' },
  { value: 'md', label: '0.5', preview: '0.5rem' },
  { value: 'lg', label: '0.75', preview: '0.75rem' },
  { value: 'xl', label: '1.0', preview: '1rem' },
]

function RadiusConfig() {
  const { defaults, customization, setRadius } = useThemeCustomization()
  return (
    <div>
      <SectionTitle
        title='圆角'
        showReset={customization.radius !== defaults.radius}
        onReset={() => setRadius(defaults.radius)}
      />
      <Radio
        value={customization.radius}
        onValueChange={(v) => setRadius(v as ThemeRadius)}
        className='grid w-full grid-cols-6 gap-2'
        aria-label='选择圆角'
      >
        {RADIUS_OPTIONS.map((option) => (
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
              <span
                aria-hidden='true'
                className='border-foreground/70 absolute top-2.5 left-2.5 size-3.5 border-t-[1.5px] border-l-[1.5px]'
                style={{ borderTopLeftRadius: option.preview }}
              />
            </div>
            <div className='mt-1.5 text-center text-xs'>{option.label}</div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}

/** 密度预览行：行高代表相对行距密度（紧凑=行密，舒适=行疏） */
function ScalePreview(props: { rows: number; rowGap: string }) {
  return (
    <div
      aria-hidden='true'
      className='absolute inset-2.5 flex flex-col justify-center'
      style={{ gap: props.rowGap }}
    >
      {Array.from({ length: props.rows }, (_, index) => 85 - index * 10).map(
        (width) => (
          <span
            key={width}
            className='bg-foreground/60 block h-[2px] rounded-full'
            style={{ width: `${width}%` }}
          />
        )
      )}
    </div>
  )
}

function ScaleConfig() {
  const { defaults, customization, setScale } = useThemeCustomization()
  const scaleOptions: {
    value: ThemeScale
    label: string
    rows: number
    rowGap: string
  }[] = [
    { value: 'sm', label: '紧凑', rows: 4, rowGap: '3px' },
    { value: 'default', label: '默认', rows: 3, rowGap: '6px' },
    { value: 'lg', label: '舒适', rows: 2, rowGap: '10px' },
    { value: 'xl', label: '超大', rows: 1, rowGap: '14px' },
  ]
  return (
    <div>
      <SectionTitle
        title='密度'
        showReset={customization.scale !== defaults.scale}
        onReset={() => setScale(defaults.scale)}
      />
      <Radio
        value={customization.scale}
        onValueChange={(v) => setScale(v as ThemeScale)}
        className='grid w-full grid-cols-4 gap-3'
        aria-label='选择界面密度'
      >
        {scaleOptions.map((option) => (
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
              <ScalePreview rows={option.rows} rowGap={option.rowGap} />
            </div>
            <div className='mt-1.5 truncate text-center text-xs'>
              {option.label}
            </div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}

function ContentLayoutConfig() {
  const { defaults, customization, setContentLayout } = useThemeCustomization()
  return (
    <div className='max-md:hidden'>
      <SectionTitle
        title='内容宽度'
        showReset={customization.contentLayout !== defaults.contentLayout}
        onReset={() => setContentLayout(defaults.contentLayout)}
      />
      <Radio
        value={customization.contentLayout}
        onValueChange={(v) => setContentLayout(v as ContentLayout)}
        className='grid w-full grid-cols-2 gap-4'
        aria-label='选择内容宽度'
      >
        {[
          { value: 'full', label: '全宽' },
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
              <ContentLayoutPreview centered={option.value === 'centered'} />
            </div>
            <div className='mt-1.5 truncate text-center text-xs'>
              {option.label}
            </div>
          </Item>
        ))}
      </Radio>
    </div>
  )
}

/** 内容宽度选项的迷你「页面」预览：全宽铺满、居中收窄为窄列 */
function ContentLayoutPreview(props: { centered: boolean }) {
  return (
    <div aria-hidden='true' className='absolute inset-2 flex flex-col gap-1.5'>
      <span className='bg-foreground/40 block h-1.5 w-full rounded-sm' />
      <div
        className={cn(
          'flex flex-1 flex-col gap-1',
          props.centered ? 'mx-auto w-1/2' : 'w-full'
        )}
      >
        <span className='bg-foreground/60 block h-[2px] w-full rounded-full' />
        <span className='bg-foreground/60 block h-[2px] w-3/4 rounded-full' />
      </div>
    </div>
  )
}
