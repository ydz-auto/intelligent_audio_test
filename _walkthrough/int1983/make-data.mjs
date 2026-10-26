/**
 * INT-1983 走查数据生成：极简合法 WAV（16-bit PCM / 8kHz / 单声道 / 0.5s 静音）
 * 只写本 run 的测试数据，放在 worktree 的 _walkthrough/int1983 下，收尾删除。
 */
import { writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

function wavBuffer(seconds = 0.5, sampleRate = 8000, freq = 440) {
  const numSamples = Math.floor(seconds * sampleRate)
  const dataSize = numSamples * 2
  const buf = Buffer.alloc(44 + dataSize)
  buf.write('RIFF', 0)
  buf.writeUInt32LE(36 + dataSize, 4)
  buf.write('WAVE', 8)
  buf.write('fmt ', 12)
  buf.writeUInt32LE(16, 16)       // fmt chunk size
  buf.writeUInt16LE(1, 20)        // PCM
  buf.writeUInt16LE(1, 22)        // mono
  buf.writeUInt32LE(sampleRate, 24)
  buf.writeUInt32LE(sampleRate * 2, 28) // byte rate
  buf.writeUInt16LE(2, 32)        // block align
  buf.writeUInt16LE(16, 34)       // bits per sample
  buf.write('data', 36)
  buf.writeUInt32LE(dataSize, 40)
  // 低频正弦，避免全零被当成空文件
  for (let i = 0; i < numSamples; i++) {
    const v = Math.round(Math.sin((2 * Math.PI * freq * i) / sampleRate) * 3000)
    buf.writeInt16LE(v, 44 + i * 2)
  }
  return buf
}

const targets = [
  ['data/接线测试_组1/子目录/接线测试_c1.wav', 'data/接线测试_组1/子目录/接线测试_case1.json', 440, {
    rounds: [{ roundNumber: 1, segments: [{ audioName: '接线测试_c1.wav', query: '组1查询' }] }],
    tags: ['JSON标签1', '共同标签'],
  }],
  ['data/接线测试_组2/子目录/接线测试_c2.wav', 'data/接线测试_组2/子目录/接线测试_case2.json', 660, {
    audioName: '接线测试_c2.wav',
    tags: ['JSON标签2', '共同标签'],
  }],
  // B4（仅路径解析）/ B5（仅 JSON tags）各用独立音频，避免与 B3 同 md5 触发秒传而拿不到 merge 载荷
  ['data/接线测试_组3/子目录/接线测试_c3.wav', 'data/接线测试_组3/子目录/接线测试_case3.json', 880, {
    audioName: '接线测试_c3.wav',
    tags: ['JSON标签3', '共同标签'],
  }],
  ['data/接线测试_组4/子目录/接线测试_c4.wav', 'data/接线测试_组4/子目录/接线测试_case4.json', 990, {
    rounds: [{ roundNumber: 1, segments: [{ audioName: '接线测试_c4.wav', query: '组4查询' }] }],
    tags: ['JSON标签4', '共同标签'],
  }],
]

for (const [wavRel, jsonRel, freq, json] of targets) {
  const wavPath = join(__dirname, wavRel)
  mkdirSync(dirname(wavPath), { recursive: true })
  writeFileSync(wavPath, wavBuffer(0.5, 8000, freq))
  writeFileSync(join(__dirname, jsonRel), JSON.stringify(json, null, 2), 'utf8')
  console.log('[data] ' + wavRel)
  console.log('[data] ' + jsonRel)
}

// 单文件上传（B6/B8）用：3 个音频 + 1 个畸形 JSON（B8）；音高各异 → md5 不同，避免秒传
const singles = ['接线测试_s1.wav', '接线测试_s2.wav', '接线测试_s3.wav']
singles.forEach((name, i) => {
  const p = join(__dirname, 'data/接线测试_单文件', name)
  mkdirSync(dirname(p), { recursive: true })
  writeFileSync(p, wavBuffer(0.5, 8000, 520 + i * 90))
  console.log('[data] ' + name)
})

// 畸形 JSON 目录（B8：JSON 畸形 → 提示正常，无未捕获异常）
const badDir = join(__dirname, 'data/接线测试_畸形JSON/子目录')
mkdirSync(badDir, { recursive: true })
writeFileSync(join(badDir, '接线测试_bad.wav'), wavBuffer())
writeFileSync(join(badDir, '接线测试_bad.json'), '{"rounds":[{"roundNumber":1,"segments":[', 'utf8')
console.log('[data] 接线测试_畸形JSON')
