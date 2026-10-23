/**
 * 文件夹导入的 JSON 用例解析与分组轮次构建（INT-1613；V9.7.10 `utils/testCaseStrategy.ts` +
 * `utils/folderParser.ts` 平移，§5.7.6 恢复多轮导入）。
 *
 * 口径：
 * - 每个 `.json` 用例文件 = 一个用例分组，分组键 = JSON 文件名去扩展名；其 `rounds` 数组长度
 *   即该用例的轮数，解析结果覆盖自动推断的 rounds。
 * - 支持 V9.7.10 的三种 JSON 形态：rounds 多轮 / flat 单轮（顶层即 segment）/ txt 数组单轮。
 * - 未被任何 JSON 引用的音频回退按最子级文件夹分组；无 JSON 时全部按文件夹分组，
 *   rounds 按 §5.7.6 推断：1 个音频 = 1 轮；多个音频 = 1 轮多音频。
 * - 组内轮次共用同一对象引用（merge 后回填 audio_id，末文件提交时整组 rounds 一次带出）。
 */
import type {
  UploadRoundAudioConfig,
  UploadRoundConfig,
} from '@/infrastructure/api/audio-upload-api'

/** JSON 用例分组（rounds 已归一化为升序连续 1..N） */
export interface CaseGroup {
  /** 分组键（JSON 文件名去扩展名） */
  groupKey: string
  /** 源文件（webkitRelativePath 或 name；标注解析时据此排除用例 JSON） */
  fileName: string
  rounds: UploadRoundConfig[]
  /** JSON 引用的音频文件名（用于把音频归到本分组） */
  audioNames: string[]
  /** case 级背景噪声（rounds 外层） */
  backgroundNoise?: unknown
}

/** 一个导入分组：待处理音频 + 整组轮次 */
export interface AudioImportGroup {
  groupKey: string
  files: File[]
  /** 整组轮次（组内所有文件共享同一引用） */
  rounds: UploadRoundConfig[]
}

/** 文件相对路径（文件夹选择时含子目录） */
export function relativePathOf(file: File): string {
  return file.webkitRelativePath || file.name
}

/** 取文件所在的最子级文件夹名（V9.7.10 getLeafFolderName 对位：相对路径倒数第二段；
 *  无文件夹结构时按文件名去扩展名回退） */
export function leafFolderName(file: File): string {
  const rel = file.webkitRelativePath || ''
  if (rel) {
    const parts = rel.split('/').filter(Boolean)
    if (parts.length >= 2) return parts[parts.length - 2] ?? ''
  }
  return file.name.replace(/\.[^.]+$/, '')
}

/** 文件名去扩展名（分组/匹配键） */
function baseNameWithoutExt(name: string): string {
  const leaf = name.split('/').filter(Boolean).pop() ?? name
  return leaf.replace(/\.[^.]+$/, '')
}

function readAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(new Error(`读取文件失败: ${file.name}`))
    reader.readAsText(file)
  })
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** segment 里的音频名（V9.7.10 三键兼容：audio / audio_name / audioName） */
function audioNameOf(item: Record<string, unknown>): string {
  return String(item.audio ?? item.audio_name ?? item.audioName ?? '')
}

/** 收集一项里引用到的音频名（主音频 + 背景噪声 + 干扰人；用于把音频文件归到该 JSON 分组） */
function collectAudioNames(item: Record<string, unknown>, out: string[]): void {
  const direct = audioNameOf(item)
  if (direct) out.push(direct)
  const bg = asRecord(item.background_noise)
  if (bg) {
    const bgAudio = audioNameOf(bg)
    if (bgAudio) out.push(bgAudio)
  }
  if (Array.isArray(item.interferers)) {
    for (const raw of item.interferers) {
      const interf = asRecord(raw)
      if (!interf) continue
      const name = audioNameOf(interf)
      if (name) out.push(name)
    }
  }
}

/** 单个 segment → 轮内音频（play_order 按 1..n 升序写；spl/设备/噪声原样保留） */
function toRoundAudio(
  item: Record<string, unknown>,
  playOrder: number
): UploadRoundAudioConfig {
  const audio: UploadRoundAudioConfig = {
    audio_name: audioNameOf(item),
    play_order: playOrder,
  }
  if (item.spl != null && item.spl !== '') audio.spl = Number(item.spl)
  const deviceName = item.playback_device_name ?? item.playbackDeviceName
  if (deviceName) audio.playback_device_name = String(deviceName)
  if (item.background_noise) audio.background_noise = item.background_noise
  return audio
}

/** segment 级执行控制字段提升到轮级（V9.7.10 口径：取最后一个非空值；后端 RoundConfigItem extra 保留） */
function promoteExecControlFields(
  sources: Array<Record<string, unknown>>,
  round: UploadRoundConfig
): void {
  for (const field of ['is_interruption', 'record_mode']) {
    let value: unknown
    for (const source of sources) {
      if (source[field] !== undefined && source[field] !== null && source[field] !== '') {
        value = source[field]
      }
    }
    if (value !== undefined) round[field] = value
  }
}

/** rounds 多轮 JSON：{ rounds: [{ round_number?, segments: [{ audio, ... }] }] } */
function buildRoundsFromRoundsJson(
  raw: Record<string, unknown>,
  audioNames: string[]
): UploadRoundConfig[] {
  const rounds: UploadRoundConfig[] = []
  for (const rawRound of raw.rounds as unknown[]) {
    const roundObj = asRecord(rawRound)
    if (!roundObj) continue
    const segments = (Array.isArray(roundObj.segments) ? roundObj.segments : [])
      .map((seg) => asRecord(seg))
      .filter((seg): seg is Record<string, unknown> => seg !== null)
    const audios = segments.map((seg, idx) => toRoundAudio(seg, idx + 1))
    for (const seg of segments) collectAudioNames(seg, audioNames)
    const round: UploadRoundConfig = { round_number: rounds.length + 1, audios }
    if (roundObj.background_noise) {
      round.background_noise = roundObj.background_noise
      const bg = asRecord(roundObj.background_noise)
      if (bg) {
        const bgAudio = audioNameOf(bg)
        if (bgAudio) audioNames.push(bgAudio)
      }
    }
    promoteExecControlFields(segments, round)
    rounds.push(round)
  }
  if (raw.background_noise) {
    const bg = asRecord(raw.background_noise)
    if (bg) {
      const bgAudio = audioNameOf(bg)
      if (bgAudio) audioNames.push(bgAudio)
    }
  }
  return rounds
}

/** flat 单轮 JSON：顶层直接是 segment 字段 { audio, spl?, ... } */
function buildRoundsFromFlatJson(
  raw: Record<string, unknown>,
  audioNames: string[]
): UploadRoundConfig[] {
  const audio = toRoundAudio(raw, 1)
  if (!audio.audio_name) return []
  collectAudioNames(raw, audioNames)
  const round: UploadRoundConfig = { round_number: 1, audios: [audio] }
  promoteExecControlFields([raw], round)
  return [round]
}

/** txt 数组单轮 JSON：{ txt: [{ audio, ... }] } */
function buildRoundsFromTxtArrayJson(
  raw: Record<string, unknown>,
  audioNames: string[]
): UploadRoundConfig[] {
  const items = (raw.txt as unknown[])
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null)
  if (items.length === 0) return []
  const audios = items.map((item, idx) => toRoundAudio(item, idx + 1))
  for (const item of items) collectAudioNames(item, audioNames)
  if (raw.background_noise) {
    const bg = asRecord(raw.background_noise)
    if (bg) {
      const bgAudio = audioNameOf(bg)
      if (bgAudio) audioNames.push(bgAudio)
    }
  }
  const round: UploadRoundConfig = { round_number: 1, audios }
  promoteExecControlFields(items, round)
  return [round]
}

/**
 * 解析单个 JSON 用例文件（V9.7.10 selectStrategy 三策略同口径）。
 * 无法识别为用例（含解析失败）返回 null，调用方跳过。
 */
export function parseCaseJson(content: string, fileName: string): CaseGroup | null {
  let raw: Record<string, unknown> | null
  try {
    raw = asRecord(JSON.parse(content))
  } catch {
    return null
  }
  if (!raw) return null

  const audioNames: string[] = []
  let rounds: UploadRoundConfig[] = []
  if (Array.isArray(raw.rounds)) {
    rounds = buildRoundsFromRoundsJson(raw, audioNames)
  } else if (Array.isArray(raw.txt) && raw.txt.length > 0) {
    rounds = buildRoundsFromTxtArrayJson(raw, audioNames)
  } else if (audioNameOf(raw)) {
    rounds = buildRoundsFromFlatJson(raw, audioNames)
  }
  if (rounds.length === 0) return null

  const group: CaseGroup = {
    groupKey: baseNameWithoutExt(fileName),
    fileName,
    rounds,
    audioNames,
  }
  if (raw.background_noise) group.backgroundNoise = raw.background_noise
  return group
}

/** 解析选中的 JSON 用例文件 → 分组 Map（分组键 = JSON 文件名去扩展名） */
export async function buildCaseGroups(jsonFiles: File[]): Promise<Map<string, CaseGroup>> {
  const groups = new Map<string, CaseGroup>()
  for (const file of jsonFiles) {
    try {
      const group = parseCaseJson(await readAsText(file), relativePathOf(file))
      if (group) groups.set(group.groupKey, group)
    } catch {
      // 单个文件读取/解析失败跳过（其余照常；全失败由调用方提示）
    }
  }
  return groups
}

/** 无 JSON 时的轮次推断（§5.7.6）：1 个音频 = 1 轮；多个音频 = 1 轮多音频（都是单轮） */
export function inferRounds(files: File[]): UploadRoundConfig[] {
  if (files.length === 0) return []
  return [
    {
      round_number: 1,
      audios: files.map((file, idx) => ({ audio_name: file.name, play_order: idx + 1 })),
    },
  ]
}

/**
 * 把待导入音频按分组归队（V9.7.10 groupAudiosByTestCase / groupAudioFilesByLeafFolder 同口径）：
 * - 有 JSON 用例：被 JSON 引用的音频归入该 JSON 分组（整体 rounds 用 JSON 的）；未被引用的
 *   音频各自成组（分组键 = 文件名去扩展名），轮次按文件夹/单文件推断。
 * - 无 JSON：按最子级文件夹分组，轮次按 §5.7.6 推断。
 */
export function buildAudioImportGroups(
  audioFiles: File[],
  caseGroups: Map<string, CaseGroup>
): AudioImportGroup[] {
  const buckets = new Map<string, { files: File[]; group?: CaseGroup }>()
  const push = (key: string, file: File, group?: CaseGroup) => {
    const bucket = buckets.get(key) ?? { files: [], group }
    bucket.files.push(file)
    buckets.set(key, bucket)
  }

  if (caseGroups.size === 0) {
    for (const file of audioFiles) push(leafFolderName(file), file)
  } else {
    const audioNameToGroup = new Map<string, string>()
    for (const [groupKey, group] of caseGroups) {
      for (const rawName of group.audioNames) {
        const leaf = rawName.split('/').pop() ?? rawName
        audioNameToGroup.set(leaf, groupKey)
        audioNameToGroup.set(baseNameWithoutExt(leaf), groupKey)
      }
    }
    for (const file of audioFiles) {
      const matched =
        audioNameToGroup.get(file.name) ?? audioNameToGroup.get(baseNameWithoutExt(file.name))
      if (matched) {
        push(matched, file, caseGroups.get(matched))
      } else {
        push(baseNameWithoutExt(file.name), file)
      }
    }
  }

  return Array.from(buckets.entries()).map(([groupKey, bucket]) => ({
    groupKey,
    files: bucket.files,
    rounds:
      bucket.group && bucket.group.rounds.length > 0
        ? bucket.group.rounds
        : inferRounds(bucket.files),
  }))
}

/**
 * merge 后把真实 audio_id 回填进整组 rounds（组内前几个文件 merge 时 create_test_case=false，
 * 到末文件才整组提交；后端查 audio_id 依赖这里回填的值，V9.7.10 audioImport.ts 同口径）。
 */
export function applyMergedAudioId(
  rounds: UploadRoundConfig[],
  audioName: string,
  audioId: number
): void {
  const leaf = audioName.split('/').pop() ?? audioName
  for (const round of rounds) {
    for (const audio of round.audios) {
      if (audio.audio_name === audioName || audio.audio_name === leaf) {
        audio.audio_id = audioId
      }
    }
  }
}
