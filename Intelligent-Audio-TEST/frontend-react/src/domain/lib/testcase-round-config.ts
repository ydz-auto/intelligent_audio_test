/**
 * 用例轮次配置序列化纯函数（domain/lib 层；11_用例域.md §5.1 RoundConfigEditor）。
 * 编辑抽屉轮次草稿（RoundDraft）⇄ 后端 config.rounds[]（schemas/testcase.py
 * RoundConfigItem：round_number/audios/evaluation）+ algorithm_params 独立列转换：
 * - roundDraftFromConfig / audioDraftFromConfig：真实回填（音频 audio_id/audio_name/spl/
 *   playback_device_id/playback_device_name；评估维度 id/weight/threshold/llmJudgeConfig；
 *   INT-996 算法参数独立列 + 噪声草稿按轮读取）；
 * - roundsToConfig：音频草稿与评估草稿序列化合并（保留原始轮次未编辑字段，
 *   新选维度补 name——INT-877 P3-3；噪声段经 round-noise-codec 写入 audios[0]——INT-996）；
 * - toStrategyOverridesDto：用例级覆盖 camelCase → snake_case（后端
 *   EvaluationStrategyMergeService 读 raw dict 的 `background_noise` 键，INT-877 P3-1）。
 * 纯函数无副作用，可单测（vitest .ts 直跑）。
 */
import type { CaseEvaluationStrategy } from '@/domain/models/evaluationStrategy'
import type { CasePlaybackDevice } from '@/domain/models/testCase'
import {
  emptyRoundNoise,
  type RoundAudioDraft,
  type RoundDraft,
  type RoundEvaluationDraft,
  type RoundAlgorithmParamItem,
} from '@/domain/models/testCaseRound'
import {
  algorithmParamsForRound,
  applyNoiseToRound,
  noiseDraftFromRound,
} from '@/features/testcases/modals/round-config/round-noise-codec'

/** 新建态默认轮次（单轮空评估 + 空音频/空算法参数/空噪声；rounds 由保存侧序列化为 config.rounds） */
export function defaultRounds(): RoundDraft[] {
  return [
    {
      number: 1,
      audioCount: 0,
      dimensionCount: 0,
      evaluation: { enabled: true, selectedIds: [], params: {} },
      audios: [],
      algorithmParams: [],
      noise: emptyRoundNoise(),
    },
  ]
}

/**
 * 用例 config.rounds[].audios[] → 已配置播放设备（去重；INT-1534 播放器设备区真实数据源）。
 * 后端音频条目字段为 playback_device_id / playback_device_name（INT-996 编辑回填同款），
 * 缺设备名时以「设备 {id}」占位，避免把未命名的设备静默丢掉。
 */
export function casePlaybackDevicesFromConfig(
  config: Record<string, unknown> | null | undefined
): CasePlaybackDevice[] {
  if (!config) return []
  const rounds = Array.isArray(config.rounds) ? config.rounds : []
  const seen = new Set<string>()
  const devices: CasePlaybackDevice[] = []
  for (const round of rounds) {
    if (!round || typeof round !== 'object') continue
    const audios = Array.isArray((round as { audios?: unknown[] }).audios)
      ? ((round as { audios: Array<Record<string, unknown>> }).audios ?? [])
      : []
    for (const audio of audios) {
      if (!audio || typeof audio !== 'object') continue
      const rawId = audio.playback_device_id ?? audio.playbackDeviceId ?? null
      const rawName = audio.playback_device_name ?? audio.playbackDeviceName ?? null
      const id = rawId == null || rawId === '' ? null : String(rawId)
      const name =
        typeof rawName === 'string' && rawName.trim() !== ''
          ? rawName
          : id
            ? `设备 ${id}`
            : null
      if (!name) continue
      const key = `${id ?? ''}::${name}`
      if (seen.has(key)) continue
      seen.add(key)
      devices.push({ id, name })
    }
  }
  return devices
}

/**
 * 后端 config.rounds[].audios 单条 → RoundAudioDraft（编辑回填真实音频：
 * audio_id/audio_name/spl/playback_device_id/playback_device_name）。
 */
export function audioDraftFromConfig(
  raw: Record<string, unknown>,
  index: number
): RoundAudioDraft {
  const audioId = (raw.audio_id ?? raw.audioId ?? null) as number | string | null
  const deviceId = (raw.playback_device_id ?? raw.playbackDeviceId ?? '') as
    | number
    | string
    | null
  return {
    id: `backfill-${index}`,
    audioId,
    audioName: (raw.audio_name ?? raw.audioName ?? null) as string | null,
    spl: Number(raw.spl ?? 65),
    deviceId: deviceId == null ? '' : String(deviceId),
    deviceName: (raw.playback_device_name ?? raw.playbackDeviceName ?? null) as
      | string
      | null,
    playOrder: raw.play_order != null ? Number(raw.play_order) : undefined,
  }
}

/**
 * 后端 config.rounds 单轮 → RoundDraft（编辑回填：轮次数 + 音频/维度摘要 + 评估内容 +
 * INT-996 算法参数独立列 + 噪声与干扰草稿）。
 */
export function roundDraftFromConfig(
  raw: Record<string, unknown>,
  index: number,
  paramsForRound: RoundAlgorithmParamItem[]
): RoundDraft {
  const number = Number(raw.round_number ?? raw.roundNumber ?? index + 1)
  const audios = Array.isArray(raw.audios) ? (raw.audios as Array<Record<string, unknown>>) : []
  const evaluation =
    raw.evaluation && typeof raw.evaluation === 'object'
      ? (raw.evaluation as Record<string, unknown>)
      : null
  const dimensions = Array.isArray(evaluation?.dimensions)
    ? (evaluation.dimensions as Array<Record<string, unknown>>)
    : []
  const draft: RoundEvaluationDraft = {
    enabled: evaluation?.enabled !== false,
    selectedIds: dimensions
      .map((d) => Number(d.id))
      .filter((id) => Number.isFinite(id) && id !== 0),
    params: {},
  }
  for (const d of dimensions) {
    const id = Number(d.id)
    if (!Number.isFinite(id) || id === 0) continue
    const llm =
      d.llmJudgeConfig && typeof d.llmJudgeConfig === 'object'
        ? (d.llmJudgeConfig as Record<string, unknown>)
        : null
    draft.params[id] = {
      weight: Number(d.weight ?? 50),
      threshold: Number(d.threshold ?? 80),
      ...(llm?.model != null ? { model: String(llm.model) } : {}),
      ...(llm?.promptTemplate != null ? { promptTemplate: String(llm.promptTemplate) } : {}),
    }
  }
  return {
    number,
    audioCount: audios.length,
    dimensionCount: dimensions.length,
    evaluation: draft,
    audios: audios.map(audioDraftFromConfig),
    algorithmParams: paramsForRound,
    noise: noiseDraftFromRound(raw, paramsForRound),
  }
}

/** 真实 config.rounds → RoundDraft[]（空/缺失回退默认轮次；INT-996 按轮读独立列 algorithmParams） */
export function roundsFromConfig(
  config: Record<string, unknown> | null | undefined,
  algorithmParams: unknown
): RoundDraft[] {
  const rawRounds = Array.isArray(config?.rounds)
    ? (config.rounds as Array<Record<string, unknown>>)
    : []
  if (rawRounds.length === 0) return defaultRounds()
  return rawRounds.map((raw, i) =>
    roundDraftFromConfig(
      raw,
      i,
      algorithmParamsForRound(algorithmParams, Number(raw.round_number ?? raw.roundNumber ?? i + 1))
    )
  )
}

/**
 * RoundDraft[] → 后端 config.rounds（合并原始轮次保留未编辑字段；
 * audios 由音频草稿序列化（INT-877 P1-1 保存生效，按 audio_id 保留未编辑字段）；
 * evaluation 序列化为 {enabled, dimensions}，新选维度补 name（INT-877 P3-3，dimNameById 解析）；
 * 噪声与干扰段经 round-noise-codec 写入 segment 级 audios[0].background_noise/interferers（INT-996）。
 */
export function roundsToConfig(
  drafts: RoundDraft[],
  originalRounds: Array<Record<string, unknown>> | null | undefined,
  dimNameById: ReadonlyMap<number, string>
): Array<Record<string, unknown>> {
  return drafts.map((draft) => {
    const orig =
      originalRounds?.find(
        (r) => Number(r.round_number ?? r.roundNumber) === draft.number
      ) ?? null
    // 原始单轮 evaluation（保留 name 等未在抽屉编辑的字段；INT-922 保存不得丢维度名）
    const origEval =
      orig?.evaluation && typeof orig.evaluation === 'object'
        ? (orig.evaluation as Record<string, unknown>)
        : null
    const origDims = Array.isArray(origEval?.dimensions)
      ? (origEval.dimensions as Array<Record<string, unknown>>)
      : []
    // 原始单轮 audios（按 audio_id 匹配保留 interferers 等未编辑字段；噪声段由 noise 草稿重写）
    const origAudios = Array.isArray(orig?.audios)
      ? (orig.audios as Array<Record<string, unknown>>)
      : []
    const base: Record<string, unknown> = { ...(orig ?? {}) }
    // 独立列字段/round 级 algorithmParams 由 CRUD 服务弹出，round 内不携带（INT-996 口径）
    delete base.algorithmParams
    delete base.algorithm_params
    return applyNoiseToRound(
      {
        ...base,
        round_number: draft.number,
        audios: draft.audios.map((audio) => {
          const origAudio = origAudios.find(
            (a) => String(a.audio_id ?? a.audioId ?? '') === String(audio.audioId ?? '')
          )
          return {
            ...(origAudio ?? {}),
            audio_id: audio.audioId ?? null,
            audio_name: audio.audioName ?? null,
            spl: audio.spl,
            playback_device_id: audio.deviceId || null,
            playback_device_name: audio.deviceName ?? null,
            ...(audio.playOrder != null ? { play_order: audio.playOrder } : {}),
          }
        }),
        evaluation: {
          enabled: draft.evaluation.enabled,
          dimensions: draft.evaluation.selectedIds.map((id) => {
            const p = draft.evaluation.params[id]
            const origDim = origDims.find((d) => Number(d.id) === id) ?? null
            return {
              ...(origDim ?? {}),
              id,
              name: String(origDim?.name ?? dimNameById.get(id) ?? `dim-${id}`),
              weight: p?.weight ?? Number(origDim?.weight ?? 50),
              threshold: p?.threshold ?? Number(origDim?.threshold ?? 80),
              ...(p?.model || p?.promptTemplate
                ? {
                    llmJudgeConfig: {
                      model: p?.model ?? '',
                      promptTemplate: p?.promptTemplate ?? '',
                    },
                  }
                : {}),
            }
          }),
        },
      },
      draft.noise
    )
  })
}

/**
 * 用例级覆盖 camelCase → snake_case（INT-877 P3-1：后端 EvaluationStrategyMergeService
 * validate_overrides/resolve 读 raw dict 的 `background_noise` 键，camelCase 会被静默丢弃）。
 * dimensions 条目字段保持 llmJudgeConfig（后端 _DIMENSION_OVERRIDE_FIELDS 同 camelCase）。
 */
export function toStrategyOverridesDto(
  overrides: CaseEvaluationStrategy['overrides'] | null | undefined
): Record<string, unknown> | null {
  if (!overrides) return null
  const dto: Record<string, unknown> = {}
  if (overrides.dimensions != null) dto.dimensions = overrides.dimensions
  if (overrides.backgroundNoise != null) dto.background_noise = overrides.backgroundNoise
  return Object.keys(dto).length > 0 ? dto : null
}
