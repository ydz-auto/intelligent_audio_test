import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Tailwind 4 + 语义 token + 主题预设（styles/index.css 逐文件照搬 newAPI）
import '@/styles/index.css'

import { Providers } from '@/app/providers'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers />
  </StrictMode>
)
