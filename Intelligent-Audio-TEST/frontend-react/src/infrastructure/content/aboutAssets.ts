import aboutMarkdown from '@/features/about/content/about.md?raw'

/**
 * 关于页默认正文资产（infrastructure 层，构建期 ?raw 静态导入）。
 * TODO(API 接线): /api/about 服务端可编辑端点立项后（06_关于.md §4.2），
 * 该值降级为「服务端内容为空时的回退默认」；未落前恒为正文来源。
 */
export const ABOUT_DOCUMENT = aboutMarkdown
