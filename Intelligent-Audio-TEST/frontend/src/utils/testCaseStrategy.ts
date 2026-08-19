/**
 * 测试用例分组策略（策略模式）
 *
 * 支持同一文件夹下平铺多个 JSON，每个 JSON 各自定义一个独立用例。
 * JSON 通过 segment.audio 字段引用音频，未被任何 JSON 引用的音频回退到 folderParser 兜底。
 *
 * 4 种 use case：
 * 1. rounds 多轮 JSON  — { rounds: [{ round_number, segments: [{ audio, ... }] }] }
 * 2. flat 单轮 JSON     — 顶层直接是 segment 字段 { audio, query, spl, ... }
 * 3. txt 数组单轮 JSON  — { txt: [{ audio, query, ... }] }
 * 4. 纯音频无 JSON      — folderParser.buildRoundsConfig 兜底
 */

import type { RoundConfig, RoundAudioConfig } from './folderParser';

// 策略统一输出
export interface TestCaseGroup {
  /** 分组键：JSON 文件名去扩展名 */
  groupKey: string;
  /** 轮次配置 */
  rounds: RoundConfig[];
  /** case 级背景噪声（rounds 外层） */
  backgroundNoise?: any;
  /** 该 JSON 引用的所有音频文件名（用于音频匹配） */
  audioNames: string[];
}

// 策略接口
interface TestCaseStrategy {
  /** 判断该 JSON 是否匹配此策略 */
  matches(rawJson: any): boolean;
  /** 构建 TestCaseGroup */
  build(rawJson: any, annFileBaseKey: string): TestCaseGroup;
}

// ──────────────────────────────────────────────
// 策略 1：rounds 多轮 JSON
// ──────────────────────────────────────────────
class RoundsJsonStrategy implements TestCaseStrategy {
  matches(rawJson: any): boolean {
    return !!(rawJson && Array.isArray(rawJson.rounds));
  }

  build(rawJson: any, annFileBaseKey: string): TestCaseGroup {
    const audioNames: string[] = [];
    const rounds: RoundConfig[] = (rawJson.rounds as any[])
      .map((round: any, ri: number) => {
        if (!round || !Array.isArray(round.segments)) return null;
        const audios: RoundAudioConfig[] = round.segments
          .filter((seg: any) => seg && typeof seg === 'object')
          .map((seg: any, idx: number) => {
            const audioName = seg.audio || seg.audio_name || seg.audioName || '';
            if (audioName) audioNames.push(audioName);
            const cfg: any = { audio_name: audioName, play_order: idx };
            if (seg.spl != null && seg.spl !== '') cfg.spl = Number(seg.spl);
            if (seg.playback_device_name || seg.playbackDeviceName) {
              cfg.playback_device_name = seg.playback_device_name || seg.playbackDeviceName;
            }
            // interferers 不在此硬编码透传，由 extractParamsFromAnnotations 配置化提取到 algorithm_params
            // background_noise 是结构性字段，保留在 rounds 中
            if (seg.background_noise) {
              cfg.background_noise = seg.background_noise;
            }
            // 收集 background_noise.audio（用于音频分组匹配）
            const segBgAudio = seg.background_noise?.audio || seg.background_noise?.audio_name || seg.background_noise?.audioName || '';
            if (segBgAudio) audioNames.push(segBgAudio);
            // 收集 interferers[].audio（用于音频分组匹配）
            if (Array.isArray(seg.interferers)) {
              for (const interf of seg.interferers) {
                if (!interf) continue;
                const interfAudio = interf.audio || interf.audio_name || interf.audioName || '';
                if (interfAudio) audioNames.push(interfAudio);
              }
            }
            return cfg;
          });
        const roundObj: any = {
          roundNumber: round.round_number || round.roundNumber || ri + 1,
          audios,
        };
        if (round.background_noise) {
          roundObj.background_noise = round.background_noise;
          // 收集 round 级 background_noise.audio
          const roundBgAudio = round.background_noise?.audio || round.background_noise?.audio_name || round.background_noise?.audioName || '';
          if (roundBgAudio) audioNames.push(roundBgAudio);
        }
        return roundObj;
      })
      .filter((r: any) => r !== null);

    // 收集 case 级 background_noise.audio
    if (rawJson.background_noise) {
      const caseBgAudio = rawJson.background_noise.audio || rawJson.background_noise.audio_name || rawJson.background_noise.audioName || '';
      if (caseBgAudio) audioNames.push(caseBgAudio);
    }

    const groupKey = extractFileNameWithoutExt(annFileBaseKey);
    return {
      groupKey,
      rounds,
      backgroundNoise: rawJson.background_noise,
      audioNames,
    };
  }
}

// ──────────────────────────────────────────────
// 策略 2：flat 单轮 JSON（顶层直接是 segment 字段）
// ──────────────────────────────────────────────
class FlatJsonStrategy implements TestCaseStrategy {
  matches(rawJson: any): boolean {
    if (!rawJson || typeof rawJson !== 'object') return false;
    if (Array.isArray(rawJson.rounds)) return false;
    if (Array.isArray(rawJson.txt)) return false;
    if (Array.isArray(rawJson.annotations)) return false;
    // 必须有 audio 字段才算 flat 用例 JSON
    return !!(rawJson.audio || rawJson.audio_name || rawJson.audioName);
  }

  build(rawJson: any, annFileBaseKey: string): TestCaseGroup {
    const audioNames: string[] = [];
    const audioName = rawJson.audio || rawJson.audio_name || rawJson.audioName || '';
    if (audioName) audioNames.push(audioName);
    const cfg: any = { audio_name: audioName, play_order: 0 };
    if (rawJson.spl != null && rawJson.spl !== '') cfg.spl = Number(rawJson.spl);
    if (rawJson.playback_device_name || rawJson.playbackDeviceName) {
      cfg.playback_device_name = rawJson.playback_device_name || rawJson.playbackDeviceName;
    }
    // interferers 不硬编码到 cfg，由 extractParamsFromAnnotations 配置化提取到 algorithm_params
    if (rawJson.background_noise) {
      cfg.background_noise = rawJson.background_noise;
    }
    // 收集 background_noise.audio（用于音频分组匹配）
    const bgAudio = rawJson.background_noise?.audio || rawJson.background_noise?.audio_name || rawJson.background_noise?.audioName || '';
    if (bgAudio) audioNames.push(bgAudio);
    // 收集 interferers[].audio（用于音频分组匹配）
    if (Array.isArray(rawJson.interferers)) {
      for (const interf of rawJson.interferers) {
        if (!interf) continue;
        const interfAudio = interf.audio || interf.audio_name || interf.audioName || '';
        if (interfAudio) audioNames.push(interfAudio);
      }
    }

    const groupKey = extractFileNameWithoutExt(annFileBaseKey);
    return {
      groupKey,
      rounds: [{ roundNumber: 1, audios: [cfg] }],
      backgroundNoise: undefined,
      audioNames,
    };
  }
}

// ──────────────────────────────────────────────
// 策略 3：txt 数组单轮 JSON（{ txt: [{ audio, query, ... }] }）
// ──────────────────────────────────────────────
class TxtArrayJsonStrategy implements TestCaseStrategy {
  matches(rawJson: any): boolean {
    return !!(rawJson && Array.isArray(rawJson.txt) && rawJson.txt.length > 0);
  }

  build(rawJson: any, annFileBaseKey: string): TestCaseGroup {
    const audioNames: string[] = [];
    const audios: RoundAudioConfig[] = rawJson.txt
      .filter((item: any) => item && typeof item === 'object')
      .map((item: any, idx: number) => {
        const audioName = item.audio || item.audio_name || item.audioName || '';
        if (audioName) audioNames.push(audioName);
        const cfg: any = { audio_name: audioName, play_order: idx };
        if (item.spl != null && item.spl !== '') cfg.spl = Number(item.spl);
        if (item.playback_device_name || item.playbackDeviceName) {
          cfg.playback_device_name = item.playback_device_name || item.playbackDeviceName;
        }
        // interferers 不在此硬编码透传，由 extractParamsFromAnnotations 配置化提取到 algorithm_params
        // background_noise 是结构性字段，保留在 rounds 中
        if (item.background_noise) {
          cfg.background_noise = item.background_noise;
        }
        // 收集 background_noise.audio（用于音频分组匹配）
        const itemBgAudio = item.background_noise?.audio || item.background_noise?.audio_name || item.background_noise?.audioName || '';
        if (itemBgAudio) audioNames.push(itemBgAudio);
        // 收集 interferers[].audio（用于音频分组匹配）
        if (Array.isArray(item.interferers)) {
          for (const interf of item.interferers) {
            if (!interf) continue;
            const interfAudio = interf.audio || interf.audio_name || interf.audioName || '';
            if (interfAudio) audioNames.push(interfAudio);
          }
        }
        return cfg;
      });

    // 收集 case 级 background_noise.audio
    if (rawJson.background_noise) {
      const caseBgAudio = rawJson.background_noise.audio || rawJson.background_noise.audio_name || rawJson.background_noise.audioName || '';
      if (caseBgAudio) audioNames.push(caseBgAudio);
    }

    const groupKey = extractFileNameWithoutExt(annFileBaseKey);
    return {
      groupKey,
      rounds: [{ roundNumber: 1, audios }],
      backgroundNoise: rawJson.background_noise,
      audioNames,
    };
  }
}

// ──────────────────────────────────────────────
// 策略注册表 + 工厂
// ──────────────────────────────────────────────
const strategies: TestCaseStrategy[] = [
  new RoundsJsonStrategy(),
  new FlatJsonStrategy(),
  new TxtArrayJsonStrategy(),
];

/**
 * 按 JSON 内容选择策略
 */
function selectStrategy(rawJson: any): TestCaseStrategy | null {
  return strategies.find(s => s.matches(rawJson)) || null;
}

/**
 * 从路径中提取文件名（去扩展名，去目录前缀）
 */
function extractFileNameWithoutExt(baseKey: string): string {
  const parts = baseKey.split('/').filter(Boolean);
  const last = parts[parts.length - 1] || baseKey;
  return last.replace(/\.[^.]+$/, '');
}

// ──────────────────────────────────────────────
// 统一入口
// ──────────────────────────────────────────────

/**
 * 解析所有 JSON 标注文件，构建测试用例分组。
 * 每个 JSON 产生一个独立的 TestCaseGroup，分组键 = JSON 文件名去扩展名。
 *
 * @param annFiles - JSON 标注文件数组（File 对象）
 * @returns Map<groupKey, TestCaseGroup>
 */
export async function buildTestCaseGroups(
  annFiles: File[]
): Promise<Map<string, TestCaseGroup>> {
  const groups = new Map<string, TestCaseGroup>();

  for (const annFile of annFiles) {
    try {
      const content = await readFileAsText(annFile);
      const rawJson = JSON.parse(content);
      const strategy = selectStrategy(rawJson);
      if (!strategy) continue;

      const key = (annFile as any).webkitRelativePath || annFile.name;
      const baseKey = key.substring(0, key.lastIndexOf('.')) || key;
      const group = strategy.build(rawJson, baseKey);

      if (group.rounds.length > 0 && group.groupKey) {
        groups.set(group.groupKey, group);
      }
    } catch (e) {
      console.error(`解析用例 JSON ${annFile.name} 失败:`, e);
    }
  }

  return groups;
}

/**
 * 将音频文件按测试用例分组：
 * 1. 被 JSON 引用的音频 → 归入对应 JSON 的 groupKey
 * 2. 未被任何 JSON 引用的音频 → 回退按文件名分组（folderParser 兜底）
 *
 * @param audioFiles - 所有音频文件信息
 * @param testCaseGroups - buildTestCaseGroups 的输出
 * @returns Map<groupKey, AudioFileInfo[]> 音频分组
 */
export function groupAudiosByTestCase(
  audioFiles: import('./folderParser').AudioFileInfo[],
  testCaseGroups: Map<string, TestCaseGroup>
): Map<string, import('./folderParser').AudioFileInfo[]> {
  // 构建 audioName → groupKey 的反向映射
  const audioNameToGroupKey = new Map<string, string>();
  for (const [groupKey, group] of testCaseGroups) {
    for (const audioName of group.audioNames) {
      // 存文件名（去路径去扩展名）和完整文件名两种形式
      const fileNameOnly = audioName.split('/').pop() || audioName;
      audioNameToGroupKey.set(fileNameOnly, groupKey);
      audioNameToGroupKey.set(audioName, groupKey);
    }
  }

  const result = new Map<string, import('./folderParser').AudioFileInfo[]>();
  const matchedAudioNames = new Set<string>();

  for (const audio of audioFiles) {
    // 先按完整文件名匹配
    let groupKey = audioNameToGroupKey.get(audio.name);
    if (!groupKey) {
      // 再按去扩展名匹配
      const nameWithoutExt = audio.name.replace(/\.[^.]+$/, '');
      groupKey = audioNameToGroupKey.get(nameWithoutExt);
    }

    if (groupKey) {
      matchedAudioNames.add(audio.name);
      if (!result.has(groupKey)) {
        result.set(groupKey, []);
      }
      result.get(groupKey)!.push(audio);
    } else {
      // 未被 JSON 引用 → 回退按文件名去扩展名分组
      const fallbackKey = audio.name.replace(/\.[^.]+$/, '');
      if (!result.has(fallbackKey)) {
        result.set(fallbackKey, []);
      }
      result.get(fallbackKey)!.push(audio);
    }
  }

  return result;
}

/**
 * 为单个音频文件计算其所属的分组键。
 * 优先匹配 JSON 引用，未匹配则回退文件名去扩展名。
 */
export function computeGroupKeyForAudio(
  audioName: string,
  audioRelativePath: string,
  testCaseGroups: Map<string, TestCaseGroup>
): string {
  // 先按完整文件名匹配
  let groupKey: string | undefined;
  for (const [gk, group] of testCaseGroups) {
    if (group.audioNames.includes(audioName)) {
      return gk;
    }
    // 也尝试去扩展名匹配
    const nameWithoutExt = audioName.replace(/\.[^.]+$/, '');
    const audioNamesWithoutExt = group.audioNames.map(n => n.replace(/\.[^.]+$/, ''));
    if (audioNamesWithoutExt.includes(nameWithoutExt)) {
      return gk;
    }
  }
  // 回退：文件名去扩展名
  return audioName.replace(/\.[^.]+$/, '');
}

// ──────────────────────────────────────────────
// 工具
// ──────────────────────────────────────────────

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target?.result as string);
    reader.onerror = reject;
    reader.readAsText(file);
  });
}
