/**
 * audioUtils —— 音量 / 分贝 / 线性增益换算
 *
 * 提供 volume↔db↔linear 的换算函数与增益曲线生成（原 audioUtils.ts 内 DB 换算分组）。
 */
import { DB_MIN, DB_MAX } from './audioUtils.constants';

export function volumeToDb(volume: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  if (volume < 0 || volume > 100) {
    console.warn(`[volumeToDb] 音量值 ${volume} 超出 0-100 范围，已裁剪`);
  }
  const clampedVolume = Math.max(0, Math.min(100, volume));
  return minDb + (clampedVolume / 100) * (maxDb - minDb);
}

export function dbToLinear(db: number): number {
  return Math.pow(10, db / 20);
}

export function volumeToLinear(volume: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  const targetDb = volumeToDb(volume, minDb, maxDb);
  return dbToLinear(targetDb);
}

export function linearToDb(linear: number): number {
  if (linear <= 0) return -Infinity;
  return 20 * Math.log10(linear);
}

export function dbToVolume(db: number, minDb: number = DB_MIN, maxDb: number = DB_MAX): number {
  const clampedDb = Math.max(minDb, Math.min(maxDb, db));
  return ((clampedDb - minDb) / (maxDb - minDb)) * 100;
}

export interface GainCurvePoint {
  volume: number;
  db: number;
  linear: number;
}

export function generateGainCurve(
  minDb: number = DB_MIN,
  maxDb: number = DB_MAX,
  steps: number = 101
): GainCurvePoint[] {
  const curve: GainCurvePoint[] = [];
  for (let i = 0; i < steps; i++) {
    const volume = (i / (steps - 1)) * 100;
    const db = volumeToDb(volume, minDb, maxDb);
    const linear = dbToLinear(db);
    curve.push({ volume, db, linear });
  }
  return curve;
}
