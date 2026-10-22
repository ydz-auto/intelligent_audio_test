import { describe, it, expect } from 'vitest';
import { sampleRateToKHz, normalizeSampleRate } from '../useFolderTree';

/**
 * INT-1331 回归守卫：采样率筛选请求载荷必须为 kHz 口径。
 *
 * 后端 apply_audio_list_filters 按 kHz 解析（float(str(sample_rate).split()[0]) * 1000），
 * 前端筛选态与客户端过滤仍为 Hz（44100），列表请求载荷须由 sampleRateToKHz 换算为 kHz。
 * 若回归为 Hz 下发（"44100"），后端会算成 44100000 → 列表空态。
 */
describe('sampleRateToKHz（INT-1331 采样率筛选载荷 kHz 口径）', () => {
  it('Hz 整数值 → kHz 字符串', () => {
    expect(sampleRateToKHz('44100')).toBe('44.1');
    expect(sampleRateToKHz('48000')).toBe('48');
    expect(sampleRateToKHz('96000')).toBe('96');
    expect(sampleRateToKHz('16000')).toBe('16');
    expect(sampleRateToKHz('8000')).toBe('8');
  });

  it('kHz 标注（下拉 label 形态）→ 直接取数字', () => {
    expect(sampleRateToKHz('44.1 kHz')).toBe('44.1');
    expect(sampleRateToKHz('48 kHz')).toBe('48');
    expect(sampleRateToKHz('48k')).toBe('48');
  });

  it('与 normalizeSampleRate 组合结果一致（筛选态 Hz → 载荷 kHz）', () => {
    // 下拉选项值为 Hz（'44100'），normalizeSampleRate 保持 Hz 用于客户端过滤
    expect(normalizeSampleRate('44.1 kHz')).toBe('44100');
    // 同一筛选值换算为请求载荷必须为 kHz
    expect(sampleRateToKHz(normalizeSampleRate('44.1 kHz'))).toBe('44.1');
  });

  it('空值 / all 返回 null', () => {
    expect(sampleRateToKHz(undefined)).toBeNull();
    expect(sampleRateToKHz(null)).toBeNull();
    expect(sampleRateToKHz('all')).toBeNull();
    expect(sampleRateToKHz('')).toBeNull();
  });
});
