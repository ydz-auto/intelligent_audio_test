import { Check, Copy } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * 复制按钮（对位 newAPI components/copy-button.tsx 精简版：
 * icon 态 Copy→Check 2s 回落；本卡消费于终端演示卡）。
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
  className?: string
  iconClassName?: string
  variant?: 'ghost' | 'outline' | 'default' | 'secondary' | 'destructive'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  'aria-label'?: string
}

export function CopyButton({
  value,
  className,
  iconClassName,
  variant = 'ghost',
  size = 'icon',
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

  return (
    <Button
      variant={variant}
      size={size}
      className={cn('shrink-0', className)}
      onClick={() => void copyToClipboard(value)}
      aria-label={isCopied ? '已复制' : (ariaLabel ?? '复制到剪贴板')}
    >
      {isCopied ? (
        <Check className={cn('text-success', iconClassName)} />
      ) : (
        <Copy className={cn(iconClassName)} />
      )}
    </Button>
  )
}
