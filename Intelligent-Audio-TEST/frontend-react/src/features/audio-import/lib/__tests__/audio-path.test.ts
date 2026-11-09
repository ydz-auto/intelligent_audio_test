import { describe, expect, it } from 'vitest'

import { audioRelativePath, inAudioFolder } from '@/features/audio-import/lib/audio-path'

describe('audioRelativePath', () => {
  it('oss:// 形态取 /audios/ 之后段', () => {
    expect(audioRelativePath('oss://audios/direct/x.wav')).toBe('direct/x.wav')
  })

  it('Windows 绝对路径形态取 /audios/ 之后段（含反斜杠归一化）', () => {
    expect(audioRelativePath('D:/00_static/static/audios/环境理解/子目录/x.wav')).toBe(
      '环境理解/子目录/x.wav'
    )
    expect(audioRelativePath('D:\\00_static\\static\\audios\\direct\\x.wav')).toBe(
      'direct/x.wav'
    )
  })

  it('已是相对路径时原样返回', () => {
    expect(audioRelativePath('direct/x.wav')).toBe('direct/x.wav')
  })

  it('空输入返回空串', () => {
    expect(audioRelativePath(null)).toBe('')
    expect(audioRelativePath(undefined)).toBe('')
    expect(audioRelativePath('')).toBe('')
  })
})

describe('inAudioFolder', () => {
  it('命中文件夹内文件（oss:// 形态）', () => {
    expect(inAudioFolder('oss://audios/direct/x.wav', 'direct')).toBe(true)
  })

  it('命中嵌套文件夹内文件（绝对路径形态）', () => {
    expect(
      inAudioFolder('D:/00_static/static/audios/环境理解/子目录/x.wav', '环境理解/子目录')
    ).toBe(true)
  })

  it('同前缀兄弟文件夹不串档：dir 不匹配 dir2', () => {
    expect(inAudioFolder('oss://audios/dir2/x.wav', 'dir')).toBe(false)
  })

  it('其他文件夹文件不命中', () => {
    expect(inAudioFolder('oss://audios/other/x.wav', 'direct')).toBe(false)
  })

  it('folder 为空串时不命中', () => {
    expect(inAudioFolder('oss://audios/direct/x.wav', '')).toBe(false)
  })

  it('filePath 为空时不命中', () => {
    expect(inAudioFolder(null, 'direct')).toBe(false)
  })
})
