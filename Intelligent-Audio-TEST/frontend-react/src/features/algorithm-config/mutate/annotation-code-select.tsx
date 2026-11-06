/**
 * 标注代码下拉（INT-1030 走查实施：标注代码不再以原始代码文本输入）。
 * 语义：标注代码=算法类型代码——选「默认同算法类型」（空值，后端用当前算法类型），
 * 选其它算法类型表示复用该算法的标注（互用标注，算法 A 想要 B 的标注就选 B）。
 * 选项 = 算法列表 → 「算法名称（类型代码）」，人可读、不再让人填看不懂的代码。
 * 与 params-table（用例参数行）和 reference-params-section（参考参数行）共用。
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** 标注代码选项（算法类型 → 名称映射；类型代码即标注代码） */
export type AlgorithmOption = { type: string; name: string }

export function AnnotationCodeSelect({
  value,
  onValueChange,
  algorithmOptions,
  ariaLabel = '标注代码',
  triggerClassName = 'w-48',
}: {
  value: string
  onValueChange: (value: string) => void
  /** 算法列表（选项=算法类型/标注代码 的映射） */
  algorithmOptions: AlgorithmOption[]
  ariaLabel?: string
  triggerClassName?: string
}) {
  const selected = algorithmOptions.find((option) => option.type === value)
  return (
    <Select value={value} onValueChange={(next) => onValueChange(next ?? '')}>
      <SelectTrigger size='sm' className={triggerClassName} aria-label={ariaLabel}>
        <SelectValue>
          {value === ''
            ? '默认同算法类型'
            : selected
              ? `${selected.name}（${selected.type}）`
              : value}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value=''>默认同算法类型</SelectItem>
        {algorithmOptions.map((option) => (
          <SelectItem key={option.type} value={option.type}>
            {option.name}（{option.type}）
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
