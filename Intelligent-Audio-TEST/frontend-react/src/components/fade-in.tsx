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
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface FadeInProps {
  children: ReactNode
  className?: string
  delay?: number
}

export function FadeIn(props: FadeInProps) {
  return (
    <div
      className={cn(
        'animate-in fade-in-0 motion-reduce:animate-none',
        props.className
      )}
      style={{
        animationDuration: '250ms',
        animationTimingFunction: 'cubic-bezier(0.33, 1, 0.68, 1)',
        animationDelay: `${props.delay ?? 0}s`,
      }}
    >
      {props.children}
    </div>
  )
}
