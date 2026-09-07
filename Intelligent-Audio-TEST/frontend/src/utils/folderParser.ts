import { stripAlgorithmParamSchema } from './utils';

/**
 * 文件夹解析工具：解析文件夹结构，判定轮次模式，构建 rounds 配置。
 *
 * 两种轮次模式：
 * - multi_round: 每个音频 = 一轮（单个音频的最子级文件夹）
 * - single_round_multi_audio: 多个音频同轮（多个音频的最子级文件夹）
 *
 * 标注文件位置规则：
 * - 最子级文件夹的父级目录下，文件名 = 最子级文件夹名
 * - 例如：root/folder1/round_a/audio1.wav → 标注文件 root/folder1/round_a.json
 */

export interface AudioFileInfo {
  file: File
  name: string
  relativePath: string
  webkitRelativePath: string
}

export interface RoundAudioConfig {
  audioName: string
  playOrder: number
  spl?: number
  playbackDeviceId?: string
  /** 上传合并后回填的音频 ID（测试用例按 ID 引用音频） */
  audioId?: string | number
}

/** 文件解析策略专用类型（原样保留）：音频以 audioName 文件名引用；
 * 与 TestCaseModal/types.ts 的 RoundConfigItem（audioId 引用、含 evaluation）结构不同，不可合并 */
export interface RoundConfig {
  roundNumber: number
  audios: RoundAudioConfig[]
  annotationFile?: string
  algorithmParams?: any[]
}

export interface TestCaseConfig {
  rounds?: RoundConfig[]
  groupName?: string
  inheritTags?: boolean
  algorithmParams?: any[]
  /** 后端用例配置协议原文（round_config_service 仅读 background_noise，无 camelCase 兜底） */
  background_noise?: any
}

/**
 * 获取文件所在的最子级文件夹名称
 */
function getLeafFolderName(relativePath: string): string {
  const parts = relativePath.split('/').filter(Boolean)
  if (parts.length < 2) return ''
  // 最子级文件夹 = 倒数第二部分（最后一部分是文件名）
  return parts[parts.length - 2] || ''
}

/**
 * 获取文件的父级目录路径
 */
function getParentDirPath(relativePath: string): string {
  const parts = relativePath.split('/').filter(Boolean)
  if (parts.length < 2) return ''
  parts.pop() // 移除文件名
  return parts.join('/')
}

/**
 * 按最子级文件夹分组音频文件
 */
export function groupAudioFilesByLeafFolder(
  audioFiles: AudioFileInfo[]
): Map<string, AudioFileInfo[]> {
  const groups = new Map<string, AudioFileInfo[]>()

  for (const audio of audioFiles) {
    const leafFolder = getLeafFolderName(audio.relativePath || audio.webkitRelativePath)
    if (!leafFolder) {
      // 没有文件夹结构的文件，按文件名分组
      const fileName = audio.name.replace(/\.[^.]+$/, '')
      if (!groups.has(fileName)) {
        groups.set(fileName, [])
      }
      groups.get(fileName)!.push(audio)
    } else {
      if (!groups.has(leafFolder)) {
        groups.set(leafFolder, [])
      }
      groups.get(leafFolder)!.push(audio)
    }
  }

  return groups
}

/**
 * 查找与最子级文件夹同名的标注文件
 * 标注文件位置（按优先级匹配）：
 *   1. 最子级文件夹的父级目录下（如 root/folder1/round_a/audio1.wav → root/folder1/round_a.json）
 *   2. 最子级文件夹内部（如 root/folder1/round_a/audio1.wav → root/folder1/round_a/round_a.json）
 *   3. 与音频同级目录（无文件夹结构时，如 root/audio1.wav → root/audio1.json）
 */
export function findAnnotationForLeafFolder(
  leafFolder: string,
  allFiles: File[]
): File | null {
  const annotationExts = ['json', 'jsonl', 'rttm', 'stm', 'txt']

  // 第一轮：匹配父级目录下的同名标注文件
  for (const file of allFiles) {
    const relativePath = (file as any).webkitRelativePath || file.name
    const parts = relativePath.split('/').filter(Boolean)
    if (parts.length < 2) continue

    const fileName = parts[parts.length - 1]
    const fileNameWithoutExt = fileName.replace(/\.[^.]+$/, '')

    if (fileNameWithoutExt === leafFolder) {
      const ext = fileName.split('.').pop()?.toLowerCase() || ''
      if (annotationExts.includes(ext)) {
        return file
      }
    }
  }

  // 第二轮：匹配最子级文件夹内部或与音频同级的同名标注文件
  for (const file of allFiles) {
    const relativePath = (file as any).webkitRelativePath || file.name
    const parts = relativePath.split('/').filter(Boolean)
    if (parts.length === 0) continue

    const fileName = parts[parts.length - 1]
    const fileNameWithoutExt = fileName.replace(/\.[^.]+$/, '')

    if (fileNameWithoutExt === leafFolder) {
      const ext = fileName.split('.').pop()?.toLowerCase() || ''
      if (annotationExts.includes(ext)) {
        return file
      }
    }
  }

  return null
}

/**
 * 判定轮次模式
 * - 单个音频 → multi_round（每个音频一轮）
 * - 多个音频 → single_round_multi_audio（多音频同轮）
 */
export function determineRoundMode(
  audioFiles: AudioFileInfo[]
): 'multi_round' | 'single_round_multi_audio' {
  return audioFiles.length === 1 ? 'multi_round' : 'single_round_multi_audio'
}

/**
 * 构建 rounds 配置
 */
export function buildRoundsConfig(
  audioFiles: AudioFileInfo[],
  allFiles: File[],
  spl: number = 65.0,
  playbackDeviceId?: string
): RoundConfig[] {
  if (audioFiles.length === 0) return []

  const mode = determineRoundMode(audioFiles)
  const makeAudioConfig = (audio: AudioFileInfo, playOrder: number): RoundAudioConfig => {
    const cfg: RoundAudioConfig = {
      audioName: audio.name,
      playOrder: playOrder
    }
    // spl 为有效数字时才写入（undefined 不传，后端从标注提取）
    if (spl != null && !isNaN(Number(spl))) {
      cfg.spl = Number(spl)
    }
    if (playbackDeviceId) cfg.playbackDeviceId = playbackDeviceId
    return cfg
  }

  if (mode === 'single_round_multi_audio') {
    // 多音频同轮
    const audios = audioFiles.map((audio, idx) => makeAudioConfig(audio, idx))
    // 查找标注文件（最子级文件夹同名）
    const leafFolder = getLeafFolderName(
      audioFiles[0].relativePath || audioFiles[0].webkitRelativePath
    )
    const annotationFile = leafFolder ? findAnnotationForLeafFolder(leafFolder, allFiles) : null

    return [{
      roundNumber: 1,
      audios,
      annotationFile: annotationFile?.name
    }]
  } else {
    // 每个音频一轮
    const rounds: RoundConfig[] = []
    audioFiles.forEach((audio, idx) => {
      const leafFolder = getLeafFolderName(
        audio.relativePath || audio.webkitRelativePath
      )
      const annotationFile = leafFolder ? findAnnotationForLeafFolder(leafFolder, allFiles) : null

      rounds.push({
        roundNumber: idx + 1,
        audios: [makeAudioConfig(audio, 0)],
        annotationFile: annotationFile?.name
      })
    })
    return rounds
  }
}

/**
 * 从 File 数组中提取音频文件信息
 */
export function extractAudioFiles(files: File[]): AudioFileInfo[] {
  const audioExts = ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg']

  return files
    .filter(file => {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      return audioExts.includes(ext)
    })
    .map(file => ({
      file,
      name: file.name,
      relativePath: (file as any).webkitRelativePath || file.name,
      webkitRelativePath: (file as any).webkitRelativePath || ''
    }))
}

/**
 * 构建完整的 testCaseConfig
 */
export function buildTestCaseConfig(
  audioFiles: AudioFileInfo[],
  allFiles: File[],
  options: {
    spl?: number
    playbackDeviceId?: string
    groupName?: string
    inheritTags?: boolean
    algorithmParams?: any[]
  } = {}
): TestCaseConfig {
  const rounds = buildRoundsConfig(
    audioFiles,
    allFiles,
    options.spl,
    options.playbackDeviceId
  )

  // AlgorithmSelector 会把 schema 定义（caseAlgorithmParams / algorithmFormSchema）塞进 params，
  // 这里剔除，避免 schema 被当成参数值传给后端
  const normalizedParams = stripAlgorithmParamSchema(options.algorithmParams)

  return {
    rounds: rounds.length > 0 ? rounds : undefined,
    groupName: options.groupName,
    inheritTags: options.inheritTags ?? true,
    algorithmParams: normalizedParams.length > 0 ? normalizedParams : undefined
  }
}
