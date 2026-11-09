/**
 * 音频相对路径工具（features/audio-import/lib）。
 * 与后端 `POST /audios/folder-tree` 返回的树节点 `path` 口径对齐：
 * 树节点 path 是「相对音频库根」的目录路径（如 `direct`、`环境理解/子目录`），
 * 而 `AudioAsset.filePath` 实存两种形态：`oss://audios/direct/x.wav` 与
 * `D:/00_static/static/audios/环境理解/…/x.wav`，需要先归一化为 `/audios/` 之后段
 * 才能做前缀匹配。音频管理页文件夹视图与音频选择模态窗共用本工具。
 */

/**
 * 音频相对路径（对齐 /audios/folder-tree 的 path 口径：相对音频库根）。
 * filePath 两种实存形态：`oss://audios/direct/x.wav` 与 `D:/00_static/static/audios/环境理解/…/x.wav`，
 * 统一取 `/audios/` 之后段，才能与文件夹树节点 path（如 `direct`、`环境理解`）前缀匹配。
 */
export function audioRelativePath(filePath: string | null | undefined): string {
  if (!filePath) return ''
  const normalized = filePath.replace(/\\/g, '/')
  const m = normalized.match(/\/audios\/(.+)$/i)
  if (m) return m[1]
  return normalized.replace(/^[a-z]+:\/\//i, '')
}

/**
 * 文件是否归属某文件夹节点（path 为树节点相对路径）。
 * 按 `${folder}/` 目录前缀匹配，避免 `dir1` 误匹配 `dir11` 等同前缀兄弟目录串档。
 */
export function inAudioFolder(
  filePath: string | null | undefined,
  folder: string
): boolean {
  if (!folder) return false
  return audioRelativePath(filePath).startsWith(`${folder}/`)
}
