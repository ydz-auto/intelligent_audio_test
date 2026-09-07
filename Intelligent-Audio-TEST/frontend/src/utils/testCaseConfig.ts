import type { TestCaseFormData } from '../domain';
import { TestType } from '@/domain/enums';
import { snakifyKeys } from './keyTransform';

/**
 * AlgorithmSelector 会把 schema 定义（caseAlgorithmParams / algorithmFormSchema）塞进 params 对象，
 * 这些不是参数值，传给后端会产生垃圾数据。此函数把 params 归一化为 [{fieldCode, fieldValue}] 并剔除 schema。
 * 接受对象、数组两种输入，返回数组。
 */
export function stripAlgorithmParamSchema(params: any): any[] {
  if (!params) return [];
  const SCHEMA_KEYS = new Set(['caseAlgorithmParams', 'algorithmFormSchema']);
  if (Array.isArray(params)) {
    return params
      .filter((p: any) => !SCHEMA_KEYS.has(p.fieldCode))
      .map((p: any) => ({
        fieldCode: p.fieldCode,
        fieldValue: p.fieldValue
      }))
      .filter((p: any) => p.fieldCode);
  }
  if (typeof params === 'object') {
    return Object.entries(params)
      .filter(([k]) => !SCHEMA_KEYS.has(k))
      .map(([fieldCode, fieldValue]) => ({ fieldCode, fieldValue }));
  }
  return [];
}

/**
 * 归一化背景噪声配置，兼容多种存储格式：
 * - 标准 ID 格式：{audioId, spl, deviceIds, loop}
 * - 统一标注文件格式：{audioName:"文件名.wav", spl, playbackDeviceNames:["设备名1","设备名2"]}
 * - 旧单设备格式：{audioName:"文件名.wav", spl, playbackDeviceName:"设备名"}
 * 输出统一为 {audioId, audioName, spl, deviceIds, deviceNames, loop, audio(文件名)}
 */
export function normalizeBackgroundNoise(bg: any) {
  if (!bg || typeof bg !== 'object') return undefined;
  const audioId = bg.audioId ?? '';
  const audioName = bg.audioName ?? '';
  const audioFile = typeof bg.audio === 'string' ? bg.audio : '';
  // 设备 ID 列表：优先 deviceIds，其次从设备名反查（由调用方注入 devNameToId）
  const deviceIds: string[] = Array.isArray(bg.deviceIds)
    ? bg.deviceIds.map(String)
    : [];
  // 设备名列表（统一标注文件格式）
  let deviceNames: string[] = [];
  if (Array.isArray(bg.playbackDeviceNames)) {
    deviceNames = bg.playbackDeviceNames;
  } else if (bg.playbackDeviceName) {
    deviceNames = [bg.playbackDeviceName];
  }
  return {
    audioId: String(audioId || ''),
    audioName: String(audioName || audioFile || ''),
    audio: audioFile, // 保留文件名（用于运行时解析或 UI 显示兜底）
    spl: bg.spl ?? null,
    deviceIds,
    deviceNames, // 保留设备名（用于 UI 显示兜底 / 反查 ID）
    loop: bg.loop ?? false,
  };
}

/** 用例配置归一化：rounds 架构 + 旧扁平 audios 兜底 */
export function normalizeTestCaseConfig(config: Record<string, any>) {
  const rawConfig = config || {};

  // ---- rounds-based format (new architecture) ----
  if (rawConfig.rounds && Array.isArray(rawConfig.rounds)) {
    // case 级背景噪声（rounds 外层），优先级高于轮次级
    const caseBgNoise = rawConfig.backgroundNoiseCase;

    const normalizedRounds = rawConfig.rounds.map((round: any) => {
      // 轮次级背景噪声：case 级存在时直接用 case 级（轮次级不播放）
      const roundBgSrc = caseBgNoise ?? round.backgroundNoise;
      // 归一化背景噪声：兼容 audioName(文件名) / playbackDeviceNames(设备名数组) / playbackDeviceName(单个)
      const bgNormalized = roundBgSrc ? normalizeBackgroundNoise(roundBgSrc) : undefined;

      return {
        roundNumber: round.roundNumber ?? 1,
        audios: Array.isArray(round.audios)
          ? round.audios.map((audio: any) => {
              const item: any = {
                audioId: audio?.audioId ?? '',
                playbackDeviceId: audio?.playbackDeviceId ?? '',
                spl: audio?.spl ?? 65,
                playOrder: audio?.playOrder ?? 0,
              };
              // 保留 segment 级背景噪声（归一化后）
              const segBg = audio?.backgroundNoise;
              if (segBg) {
                item.backgroundNoise = normalizeBackgroundNoise(segBg);
              }
              // 保留 segment 级干扰人原值（交由 InterfererConfigEditor 兼容）
              if (Array.isArray(audio?.interferers) && audio.interferers.length > 0) {
                item.interferers = audio.interferers;
              }
              return item;
            })
          : [],
        backgroundNoise: bgNormalized,
        evaluation: round.evaluation ?? undefined,
        algorithmParams: Array.isArray(round.algorithmParams)
          ? round.algorithmParams.map((p: any) => ({
              fieldCode: p.fieldCode ?? '',
              fieldValue: p.fieldValue ?? null,
            }))
          : [],
        referenceParamsPath: round.referenceParamsPath ?? '',
      };
    });

    const rawDimensions = rawConfig.dimensions;
    const normalizedDimensions = Array.isArray(rawDimensions)
      ? rawDimensions
      : (rawDimensions?.dimensions ?? []);

    const result: Record<string, any> = {
      rounds: normalizedRounds,
      dimensions: normalizedDimensions || [],
      // case 级背景噪声也写入顶层（供 syncStructuredFields / 后端保存时使用）
      backgroundNoiseCase: caseBgNoise,
    };
    // 透传顶层非结构化字段（recordMode / voiceprintConfig 等）
    for (const [k, v] of Object.entries(rawConfig)) {
      if (!(k in result) && k !== 'rounds' && k !== 'dimensions' && k !== 'audios' && k !== 'backgroundNoise' && k !== 'backgroundNoiseCase') {
        result[k] = v;
      }
    }
    return result;
  }

  // ---- legacy flat format fallback (audios + backgroundNoise) ----
  const rawBackgroundNoise =
    rawConfig.backgroundNoise ??
    (rawConfig.backgroundNoiseCase ? normalizeBackgroundNoise(rawConfig.backgroundNoiseCase) : undefined);

  const rawAudios: any[] = Array.isArray(rawConfig.audios) ? rawConfig.audios : [];
  const normalizedAudios = rawAudios.map((audio) => ({
    audioId: audio?.audioId ?? '',
    playbackDeviceId: audio?.playbackDeviceId ?? null,
    spl: audio?.spl ?? 65,
    playOrder: audio?.playOrder ?? 0,
  }));

  // Convert legacy flat audios into rounds grouped by testType
  const apiAudios = normalizedAudios.filter((a: any) => (a.testType ?? TestType.API) === TestType.API);
  const e2eAudios = normalizedAudios.filter((a: any) => (a.testType) === TestType.E2E);
  const legacyRounds: any[] = [];
  if (apiAudios.length > 0) {
    legacyRounds.push({
      roundNumber: 1,
      audios: apiAudios.map((a, i) => ({ ...a, playOrder: i })),
    });
  }
  if (e2eAudios.length > 0) {
    legacyRounds.push({
      roundNumber: legacyRounds.length + 1,
      audios: e2eAudios.map((a, i) => ({ ...a, playOrder: i })),
      backgroundNoise: rawBackgroundNoise
        ? {
            audioId: rawBackgroundNoise.audioId ?? null,
            spl: rawBackgroundNoise.spl ?? null,
            deviceIds: rawBackgroundNoise.deviceIds ?? [],
            loop: false,
          }
        : undefined,
    });
  }
  if (legacyRounds.length === 0) {
    legacyRounds.push({ roundNumber: 1, audios: [] });
  }

  const rawDimensions = rawConfig.dimensions;
  const normalizedDimensions = Array.isArray(rawDimensions)
    ? rawDimensions
    : (rawDimensions?.dimensions ?? []);

  return {
    rounds: legacyRounds,
    dimensions: normalizedDimensions || [],
  };
}

/** 用例表单转提交载荷：config 归一化 + 算法参数/参考参数独立列分组 + snake_case */
export function convertTestCaseFormData(formData: TestCaseFormData): Record<string, any> {
  const convertedData = {...formData};

  if (convertedData.config) {
    convertedData.config = normalizeTestCaseConfig(convertedData.config);
  }

  // ---- 算法参数独立列：按轮分组 [{roundNumber, params:[{fieldCode, fieldValue}]}] ----
  // 优先使用顶层 algorithmParams 独立列；若为空，则从 config.rounds[].algorithmParams 兼容提取
  let groupedAlgParams: any[] = Array.isArray((convertedData as any).algorithmParams)
    ? (convertedData as any).algorithmParams
    : [];

  // 兼容旧格式：如果顶层是 algorithmParams（对象或数组），归一化后合并
  if ((convertedData as any).algorithmParams) {
    const rawAlgParams = (convertedData as any).algorithmParams;
    if (!Array.isArray(rawAlgParams) && typeof rawAlgParams === 'object') {
      // 对象格式 → 单轮 params
      const params = Object.entries(rawAlgParams).map(([key, value]) => ({
        fieldCode: key,
        fieldValue: value,
      }));
      groupedAlgParams = [{ roundNumber: 1, params }];
    }
    delete (convertedData as any).algorithmParams;
  }

  // 从 config.rounds 兼容提取（子组件编辑期间仍写入 round.algorithmParams）
  const rounds = (convertedData.config as any)?.rounds;
  if (Array.isArray(rounds)) {
    for (const round of rounds) {
      const rn = round.roundNumber ?? 1;
      const existing = groupedAlgParams.find((e: any) => e.roundNumber === rn);
      if (round.algorithmParams && Array.isArray(round.algorithmParams)) {
        if (existing) {
          // 独立列已有该轮数据，用 round 上的补充缺失的 fieldCode
          for (const p of round.algorithmParams) {
            if (!existing.params.find((ep: any) => ep.fieldCode === p.fieldCode)) {
              existing.params.push({ fieldCode: p.fieldCode, fieldValue: p.fieldValue });
            }
          }
        } else {
          groupedAlgParams.push({
            roundNumber: rn,
            params: round.algorithmParams.map((p: any) => ({
              fieldCode: p.fieldCode,
              fieldValue: p.fieldValue,
            })),
          });
        }
        // 新设计：round 不含算法参数，从 round 上移除
        delete round.algorithmParams;
      }
    }
  }
  (convertedData as any).algorithmParams = groupedAlgParams;

  // ---- 参考参数独立列：按轮分组 [{roundNumber, referenceParamsPath}] ----
  let groupedRefParams: any[] = Array.isArray((convertedData as any).referenceParams)
    ? (convertedData as any).referenceParams
    : [];

  // 兼容旧格式
  if ((convertedData as any).referenceParams) {
    const rawRefParams = (convertedData as any).referenceParams;
    if (!Array.isArray(rawRefParams) && typeof rawRefParams === 'object') {
      if (Object.keys(rawRefParams).length === 0) {
        delete (convertedData as any).referenceParams;
      } else {
        groupedRefParams = Object.entries(rawRefParams).map(([key, value]: [string, any]) => ({
          roundNumber: Number(key) || 1,
          referenceParamsPath: typeof value === 'string' ? value : (value?.referenceParamsPath ?? ''),
        }));
      }
    }
    delete (convertedData as any).referenceParams;
  }

  // 从 config.rounds 兼容提取 referenceParamsPath
  if (Array.isArray(rounds)) {
    for (const round of rounds) {
      const rn = round.roundNumber ?? 1;
      if (round.referenceParamsPath) {
        const existing = groupedRefParams.find((e: any) => e.roundNumber === rn);
        if (existing) {
          existing.referenceParamsPath = round.referenceParamsPath;
        } else {
          groupedRefParams.push({ roundNumber: rn, referenceParamsPath: round.referenceParamsPath });
        }
        delete round.referenceParamsPath;
      }
    }
  }
  if (groupedRefParams.length > 0) {
    (convertedData as any).referenceParams = groupedRefParams;
  } else {
    delete (convertedData as any).referenceParams;
  }

  return snakifyKeys(convertedData);
}