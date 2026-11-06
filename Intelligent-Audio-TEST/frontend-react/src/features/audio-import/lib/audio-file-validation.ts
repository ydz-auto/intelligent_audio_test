/**
 * 上传前音频内容预检（INT-2192）。
 *
 * 背景：audio_service 的 upload/register、upload/merge 不校验音频内容，0 字节或纯文本改名
 * 的 `.wav` 会被当作成功入库（回读 duration=0），前端没有任何文件会进入 `failed`。
 * 上传窗在提交前用浏览器媒体探针拦掉这类文件并逐条给出失败原因；探针用 `<audio>`
 * 只读容器头（preload=metadata），不把整文件解成 PCM，大文件也不吃内存。
 * 探针不可用 / 超时 / 容器未给时长（Infinity）时按「未知」放行，交由后端兜底，不误杀。
 */

/** 支持的音频扩展名（上传窗 accept / 分类共用） */
export const AUDIO_FILE_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']

/** 上传窗 accept 字符串 */
export const AUDIO_ACCEPT_ATTR = AUDIO_FILE_EXTS.join(',')

/** 是否音频文件（按扩展名，大小写不敏感） */
export function isAudioFile(name: string): boolean {
  const lower = name.toLowerCase()
  return AUDIO_FILE_EXTS.some((ext) => lower.endsWith(ext))
}

/** 单文件内容预检失败项（弹窗逐条 toast） */
export interface AudioFileIssue {
  name: string
  error: string
}

/** 音频时长探针：返回时长（秒）；容器未给时长返回 null；内容不是可解析音频时 reject */
export type AudioProbe = (file: File) => Promise<number | null>

/** 探针上限：超时按「未知」放行，避免个别容器格式卡住整批上传 */
export const AUDIO_PROBE_TIMEOUT_MS = 10_000

/** 预检并发数：媒体探针走浏览器解码线程，过多会互相拖慢 */
const PROBE_CONCURRENCY = 4

/**
 * 浏览器媒体探针（真实文件内容，非 mock）。
 * jsdom / 无 URL.createObjectURL 的环境返回 null（按未知放行），单测注入假探针。
 */
export function probeAudioDuration(
  file: File,
  timeoutMs = AUDIO_PROBE_TIMEOUT_MS
): Promise<number | null> {
  if (typeof Audio === 'undefined' || typeof URL.createObjectURL !== 'function') {
    return Promise.resolve(null)
  }
  return new Promise<number | null>((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const audio = new Audio()
    let settled = false
    const finish = (fn: () => void) => {
      if (settled) return
      settled = true
      audio.onloadedmetadata = null
      audio.onerror = null
      audio.src = ''
      URL.revokeObjectURL(url)
      fn()
    }
    const timer = setTimeout(() => finish(() => resolve(null)), timeoutMs)
    audio.preload = 'metadata'
    audio.onloadedmetadata = () => {
      clearTimeout(timer)
      const duration = audio.duration
      finish(() => resolve(Number.isFinite(duration) ? duration : null))
    }
    audio.onerror = () => {
      clearTimeout(timer)
      finish(() => reject(new Error('文件内容不是可解析的音频文件')))
    }
    audio.src = url
  })
}

/** 单文件预检：返回 null = 可上传；返回字符串 = 该文件的失败原因 */
export async function validateAudioFile(
  file: File,
  probe: AudioProbe = probeAudioDuration
): Promise<string | null> {
  if (file.size <= 0) return '文件为空（0 字节），已跳过'
  try {
    const duration = await probe(file)
    if (duration !== null && duration <= 0) return '音频时长为 0，文件可能已损坏，已跳过'
    return null
  } catch (err) {
    return err instanceof Error && err.message ? err.message : '无法解析为音频文件，已跳过'
  }
}

/**
 * 批量预检（有限并发；结果按选择顺序返回）。
 * 返回的 invalid 只含失败文件，valid 为通过预检、真正进入上传的文件。
 */
export async function validateAudioFiles(
  files: File[],
  probe: AudioProbe = probeAudioDuration
): Promise<{ valid: File[]; invalid: AudioFileIssue[] }> {
  const errors = new Map<File, string>()
  let cursor = 0
  const worker = async () => {
    while (cursor < files.length) {
      const file = files[cursor]
      cursor += 1
      const error = await validateAudioFile(file, probe)
      if (error) errors.set(file, error)
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(PROBE_CONCURRENCY, files.length) }, () => worker())
  )
  return {
    valid: files.filter((file) => !errors.has(file)),
    invalid: files
      .filter((file) => errors.has(file))
      .map((file) => ({ name: file.name, error: errors.get(file) as string })),
  }
}
