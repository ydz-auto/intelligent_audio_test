/**
 * §6.4 作用域过滤 chips（INT-591 降维核心之一；newAPI ui/toggle-group 母版）。
 * ToggleGroup 单选计数：「全部 (n)」「设备 (n)」「API (n)」「用例 (n)」，切换即过滤统一参数表。
 * chip 为「全部」或「用例」时下方显示「功能特性快捷开关」（勾选自动批量添加/删除对应用例参数）。
 */
import { Checkbox } from '@/components/ui/checkbox'
import {
  ToggleGroup,
  ToggleGroupItem,
} from '@/components/ui/toggle-group'
import type { ParamScope } from '@/features/algorithm-config/types'

export type FeatureBundleItem = {
  key: string
  label: string
  params: string[]
  active: boolean
}

export type ParamScopeChipsProps = {
  scope: ParamScope
  onScopeChange: (scope: ParamScope) => void
  counts: { device: number; api: number; case: number }
  /** 功能特性快捷开关（scope=全部/用例时显示；其余隐藏） */
  featureBundles?: FeatureBundleItem[]
  onToggleBundle?: (key: string) => void
}

export function ParamScopeChips(props: ParamScopeChipsProps) {
  const total = props.counts.device + props.counts.api + props.counts.case
  const showBundles =
    (props.scope === 'all' || props.scope === 'case') &&
    (props.featureBundles?.length ?? 0) > 0

  return (
    <div className='space-y-2'>
      <ToggleGroup
        variant='outline'
        size='sm'
        spacing={0}
        value={[props.scope]}
        aria-label='参数作用域筛选'
        onValueChange={(values) => {
          const next = values[0]
          if (
            next === 'all' ||
            next === 'device' ||
            next === 'api' ||
            next === 'case'
          ) {
            props.onScopeChange(next)
          }
        }}
      >
        <ToggleGroupItem value='all'>全部 ({total})</ToggleGroupItem>
        <ToggleGroupItem value='device'>设备 ({props.counts.device})</ToggleGroupItem>
        <ToggleGroupItem value='api'>API ({props.counts.api})</ToggleGroupItem>
        <ToggleGroupItem value='case'>用例 ({props.counts.case})</ToggleGroupItem>
      </ToggleGroup>

      {showBundles && (
        <div className='flex flex-wrap gap-1.5 pt-1'>
          {props.featureBundles?.map((bundle) => (
            <label
              key={bundle.key}
              className='hover:bg-accent inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-background px-3 text-xs transition-colors has-data-[slot=checkbox]:bg-primary/10 has-[[data-checked=true]]:border-primary/40'
            >
              <Checkbox
                checked={bundle.active}
                onCheckedChange={() => props.onToggleBundle?.(bundle.key)}
                aria-label={`功能特性 ${bundle.label}`}
              />
              {bundle.label} {bundle.params.length} 个参数
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
