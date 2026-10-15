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
import { createContext, useContext, useEffect, useState } from 'react'

import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * 全局搜索 Provider（照 newAPI ⌘K 快捷键 + open 状态裁剪）。
 * 红线④：搜索面板为 Dialog 占位稿；TODO: Command（cmdk）检索件 + 数据源随后续卡接入。
 */

type SearchContextType = {
  open: boolean
  setOpen: React.Dispatch<React.SetStateAction<boolean>>
}

const SearchContext = createContext<SearchContextType | null>(null)

type SearchProviderProps = {
  children: React.ReactNode
}

export function SearchProvider({ children }: SearchProviderProps) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  return (
    <SearchContext.Provider value={{ open, setOpen }}>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className='overflow-hidden p-0'>
          <DialogHeader className='sr-only'>
            <DialogTitle>搜索</DialogTitle>
            <DialogDescription>全局搜索入口（占位稿）</DialogDescription>
          </DialogHeader>
          <div className='flex items-center gap-2 border-b px-3'>
            <Input
              autoFocus
              placeholder='搜索页面、任务、用例…'
              className='h-12 border-0 shadow-none focus-visible:ring-0'
            />
          </div>
          <p className='text-muted-foreground px-4 py-8 text-center text-sm'>
            全局搜索随后续卡片接入
          </p>
        </DialogContent>
      </Dialog>
    </SearchContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useSearch = () => {
  const searchContext = useContext(SearchContext)

  if (!searchContext) {
    throw new Error('useSearch has to be used within SearchProvider')
  }

  return searchContext
}
