import { describe, expect, it } from 'vitest'

import { inferBodyTemplate, inferResponseParser } from '@/domain/models/sampleInference'

describe('样例 JSON 推断（纯前端）', () => {
  it('响应样例 → result_parser 路径（浅层优先）', () => {
    const { parserText, fields } = inferResponseParser(
      JSON.stringify({
        type: 'response.audio_transcript.delta',
        session_id: 's-1',
        data: { transcript: 'hello', translation: '你好' },
      })
    )
    expect(JSON.parse(parserText)).toEqual({
      asr_text_path: 'data.transcript',
      trans_text_path: 'data.translation',
      session_id_path: 'session_id',
    })
    expect(fields.map((field) => field.code)).toContain('asr_text')
  })

  it('响应样例没有文本字段 → 抛错（不静默生成空模板）', () => {
    expect(() => inferResponseParser('{"code":0}')).toThrow(/没识别出文本字段/)
  })

  it('请求样例 → body_template，并把 base64 音频替换成占位符', () => {
    const audio = 'A'.repeat(400)
    const { templateText, audioPath } = inferBodyTemplate(
      JSON.stringify({ type: 'input_audio_buffer.append', audio })
    )
    expect(audioPath).toBe('audio')
    expect(JSON.parse(templateText)).toEqual({
      type: 'input_audio_buffer.append',
      audio: '{{audio_b64}}',
    })
  })

  it('非法 JSON → 明确报错', () => {
    expect(() => inferBodyTemplate('{bad json')).toThrow(/不是合法 JSON/)
  })
})
