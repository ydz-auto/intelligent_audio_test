/**
 * 算法定义整体保存 case_params 键名契约测试（INT-197）
 * 覆盖：toAlgorithmDefinitionDto 深度转换 case_params 列表项为 snake_case（后端
 * _update_case_params 仅识别 snake_case 键，camelCase 透传会 200 假成功静默丢失）、
 * id 保留（后端以 id 对账既有参数）、前端态字段（tempId/component）剔除、
 * updateDefinition 请求体 wire 契约。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { algorithmApi } from '../../api/algorithmApi';
import { toAlgorithmDefinitionDto, toCaseParamUpsertDto, toAlgorithmCaseParam } from '../algorithmAdapter';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('toAlgorithmDefinitionDto case_params 深度转换', () => {
  it('case_params 列表项逐字段转 snake_case，保留 id，剔除前端态字段', () => {
    const body = toAlgorithmDefinitionDto({
      type: 'voice_llm',
      caseParams: [
        {
          id: 7,
          tempId: 'temp_1',
          paramCode: 'tts_speed',
          paramName: '语速',
          paramType: 'number',
          required: true,
          defaultValue: 1.0,
          helpText: '语速倍率',
          uiOrder: 2,
          hidden: false,
          scope: 'common',
          minValue: 0.5,
          maxValue: 2,
          step: 0.1,
          unit: 'x',
          component: 'input-number',
          annotationCode: 'x',
          fieldPath: 'y',
        },
        {
          tempId: 'temp_2',
          paramCode: 'new_param',
          paramName: '新增参数',
        },
      ],
    } as any);

    expect(body.type).toBe('voice_llm');
    expect(body.case_params).toHaveLength(2);
    expect(body.case_params[0]).toEqual({
      id: 7,
      param_code: 'tts_speed',
      param_name: '语速',
      param_type: 'number',
      required: true,
      default_value: 1.0,
      help_text: '语速倍率',
      ui_order: 2,
      hidden: false,
      scope: 'common',
      min_value: 0.5,
      max_value: 2,
      step: 0.1,
      unit: 'x',
      annotation_code: 'x',
      field_path: 'y',
    });
    expect(body.case_params[0].tempId).toBeUndefined();
    expect(body.case_params[0].component).toBeUndefined();
    expect(body.case_params[1]).toEqual({
      param_code: 'new_param',
      param_name: '新增参数',
    });
  });

  it('caseParams 缺省时请求体不含 case_params 键', () => {
    const body = toAlgorithmDefinitionDto({ type: 'voice_llm' } as any);
    expect(body).toEqual({ type: 'voice_llm' });
    expect('case_params' in body).toBe(false);
  });

  it('caseParams 为空数组时保留空列表（后端整体替换语义清空用例参数）', () => {
    const body = toAlgorithmDefinitionDto({ type: 'voice_llm', caseParams: [] } as any);
    expect(body.case_params).toEqual([]);
  });

  it('required/hidden 为 false 的布尔字段不丢失', () => {
    const body = toAlgorithmDefinitionDto({
      caseParams: [{ paramCode: 'p', required: false, hidden: false }],
    } as any);
    expect(body.case_params[0].required).toBe(false);
    expect(body.case_params[0].hidden).toBe(false);
  });
});

describe('toCaseParamUpsertDto / toAlgorithmCaseParam annotation_code·field_path 契约（INT-198）', () => {
  it('upsert 请求体携带 annotation_code/field_path（/algorithm/case-params 写路径）', () => {
    const dto = toCaseParamUpsertDto({
      algorithmType: 'int138r3tmp',
      paramCode: 'ann138',
      annotationCode: 'ann138',
      fieldPath: 'fp138',
    } as any);
    expect(dto.annotation_code).toBe('ann138');
    expect(dto.field_path).toBe('fp138');
  });

  it('upsert 缺省字段时键值为 undefined（JSON 序列化剔除，后端取默认）', () => {
    const dto = toCaseParamUpsertDto({ paramCode: 'p' } as any);
    expect('annotation_code' in dto).toBe(true);
    expect(dto.annotation_code).toBeUndefined();
    expect(dto.field_path).toBeUndefined();
  });

  it('toAlgorithmCaseParam 回读 annotation_code/field_path（刷新后回填）', () => {
    const domain = toAlgorithmCaseParam({
      id: 1,
      algorithm_type: 'int138r3tmp',
      param_code: 'ann138',
      annotation_code: 'ann138',
      field_path: 'fp138',
    } as any);
    expect(domain.annotationCode).toBe('ann138');
    expect(domain.fieldPath).toBe('fp138');
  });
});

describe('algorithmApi.updateDefinition case_params wire 契约', () => {
  it('PUT /algorithm/definitions/{type} 请求体携带 snake_case case_params', async () => {
    mockedRequest.mockResolvedValueOnce({ type: 'voice_llm', case_params: [] });
    await algorithmApi.updateDefinition('voice_llm', {
      caseParams: [{ id: 3, paramCode: 'lang', paramName: '语言', required: true }],
    } as any);

    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [, url, body] = mockedRequest.mock.calls[0];
    expect(url).toBe('/algorithm/definitions/voice_llm');
    expect((body as any).case_params).toEqual([
      { id: 3, param_code: 'lang', param_name: '语言', required: true },
    ]);
    expect((body as any).caseParams).toBeUndefined();
  });
});
