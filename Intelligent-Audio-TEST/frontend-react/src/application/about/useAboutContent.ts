import { ABOUT_DOCUMENT } from '@/infrastructure/content/aboutAssets'
import { isHttpUrl, isLikelyHtml } from '@/lib/content-format'

/** 内容解析四分支：默认 md 资产 / URL iframe / HTML / 空态回退默认（06_关于.md §1.3/§4.2） */
export type AboutContentState =
  | { status: 'markdown'; content: string }
  | { status: 'url'; url: string }
  | { status: 'html'; html: string }

/**
 * 关于页内容解析（application 层）。
 * /api/about 服务端可编辑端点待后端立项，未落前恒走 md 分支（构建期 ?raw 资产）。
 */
export function useAboutContent(): AboutContentState {
  // TODO(API 接线): GET /api/about（requireServerSuccess）有值时优先服务端内容；
  // 空/全空白（trim 后空串）回退默认资产；URL/HTML 分支在端点接入后自动生效。
  const raw = ABOUT_DOCUMENT.trim()

  if (!raw) {
    return { status: 'markdown', content: ABOUT_DOCUMENT }
  }

  if (isHttpUrl(raw)) {
    return { status: 'url', url: raw }
  }

  if (isLikelyHtml(raw)) {
    return { status: 'html', html: raw }
  }

  return { status: 'markdown', content: ABOUT_DOCUMENT }
}
