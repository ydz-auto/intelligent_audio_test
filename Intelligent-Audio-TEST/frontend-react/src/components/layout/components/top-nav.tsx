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
import { Link } from '@tanstack/react-router'
import { Menu } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

import type { TopNavLink } from '../types'

type TopNavProps = React.HTMLAttributes<HTMLElement> & {
  links: TopNavLink[]
}

/** Displays horizontal links on wide screens and a compact menu below xl. */
export function TopNav({ className, links, ...props }: TopNavProps) {
  if (links.length === 0) return null

  return (
    <>
      <div className='xl:hidden'>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger
            aria-label='切换导航菜单'
            render={<Button size='icon' variant='ghost' className='size-8' />}
          >
            <Menu aria-hidden='true' />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side='bottom'
            align='end'
            className='w-56 max-w-[calc(100vw-1rem)]'
          >
            <DropdownMenuGroup>
              {links.map((link) => (
                <DropdownMenuItem
                  key={`${link.title}:${link.href}`}
                  disabled={link.disabled}
                  className='min-h-10'
                  render={
                    link.external ? (
                      <a
                        href={link.href}
                        target='_blank'
                        rel='noopener noreferrer'
                      />
                    ) : (
                      <Link to={link.href} disabled={link.disabled} />
                    )
                  }
                >
                  <span className='min-w-0 truncate' title={link.title}>
                    {link.title}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <nav
        className={cn('hidden min-w-0 items-center gap-0.5 xl:flex', className)}
        {...props}
      >
        {links.map((link) =>
          link.external ? (
            <a
              key={`${link.title}:${link.href}`}
              href={link.href}
              title={link.title}
              target='_blank'
              rel='noopener noreferrer'
              aria-disabled={link.disabled}
              tabIndex={link.disabled ? -1 : undefined}
              onClick={
                link.disabled ? (event) => event.preventDefault() : undefined
              }
              className={cn(
                'text-muted-foreground hover:bg-accent hover:text-foreground min-w-0 truncate rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors',
                link.isActive && 'bg-accent text-foreground',
                link.disabled && 'pointer-events-none opacity-50'
              )}
            >
              {link.title}
            </a>
          ) : (
            <Link
              key={`${link.title}:${link.href}`}
              to={link.href}
              title={link.title}
              disabled={link.disabled}
              activeOptions={{ exact: link.href === '/' }}
              activeProps={{ className: 'bg-accent text-foreground' }}
              className={cn(
                'text-muted-foreground hover:bg-accent hover:text-foreground min-w-0 truncate rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors',
                link.isActive && 'bg-accent text-foreground',
                link.disabled && 'pointer-events-none opacity-50'
              )}
            >
              {link.title}
            </Link>
          )
        )}
      </nav>
    </>
  )
}
