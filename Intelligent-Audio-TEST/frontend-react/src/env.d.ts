/// <reference types="@rsbuild/core/types" />

// Rsbuild 环境类型 + CSS 模块声明（styles/index.css 以 side-effect import 引入）
declare module '*.css'

// 构建期 ?raw 文本资产（content/about.md 中文正文，红线④ mock 常量形态）
declare module '*?raw' {
  const content: string
  export default content
}
