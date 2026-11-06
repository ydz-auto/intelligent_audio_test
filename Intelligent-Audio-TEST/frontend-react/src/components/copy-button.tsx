import { Check, Copy } from 'lucide-react'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/**
 * 复制按钮（对位 newAPI components/copy-button.tsx：
 * icon 态 Copy→Check 2s 回落；07_文档.md §6 代码块文案「复制代码」/已复制。
 * 传 tooltip/successTooltip 时包 Tooltip；children 非空时随图标渲染（如「复制代码」文本）。
 */

async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

interface CopyButtonProps {
  value: string
  children?: ReactNode
  className?: string
  iconClassName?: string
  variant?: 'ghost' | 'outline' | 'default' | 'secondary' | 'destructive'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  tooltip?: string
  successTooltip?: string
  'aria-label'?: string
}

export function CopyButton({
  value,
  children,
  className,
  iconClassName,
  variant = 'ghost',
  size = 'icon',
  tooltip,
  successTooltip,
  'aria-label': ariaLabel,
}: CopyButtonProps) {
  const [copiedText, setCopiedText] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timeoutRef.current), [])

  const copyToClipboard = useCallback(async (text: string) => {
    const success = await writeClipboard(text)
    if (!success) return
    setCopiedText(text)
    clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setCopiedText(null), 2000)
  }, [])

  const isCopied = copiedText === value
  const resolvedTooltip = tooltip ?? '复制到剪贴板'
  const resolvedSuccessTooltip = successTooltip ?? '已复制！'

  const button = (
    <Button
      variant={variant}
      size={size}
      className={cn('shrink-0', className)}
      onClick={() => void copyToClipboard(value)}
      aria-label={isCopied ? '已复制' : (ariaLabel ?? resolvedTooltip)}
    >
      {isCopied ? (
        <Check className={cn('text-success', iconClassName)} />
      ) : (
        <Copy className={cn(iconClassName)} />
      )}
      {children}
    </Button>
  )

  if (tooltip || successTooltip) {
    return (
      <Tooltip>
        <TooltipTrigger render={button} />
        <TooltipContent>
          <p>{isCopied ? resolvedSuccessTooltip : resolvedTooltip}</p>
        </TooltipContent>
      </Tooltip>
    )
  }

  return button
}
