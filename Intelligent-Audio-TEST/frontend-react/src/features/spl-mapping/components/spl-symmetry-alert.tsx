/**
 * 三口径对称提示（§4.4；内容区底部常驻 Alert，Info 图标）。
 * 现状 SPLMapping.vue:399 文案保留；Alert 用 default 变体 + Info 图标（newAPI alert 无 info 变体）。
 */
import { Info } from 'lucide-react'

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert'
import { SPL_SYMMETRY_ALERT_TEXT } from '@/features/spl-mapping/constants'

export function SplSymmetryAlert() {
  return (
    <Alert className='items-start gap-2'>
      <Info aria-hidden='true' className='size-4 shrink-0' />
      <AlertTitle className='text-sm font-medium'>三口径对称</AlertTitle>
      <AlertDescription>{SPL_SYMMETRY_ALERT_TEXT}</AlertDescription>
    </Alert>
  )
}
