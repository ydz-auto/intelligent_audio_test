/**
 * 上传前音频内容预检单测（INT-2192）：
 * 0 字节 / 非音频内容（文本改名 .wav）在提交前被拦下并给出逐条原因；
 * 探针未知（null / 超时 / 环境不支持）放行交后端；结果保持选择顺序。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  isAudioFile,
  probeAudioDuration,
  validateAudioFile,
  validateAudioFiles,
} from '@/features/audio-import/lib/audio-file-validation'

function wav(name: string, bytes = 44): File {
  return new File([new Uint8Array(bytes)], name, { type: 'audio/wav' })
}

describe('isAudioFile', () => {
  it('按扩展名识别，大小写不敏感', () => {
    expect(isAudioFile('a.WAV')).toBe(true)
    expect(isAudioFile('b.mp3')).toBe(true)
    expect(isAudioFile('c.flac')).toBe(true)
    expect(isAudioFile('d.txt')).toBe(false)
    expect(isAudioFile('e.wav.json')).toBe(false)
  })
})

describe('validateAudioFile（单文件）', () => {
  it('0 字节文件直接判失败，不调用探针', async () => {
    const probe = vi.fn()
    const error = await validateAudioFile(new File([], 'empty.wav'), probe)
    expect(error).toBe('文件为空（0 字节），已跳过')
    expect(probe).not.toHaveBeenCalled()
  })

  it('探针解析出正常时长 → 通过', async () => {
    const error = await validateAudioFile(wav('ok.wav'), () => Promise.resolve(2.5))
    expect(error).toBeNull()
  })

  it('探针解析出 duration=0 → 判损坏', async () => {
    const error = await validateAudioFile(wav('zero.wav'), () => Promise.resolve(0))
    expect(error).toBe('音频时长为 0，文件可能已损坏，已跳过')
  })

  it('探针报错（文本改名 .wav）→ 透传可读原因', async () => {
    const error = await validateAudioFile(wav('fake.wav'), () =>
      Promise.reject(new Error('文件内容不是可解析的音频文件'))
    )
    expect(error).toBe('文件内容不是可解析的音频文件')
  })

  it('探针抛非 Error → 回退通用原因', async () => {
    const error = await validateAudioFile(wav('odd.wav'), () =>
      Promise.reject('boom' as unknown as Error)
    )
    expect(error).toBe('无法解析为音频文件，已跳过')
  })

  it('探针未知（null，环境不支持/容器未给时长）→ 放行，交后端兜底', async () => {
    const error = await validateAudioFile(wav('unknown.wav'), () => Promise.resolve(null))
    expect(error).toBeNull()
  })
})

describe('validateAudioFiles（批量）', () => {
  it('按选择顺序拆分 valid / invalid，逐条带原因', async () => {
    const ok1 = wav('ok1.wav')
    const empty = new File([], 'empty.wav')
    const fake = wav('fake.wav')
    const ok2 = wav('ok2.wav')
    const { valid, invalid } = await validateAudioFiles(
      [ok1, empty, fake, ok2],
      (file) =>
        file === fake
          ? Promise.reject(new Error('文件内容不是可解析的音频文件'))
          : Promise.resolve(1.5)
    )
    expect(valid).toEqual([ok1, ok2])
    expect(invalid).toEqual([
      { name: 'empty.wav', error: '文件为空（0 字节），已跳过' },
      { name: 'fake.wav', error: '文件内容不是可解析的音频文件' },
    ])
  })

  it('空列表返回空结果', async () => {
    await expect(validateAudioFiles([], () => Promise.resolve(1))).resolves.toEqual({
      valid: [],
      invalid: [],
    })
  })
})

describe('probeAudioDuration（浏览器探针降级）', () => {
  it('超时按未知放行（不误杀），返回 null', async () => {
    await expect(probeAudioDuration(wav('slow.wav'), 0)).resolves.toBeNull()
  })
})
