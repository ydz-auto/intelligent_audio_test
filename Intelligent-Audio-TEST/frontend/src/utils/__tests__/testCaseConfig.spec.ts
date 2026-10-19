/**
 * testCaseConfig.convertTestCaseFormData 单元测试 —— 算法参数独立列按轮分组契约
 * 锁定用例编辑模态窗保存路径：grouped 数组整体透传（第 2+ 轮不丢），
 * 顶层扁平对象按旧格式归并为第 1 轮（与后端 testcase_crud_service 归一化口径一致）
 *
 * INT-972：convertTestCaseFormData 输出 camelCase Domain 草稿；snake_case wire 由
 * adapter 的 toTestCaseUpsertDto 在 testcasesApi.create/update 出口转换（DDD §3.1）。
 * 本测试经 toTestCaseUpsertDto 核对落库 wire 形状。
 */
import { describe, it, expect } from 'vitest'
import { convertTestCaseFormData } from '../testCaseConfig'
import { toTestCaseUpsertDto } from '../../infrastructure/adapters/testCaseAdapter'

const twoRoundPayload = {
  id: 'c1',
  name: '两轮用例',
  group: '默认分组',
  algorithmType: 'qwen_ast',
  config: {
    rounds: [
      { roundNumber: 1, audios: [{ audioId: 'a1', playbackDeviceId: 'd1', spl: 65, playOrder: 0 }] },
      { roundNumber: 2, audios: [{ audioId: 'a2', playbackDeviceId: 'd2', spl: 70, playOrder: 0 }] },
    ],
    dimensions: [],
  },
  algorithmParams: [
    { roundNumber: 1, params: [{ fieldCode: 'threshold', fieldValue: 0.5 }] },
    { roundNumber: 2, params: [{ fieldCode: 'threshold', fieldValue: 0.8 }] },
  ],
} as any

describe('convertTestCaseFormData · algorithmParams 独立列', () => {
  it('按轮分组数组整体透传：第 2+ 轮参数保留', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData(twoRoundPayload))
    const col = (out as any).algorithm_params
    expect(Array.isArray(col)).toBe(true)
    expect(col).toHaveLength(2)
    expect(col[0].round_number).toBe(1)
    expect(col[0].params).toEqual([{ field_code: 'threshold', field_value: 0.5 }])
    expect(col[1].round_number).toBe(2)
    expect(col[1].params).toEqual([{ field_code: 'threshold', field_value: 0.8 }])
  })

  it('编辑保存后 config.rounds 第 2+ 轮结构保留（后端整体替换语义下不缺轮）', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData(twoRoundPayload))
    expect((out as any).config.rounds).toHaveLength(2)
    expect((out as any).config.rounds[1].round_number).toBe(2)
    expect((out as any).config.rounds[1].audios[0].audio_id).toBe('a2')
  })

  it('顶层扁平对象（旧格式）归并为第 1 轮 params', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData({
      name: 'x',
      group: 'g',
      config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
      algorithmParams: { threshold: 0.5 },
    } as any))
    expect((out as any).algorithm_params).toEqual([
      { round_number: 1, params: [{ field_code: 'threshold', field_value: 0.5 }] },
    ])
  })

  it('round.algorithmParams 兼容字段合并进独立列（子组件编辑期间写入）', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData({
      name: 'x',
      group: 'g',
      config: {
        rounds: [
          { roundNumber: 1, audios: [], algorithmParams: [{ fieldCode: 'k1', fieldValue: 'v1' }] },
        ],
        dimensions: [],
      },
    } as any))
    expect((out as any).algorithm_params).toEqual([
      { round_number: 1, params: [{ field_code: 'k1', field_value: 'v1' }] },
    ])
  })
})

describe('toTestCaseUpsertDto · 分组归属（INT-972 P1 回归）', () => {
  it('groupId 存在时优先映射 group_id，不透传 group 名', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData({
      name: 'x',
      group: '默认分组',
      groupId: 'g1_id',
      config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    } as any))
    expect((out as any).group_id).toBe('g1_id')
    expect((out as any).group).toBeUndefined()
  })

  it('新建分组流：groupId 缺失时回退 group 名交后端解析/自动建组（不再丢分组导致 400）', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData({
      name: 'x',
      group: '新组名',
      createNewGroup: true,
      config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    } as any))
    expect((out as any).group_id).toBeUndefined()
    expect((out as any).group).toBe('新组名')
  })

  it('groupId 为空串视为缺失，同样回退 group 名', () => {
    const out = toTestCaseUpsertDto(convertTestCaseFormData({
      name: 'x',
      group: '新组名',
      groupId: '',
      config: { rounds: [{ roundNumber: 1, audios: [] }], dimensions: [] },
    } as any))
    expect((out as any).group_id).toBeUndefined()
    expect((out as any).group).toBe('新组名')
  })
})
