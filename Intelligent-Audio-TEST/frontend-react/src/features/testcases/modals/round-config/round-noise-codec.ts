/**
 * 轮次草稿编码/解码（INT-996；用例编辑抽屉轮次噪声与干扰 + 算法参数独立列的序列化辅助）。
 * 真实契约（api_gateway/schemas/testcase.py 实测）：
 * - 算法参数 → test_cases.algorithm_params 独立列 [{round_number, params:[{field_code, field_value}]}]
 * - 背景噪声/干扰人 → config.rounds[].audios[].background_noise / interferers（segment 级；
 *   TestCaseAudioConfigItem extra='allow'；CRUD 服务仅弹出 round 级 algorithm_params/interferers，
 *   segment 级保留——前端必须写 segment 级才能回读）
 * - 声纹 → algorithm_params 独立列 field_code='voiceprint' 对象 {audio_id, playback_device_id, spl, voiceprint_wait_time}
 */
import type { TestCaseBackgroundNoiseItem } from '@/domain/models/evaluationStrategy'
import type {
  RoundAlgorithmParamItem,
  RoundBackgroundNoiseDraft,
  RoundInterfererDraft,
  RoundNoiseDraft,
  RoundVoiceprintDraft,
} from '@/features/testcases/modals/round-config/round-nav'

/** algorithm_params 独立列按轮号取 params 数组（缺省/异常返回空数组） */
export function algorithmParamsForRound(
  column: unknown,
  roundNumber: number
): RoundAlgorithmParamItem[] {
  if (!Array.isArray(column)) return []
  const entry = column.find((e) => {
    if (typeof e !== 'object' || e === null) return false
    const rec = e as Record<string, unknown>
    const rn = Number(rec.round_number ?? rec.roundNumber)
    return rn === roundNumber
  })
  const params = (entry as { params?: unknown } | undefined)?.params
  if (!Array.isArray(params)) return []
  const result: RoundAlgorithmParamItem[] = []
  for (const p of params) {
    if (typeof p !== 'object' || p === null) continue
    const rec = p as Record<string, unknown>
    const code = String(rec.field_code ?? rec.fieldCode ?? '')
    if (!code) continue
    result.push({ field_code: code, field_value: rec.field_value ?? rec.fieldValue })
  }
  return result
}

/** 按 field_code 取 params 中的值（兼容旧拆分字段 camelCase/snake_case 双写） */
function paramValue(params: RoundAlgorithmParamItem[], codes: string[]): unknown {
  for (const code of codes) {
    const item = params.find((p) => p.field_code === code)
    if (item && item.field_value !== undefined && item.field_value !== null) return item.field_value
  }
  return null
}

function normalizeId(value: unknown): number | string | null {
  if (value === undefined || value === null || value === '') return null
  return typeof value === 'number' ? value : String(value)
}

function normalizeIds(value: unknown): Array<number | string> {
  if (!Array.isArray(value)) return []
  return value.map((v) => normalizeId(v)).filter((v): v is number | string => v != null)
}

/** id 列表 → 纯数字数组（落库字段只收数字，非法值剔除） */
function toNumericIds(value: Array<number | string> | undefined): number[] {
  return (value ?? [])
    .map((v) => (typeof v === 'number' ? v : Number(v)))
    .filter((n) => !Number.isNaN(n))
}

/** config 单轮 → 背景噪声草稿（优先 segment 级 audios[0].background_noise，回退 round 级 background_noise） */
function backgroundNoiseDraftFromRound(
  round: Record<string, unknown>
): RoundBackgroundNoiseDraft | null {
  const audios = Array.isArray(round.audios) ? (round.audios as Array<Record<string, unknown>>) : []
  const seg = audios[0] ?? {}
  const segBg =
    seg.background_noise && typeof seg.background_noise === 'object'
      ? (seg.background_noise as Record<string, unknown>)
      : null
  const roundBg =
    round.background_noise && typeof round.background_noise === 'object'
      ? (round.background_noise as Record<string, unknown>)
      : null
  const raw = segBg ?? roundBg
  if (!raw) return null
  const audioField = raw.audio
  const audioBrief =
    audioField && typeof audioField === 'object' && !Array.isArray(audioField)
      ? {
          id: (audioField as Record<string, unknown>).id as number | string,
          name: String((audioField as Record<string, unknown>).name ?? ''),
          duration: (audioField as Record<string, unknown>).duration as number | null,
          tags: Array.isArray((audioField as Record<string, unknown>).tags)
            ? ((audioField as Record<string, unknown>).tags as string[])
            : [],
        }
      : undefined
  const fileName = typeof audioField === 'string' ? audioField : undefined
  return {
    audioId: normalizeId(raw.audio_id ?? raw.audioId) ?? (fileName ? fileName : null),
    audioName:
      (raw.audio_name as string) ?? (raw.audioName as string) ?? audioBrief?.name ?? fileName ?? null,
    audio: audioBrief ?? null,
    spl: Number(raw.spl ?? 0),
    deviceIds: normalizeIds(raw.device_ids ?? raw.deviceIds),
    speakerGroupIds: normalizeIds(
      raw.playback_speaker_group_ids ?? raw.playbackSpeakerGroupIds
    ),
    loop: Boolean(raw.loop ?? true),
  }
}

/** config 单轮 → 干扰人草稿（优先 segment 级 audios[0].interferers，回退 round 级 interferers；兼容嵌套/扁平/名称格式） */
function interferersDraftFromRound(
  round: Record<string, unknown>
): RoundInterfererDraft[] {
  const audios = Array.isArray(round.audios) ? (round.audios as Array<Record<string, unknown>>) : []
  const seg = audios[0] ?? {}
  const segIfrs = Array.isArray(seg.interferers) ? (seg.interferers as Array<Record<string, unknown>>) : []
  const roundIfrs = Array.isArray(round.interferers) ? (round.interferers as Array<Record<string, unknown>>) : []
  const raw = segIfrs.length > 0 ? segIfrs : roundIfrs
  return raw.map((itf, i) => {
    const audioField = itf.audio
    const audioName = (itf.audio_name as string) ?? (itf.audioName as string) ?? (typeof audioField === 'string' ? audioField : undefined)
    const devName = (itf.playback_device_name as string) ?? (itf.playbackDeviceName as string) ?? undefined
    return {
      id: `ifr-backfill-${i}`,
      audioId: normalizeId(itf.audio_id ?? itf.audioId) ?? (audioName ? audioName : null),
      audioName: audioName ?? null,
      playbackDeviceId: normalizeId(itf.playback_device_id ?? itf.playbackDeviceId) ?? (devName ? devName : null),
      speakerGroupId: normalizeId(
        itf.playback_speaker_group_id ?? itf.playbackSpeakerGroupId
      ),
      spl: Number(itf.spl ?? 70),
      startDelay: Number(itf.start_delay ?? itf.startDelay ?? 0),
      loop: Boolean(itf.loop ?? false),
    }
  })
}

/** algorithm_params 独立列 + config 单轮 → 声纹草稿（voiceprint 对象 / 旧拆分字段双兼容） */
function voiceprintDraftFromParams(
  params: RoundAlgorithmParamItem[]
): RoundVoiceprintDraft {
  const vpItem = params.find((p) => p.field_code === 'voiceprint')
  const vpObj =
    vpItem && typeof vpItem.field_value === 'object' && vpItem.field_value !== null
      ? (vpItem.field_value as Record<string, unknown>)
      : null
  const legacyEnabled = paramValue(params, ['voiceprint_enabled', 'voiceprintEnabled'])
  const enabled =
    vpObj != null ||
    legacyEnabled === true ||
    legacyEnabled === 'true' ||
    legacyEnabled === 1
  return {
    enabled,
    audioId:
      normalizeId(vpObj?.audio_id ?? vpObj?.audioId ?? vpObj?.audio) ??
      normalizeId(paramValue(params, ['voiceprint_audio_id', 'voiceprintAudioId'])),
    audioName: null,
    playbackDeviceId:
      normalizeId(vpObj?.playback_device_id ?? vpObj?.playbackDeviceId) ??
      normalizeId(paramValue(params, ['voiceprint_playback_device_id', 'voiceprintPlaybackDeviceId'])),
    speakerGroupId: normalizeId(
      vpObj?.playback_speaker_group_id ?? vpObj?.playbackSpeakerGroupId
    ),
    spl: Number(vpObj?.spl ?? paramValue(params, ['voiceprint_spl', 'voiceprintSpl']) ?? 75),
    waitSec: Number(
      vpObj?.voiceprint_wait_time ?? vpObj?.voiceprintWaitTime ?? paramValue(params, ['voiceprint_wait_time', 'voiceprintWaitTime']) ?? 5
    ),
  }
}

/** config 单轮 + 独立列 params → 轮次噪声与干扰草稿 */
export function noiseDraftFromRound(
  round: Record<string, unknown>,
  params: RoundAlgorithmParamItem[]
): RoundNoiseDraft {
  return {
    backgroundNoise: backgroundNoiseDraftFromRound(round),
    voiceprint: voiceprintDraftFromParams(params),
    interferers: interferersDraftFromRound(round),
  }
}

/** 背景噪声草稿 → segment 级 background_noise（snake_case；剔除 audio 简报）
 *  关联逻辑音箱时写 playback_speaker_group_ids，不再写实体设备 device_ids。 */
export function serializeBackgroundNoise(
  bg: RoundBackgroundNoiseDraft
): Record<string, unknown> {
  const groupIds = toNumericIds(bg.speakerGroupIds)
  const deviceIds = toNumericIds(bg.deviceIds)
  return {
    audio_id: bg.audioId,
    ...(bg.audioName ? { audio_name: bg.audioName } : {}),
    spl: bg.spl,
    ...(groupIds.length > 0
      ? { playback_speaker_group_ids: groupIds }
      : { device_ids: deviceIds }),
    loop: bg.loop,
  }
}

/** 干扰人草稿 → segment 级 interferers 项（snake_case；剔除本地 id） */
export function serializeInterferer(ifr: RoundInterfererDraft): Record<string, unknown> {
  const groupId = normalizeId(ifr.speakerGroupId)
  return {
    ...(ifr.audioId != null ? { audio_id: ifr.audioId } : {}),
    ...(ifr.audioName ? { audio_name: ifr.audioName } : {}),
    ...(groupId != null
      ? { playback_speaker_group_id: Number(groupId) }
      : ifr.playbackDeviceId != null
        ? { playback_device_id: ifr.playbackDeviceId }
        : {}),
    spl: ifr.spl,
    start_delay: ifr.startDelay,
    loop: ifr.loop,
  }
}

/** 声纹草稿 → algorithm_params voiceprint 对象（enabled=false 时返回 null，不入列） */
export function serializeVoiceprint(
  vp: RoundVoiceprintDraft
): Record<string, unknown> | null {
  if (!vp.enabled) return null
  const groupId = normalizeId(vp.speakerGroupId)
  return {
    ...(vp.audioId != null ? { audio_id: vp.audioId } : {}),
    ...(groupId != null
      ? { playback_speaker_group_id: Number(groupId) }
      : vp.playbackDeviceId != null
        ? { playback_device_id: vp.playbackDeviceId }
        : {}),
    spl: vp.spl,
    voiceprint_wait_time: vp.waitSec,
  }
}

/** 全局背景噪声（config.background_noise 原样对象）→ 用例级草稿 */
export function globalNoiseFromDto(
  raw: Record<string, unknown> | null | undefined
): TestCaseBackgroundNoiseItem | null {
  if (!raw) return null
  return {
    audioId: (raw.audio_id ?? raw.audioId ?? null) as number | string | null,
    audioName: (raw.audio_name ?? raw.audioName ?? null) as string | null,
    audio: (raw.audio as TestCaseBackgroundNoiseItem['audio']) ?? null,
    spl: raw.spl != null ? Number(raw.spl) : null,
    deviceIds: normalizeIds(raw.device_ids ?? raw.deviceIds),
    speakerGroupIds: normalizeIds(
      raw.playback_speaker_group_ids ?? raw.playbackSpeakerGroupIds
    ),
    deviceNames: Array.isArray(raw.device_names ?? raw.deviceNames)
      ? ((raw.device_names ?? raw.deviceNames) as string[])
      : undefined,
    loop: raw.loop == null ? true : Boolean(raw.loop),
  }
}

/** 全局背景噪声草稿 → config.background_noise（关联逻辑音箱时不再写 device_ids） */
export function serializeGlobalNoise(
  noise: TestCaseBackgroundNoiseItem
): Record<string, unknown> {
  const groupIds = toNumericIds(noise.speakerGroupIds)
  const deviceIds = toNumericIds(noise.deviceIds)
  return {
    ...(noise.audioId != null ? { audio_id: noise.audioId } : {}),
    ...(noise.audioName ? { audio_name: noise.audioName } : {}),
    ...(noise.spl != null ? { spl: noise.spl } : {}),
    ...(groupIds.length > 0
      ? { playback_speaker_group_ids: groupIds }
      : { device_ids: deviceIds }),
    loop: noise.loop ?? true,
  }
}

/** 把轮次噪声与干扰写入 config.rounds[].audios[]（segment 级；audios 为空时背景噪声回退 round 级） */
export function applyNoiseToRound(
  round: Record<string, unknown>,
  noise: RoundNoiseDraft
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...round }
  const audios = Array.isArray(round.audios) ? [...(round.audios as Array<Record<string, unknown>>)] : []
  if (audios.length > 0) {
    const first: Record<string, unknown> = { ...audios[0] }
    if (noise.backgroundNoise) {
      first.background_noise = serializeBackgroundNoise(noise.backgroundNoise)
    } else {
      delete first.background_noise
    }
    if (noise.interferers.length > 0) {
      first.interferers = noise.interferers.map(serializeInterferer)
    } else {
      delete first.interferers
    }
    audios[0] = first
    result.audios = audios
  } else if (noise.backgroundNoise) {
    // 无音频时背景噪声落 round 级（CRUD 保留、执行侧 round 级读取）；干扰人无 audio 锚点不入列
    result.background_noise = serializeBackgroundNoise(noise.backgroundNoise)
  } else {
    delete result.background_noise
  }
  return result
}
