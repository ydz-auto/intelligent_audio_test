/**
 * 密钥输入（interfaces 层）：type=password，已配置时以掩码作 placeholder；
 * 留空 = 不修改（明文永不回显）。
 */
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type SecretInputProps = {
  id: string
  label: string
  mask: string
  value: string
  onChange: (value: string) => void
  hint?: string
}

export function SecretInput(props: SecretInputProps) {
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor={props.id}>{props.label}</Label>
      <Input
        id={props.id}
        type='password'
        autoComplete='new-password'
        placeholder={
          props.mask ? `已配置 ${props.mask}，留空不修改` : '未配置，输入后保存'
        }
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
      />
      {props.hint ? (
        <p className='text-muted-foreground text-xs'>{props.hint}</p>
      ) : null}
    </div>
  )
}
