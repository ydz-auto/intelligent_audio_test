/**
 * 算法定义整体保存四列表键名契约测试（INT-210）
 * 覆盖：toAlgorithmDefinitionDto 深度转换 device_params / api_params / mappings /
 * associated_dimensions 列表项为 snake_case（后端 _update_params / _update_mappings /
 * _update_associated_dimensions 仅识别 snake_case 键，camelCase 透传会 200 假成功静默丢失，
 * mappings/维度关联还会写脏数据）、id 保留（后端以 id / dimension_id 对账既有行，未提交会被
 * 软删除）、前端态字段（tempId/paramName/dimensionName/optionsSource 及维度关联关系行 id）
 * 剔除、不完整新行跳过（空码参数/缺键值映射，blur 自动保存同样拒绝）、
 * updateDefinition 请求体 wire 契约。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { algorithmApi } from '../../api/algorithmApi';
import {
  toDeviceParamItemDto,
  toParamMappingItemDto,
  toAssociatedDimensionItemDto,
  toAlgorithmDefinitionDto,
} from '../algorithmAdapter';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('toDeviceParamItemDto（device_params/api_params 列表项）', () => {
  it('逐字段转 snake_case，保留 id，剔除前端态字段', () => {
    const item = toDeviceParamItemDto({
      id: 12,
      tempId: 'temp_3',
      algorithmType: 'voice_llm',
      paramCode: 'audio_channel',
      paramName: '声道',
      label: '声道数',
      paramType: 'number',
      direction: 'output',
      required: true,
      defaultValue: 2,
      optionsSource: 'device_api',
      optionsField: 'channels',
      optionsLabelField: 'name',
      helpText: '声道数量',
      uiOrder: 3,
      hidden: false,
    } as any);

    expect(item).toEqual({
      id: 12,
      param_code: 'audio_channel',
      param_name: '声道',
      label: '声道数',
      param_type: 'number',
      direction: 'output',
      required: true,
      default_value: 2,
      help_text: '声道数量',
      ui_order: 3,
      hidden: false,
    });
    expect(item!.tempId).toBeUndefined();
    expect(item!.algorithmType).toBeUndefined();
    expect(item!.optionsSource).toBeUndefined();
    expect(item!.optionsField).toBeUndefined();
    expect(item!.optionsLabelField).toBeUndefined();
  });

  it('required/hidden 为 false 的布尔字段不丢失', () => {
    const item = toDeviceParamItemDto({ paramCode: 'p', required: false, hidden: false } as any);
    expect(item!.required).toBe(false);
    expect(item!.hidden).toBe(false);
  });

  it('无 id 且 param_code 为空的不完整新行返回 null（对齐 blur 自动保存拒绝空码行）', () => {
    expect(toDeviceParamItemDto({ tempId: 'temp_1', paramCode: '', paramName: '未填码' } as any)).toBeNull();
  });

  it('无 id 但 param_code 已填的新行正常转换（后端按码 upsert）', () => {
    const item = toDeviceParamItemDto({ tempId: 'temp_2', paramCode: 'new_param', paramName: '新增', direction: 'input' } as any);
    expect(item).toEqual({ param_code: 'new_param', param_name: '新增', direction: 'input' });
    expect('id' in item!).toBe(false);
  });

  it('带 id 的行即使 param_code 被清空也保留提交（后端 id 分支不更新 param_code，行不被误删）', () => {
    const item = toDeviceParamItemDto({ id: 9, paramCode: '' } as any);
    expect(item).toEqual({ id: 9, param_code: '' });
  });
});

describe('toParamMappingItemDto（mappings 列表项）', () => {
  it('逐字段转 snake_case，保留 id，剔除 paramName/dimensionName 前端展示字段', () => {
    const item = toParamMappingItemDto({
      id: 21,
      tempId: 'temp_mapping_x',
      algorithmType: 'voice_llm',
      source: 'device',
      sourceParam: 'asr_text',
      paramName: '识别文本',
      sourceDirection: 'output',
      dimensionId: 5,
      dimensionName: '准确率',
      targetParam: 'text',
      transformType: 'none',
    } as any);

    expect(item).toEqual({
      id: 21,
      source: 'device',
      source_param: 'asr_text',
      source_direction: 'output',
      dimension_id: 5,
      target_param: 'text',
      transform_type: 'none',
    });
    expect(item!.tempId).toBeUndefined();
    expect(item!.algorithmType).toBeUndefined();
    expect(item!.paramName).toBeUndefined();
    expect(item!.dimensionName).toBeUndefined();
  });

  it('无 id 且 sourceParam/targetParam 未填齐的不完整新行返回 null（后端会原样建成空键值脏行）', () => {
    expect(toParamMappingItemDto({ tempId: 't', sourceParam: '', targetParam: '' } as any)).toBeNull();
    expect(toParamMappingItemDto({ tempId: 't', sourceParam: 'a', targetParam: '' } as any)).toBeNull();
    expect(toParamMappingItemDto({ tempId: 't', sourceParam: '', targetParam: 'b' } as any)).toBeNull();
  });

  it('无 id 但键值填齐的新行正常转换；带 id 的行即使键值被清空也保留提交（后端 id 分支按字段更新）', () => {
    expect(toParamMappingItemDto({ tempId: 't', sourceParam: 'a', targetParam: 'b' } as any)).toEqual({
      source_param: 'a',
      target_param: 'b',
    });
    expect(toParamMappingItemDto({ id: 7, sourceParam: '', targetParam: '' } as any)).toEqual({
      id: 7,
      source_param: '',
      target_param: '',
    });
  });
});

describe('toAssociatedDimensionItemDto（associated_dimensions 列表项）', () => {
  it('转 dimension_id/weight/is_default，绝不透传关系行 id（后端 or id 回退会把关系行 id 误当维度 id 对账）', () => {
    const item = toAssociatedDimensionItemDto({
      id: 33,
      tempId: 'temp_dim_1',
      dimensionId: 8,
      name: '准确率',
      description: 'x',
      type: 'accuracy',
      weight: 1.5,
      isDefault: true,
    } as any);

    expect(item).toEqual({ dimension_id: 8, weight: 1.5, is_default: true });
    expect('id' in item).toBe(false);
    expect(item.tempId).toBeUndefined();
    expect(item.name).toBeUndefined();
    expect(item.type).toBeUndefined();
    expect(item.description).toBeUndefined();
  });

  it('weight/isDefault 为 0/false 时不丢失', () => {
    const item = toAssociatedDimensionItemDto({ dimensionId: 2, weight: 0, isDefault: false } as any);
    expect(item.weight).toBe(0);
    expect(item.is_default).toBe(false);
  });
});

describe('toAlgorithmDefinitionDto 四列表深度转换', () => {
  it('device_params/api_params/mappings/associated_dimensions 逐项转 snake_case', () => {
    const body = toAlgorithmDefinitionDto({
      type: 'voice_llm',
      name: '语音大模型',
      deviceParams: [
        { id: 12, tempId: 't1', paramCode: 'audio_channel', paramName: '声道', paramType: 'number', direction: 'output', required: true, uiOrder: 3, hidden: false },
        { tempId: 't2', paramCode: 'new_p', paramName: '新增参数' },
        { tempId: 't3', paramCode: '', paramName: '空码行' },
      ],
      apiParams: [
        { id: 15, tempId: 't4', paramCode: 'api_lang', paramName: '语言', paramType: 'text' },
      ],
      mappings: {
        device: [
          { id: 21, tempId: 'm1', source: 'device', sourceParam: 'asr_text', sourceDirection: 'output', targetParam: 'text', transformType: 'none' },
          { tempId: 'm2', sourceParam: '', targetParam: '' },
        ],
        api: [
          { tempId: 'm3', sourceParam: 'code', targetParam: 'req_text' },
        ],
        evaluation: [
          { id: 30, source: 'case', sourceParam: 'ref', sourceDirection: 'output', dimensionId: 5, targetParam: 'acc', transformType: 'none' },
        ],
      },
      associatedDimensions: [
        { id: 33, tempId: 'd1', dimensionId: 8, name: '准确率', weight: 1.5, isDefault: true },
        { tempId: 'd2', dimensionId: null, weight: 1.0, isDefault: false },
      ],
    } as any);

    expect(body.type).toBe('voice_llm');
    expect(body.device_params).toHaveLength(2);
    expect(body.device_params[0]).toEqual({
      id: 12,
      param_code: 'audio_channel',
      param_name: '声道',
      param_type: 'number',
      direction: 'output',
      required: true,
      ui_order: 3,
      hidden: false,
    });
    expect(body.device_params[1]).toEqual({ param_code: 'new_p', param_name: '新增参数' });
    expect(body.api_params).toEqual([{ id: 15, param_code: 'api_lang', param_name: '语言', param_type: 'text' }]);
    expect(body.mappings.device).toEqual([
      { id: 21, source: 'device', source_param: 'asr_text', source_direction: 'output', target_param: 'text', transform_type: 'none' },
    ]);
    expect(body.mappings.api).toEqual([{ source_param: 'code', target_param: 'req_text' }]);
    expect(body.mappings.evaluation).toEqual([
      { id: 30, source: 'case', source_param: 'ref', source_direction: 'output', dimension_id: 5, target_param: 'acc', transform_type: 'none' },
    ]);
    expect(body.associated_dimensions).toEqual([
      { dimension_id: 8, weight: 1.5, is_default: true },
      { dimension_id: null, weight: 1.0, is_default: false },
    ]);
  });

  it('各列表缺省时请求体不含对应键；空数组保留空列表（后端整体替换语义）', () => {
    const body = toAlgorithmDefinitionDto({ type: 'voice_llm' } as any);
    expect(body).toEqual({ type: 'voice_llm' });
    expect('device_params' in body).toBe(false);
    expect('api_params' in body).toBe(false);
    expect('mappings' in body).toBe(false);
    expect('associated_dimensions' in body).toBe(false);

    const emptyBody = toAlgorithmDefinitionDto({
      deviceParams: [],
      apiParams: [],
      mappings: { device: [], api: [], evaluation: [] },
      associatedDimensions: [],
    } as any);
    expect(emptyBody.device_params).toEqual([]);
    expect(emptyBody.api_params).toEqual([]);
    expect(emptyBody.mappings).toEqual({ device: [], api: [], evaluation: [] });
    expect(emptyBody.associated_dimensions).toEqual([]);
  });
});

describe('algorithmApi.updateDefinition 四列表 wire 契约', () => {
  it('PUT /algorithm/definitions/{type} 请求体四列表均为 snake_case 列表项', async () => {
    mockedRequest.mockResolvedValueOnce({ type: 'voice_llm' });
    await algorithmApi.updateDefinition('voice_llm', {
      type: 'voice_llm',
      deviceParams: [{ id: 12, paramCode: 'audio_channel', paramName: '声道', paramType: 'number', direction: 'output', required: true, uiOrder: 3, hidden: false }],
      apiParams: [{ tempId: 't', paramCode: 'api_lang', paramName: '语言' }],
      caseParams: [{ id: 3, paramCode: 'lang', paramName: '语言', required: true }],
      mappings: { device: [{ id: 21, sourceParam: 'asr_text', targetParam: 'text' }] },
      associatedDimensions: [{ id: 33, dimensionId: 8, weight: 1.5, isDefault: true }],
    } as any);

    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [, url, body] = mockedRequest.mock.calls[0];
    expect(url).toBe('/algorithm/definitions/voice_llm');
    expect((body as any).device_params).toEqual([
      { id: 12, param_code: 'audio_channel', param_name: '声道', param_type: 'number', direction: 'output', required: true, ui_order: 3, hidden: false },
    ]);
    expect((body as any).api_params).toEqual([{ param_code: 'api_lang', param_name: '语言' }]);
    expect((body as any).case_params).toEqual([{ id: 3, param_code: 'lang', param_name: '语言', required: true }]);
    expect((body as any).mappings).toEqual({
      device: [{ id: 21, source_param: 'asr_text', target_param: 'text' }],
    });
    expect((body as any).associated_dimensions).toEqual([{ dimension_id: 8, weight: 1.5, is_default: true }]);
    expect((body as any).deviceParams).toBeUndefined();
    expect((body as any).apiParams).toBeUndefined();
    expect((body as any).mappings.device[0].sourceParam).toBeUndefined();
    expect((body as any).associatedDimensions).toBeUndefined();
  });

  it('createDefinition 同样走深度转换（模态窗新建/算法复制链路）', async () => {
    mockedRequest.mockResolvedValueOnce({ type: 'x_copy' });
    await algorithmApi.createDefinition({
      type: 'x_copy',
      deviceParams: [{ id: 12, paramCode: 'p', paramName: 'n' }],
    } as any);

    const [, , body] = mockedRequest.mock.calls[0];
    expect((body as any).device_params).toEqual([{ id: 12, param_code: 'p', param_name: 'n' }]);
    expect((body as any).deviceParams).toBeUndefined();
  });
});
