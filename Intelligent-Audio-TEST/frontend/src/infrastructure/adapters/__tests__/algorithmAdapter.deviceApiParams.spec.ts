/**
 * 设备/API 参数 upsert 请求体 wire 契约测试（INT-910 P2-1）
 *
 * 覆盖：POST/PUT /algorithm/params 写路径必须透传 direction / param_type_source /
 * options_* / validation_rules（后端按其路由 device/api 表并保留方向，缺省均回退
 * input/device，曾因误用 toCaseParamUpsertDto 静默丢失这三个字段导致 API 参数落错表、
 * direction 被改回 input）。同时验证 algorithmApi.createParam/updateParam 请求体
 * 携带 snake_case 字段且不再出现 case 参数专用字段。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { algorithmApi } from '../../api/algorithmApi';
import { toDeviceApiParamUpsertDto } from '../algorithmAdapter';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('toDeviceApiParamUpsertDto wire 契约（INT-910 P2-1）', () => {
  it('API 参数自动保存请求体透传 param_type_source=api 与 direction 原值', () => {
    const dto = toDeviceApiParamUpsertDto({
      algorithmType: 'voice_llm',
      paramTypeSource: 'api',
      paramCode: 'api_audio',
      paramName: 'API音频',
      paramType: 'text',
      direction: 'output',
      required: false,
      defaultValue: null,
      uiOrder: 3,
      hidden: false,
    } as any);
    expect(dto.algorithm_type).toBe('voice_llm');
    expect(dto.param_type_source).toBe('api');
    expect(dto.direction).toBe('output');
    expect(dto.param_code).toBe('api_audio');
    expect(dto.param_type).toBe('text');
    // 请求体只含 snake_case 键
    expect('paramTypeSource' in dto).toBe(false);
    expect('paramCode' in dto).toBe(false);
  });

  it('设备参数自动保存透传 options_* / validation_rules / help_text / ui_order', () => {
    const dto = toDeviceApiParamUpsertDto({
      algorithmType: 'voice_llm',
      paramTypeSource: 'device',
      paramCode: 'wav_path',
      paramType: 'audio_file',
      direction: 'input',
      optionsSource: 'languages',
      optionsField: 'code',
      optionsLabelField: 'name',
      validationRules: '{"min":1}',
      helpText: '音频路径',
      uiOrder: 1,
    } as any);
    expect(dto.options_source).toBe('languages');
    expect(dto.options_field).toBe('code');
    expect(dto.options_label_field).toBe('name');
    expect(dto.validation_rules).toBe('{"min":1}');
    expect(dto.help_text).toBe('音频路径');
    expect(dto.ui_order).toBe(1);
    expect(dto.param_type_source).toBe('device');
  });

  it('缺省 direction / param_type_source 时键值为 undefined（JSON 序列化剔除，后端取默认）', () => {
    const dto = toDeviceApiParamUpsertDto({ paramCode: 'p' } as any);
    expect('direction' in dto).toBe(true);
    expect(dto.direction).toBeUndefined();
    expect('param_type_source' in dto).toBe(true);
    expect(dto.param_type_source).toBeUndefined();
  });
});

describe('algorithmApi.createParam / updateParam wire 契约（INT-910 P2-1）', () => {
  it('createParam POST /algorithm/params 请求体携带 param_type_source / direction / options_*', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 101,
      algorithm_type: 'voice_llm',
      param_code: 'api_audio',
      direction: 'output',
    });
    await algorithmApi.createParam({
      algorithmType: 'voice_llm',
      paramTypeSource: 'api',
      paramCode: 'api_audio',
      paramName: 'API音频',
      paramType: 'text',
      direction: 'output',
      uiOrder: 3,
    } as any);

    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [, url, body] = mockedRequest.mock.calls[0];
    expect(url).toBe('/algorithm/params');
    expect((body as any).param_type_source).toBe('api');
    expect((body as any).direction).toBe('output');
    expect((body as any).param_code).toBe('api_audio');
    expect((body as any).paramTypeSource).toBeUndefined();
  });

  it('updateParam PUT /algorithm/params/{id} 请求体携带 direction 原值（output 不回落 input）', async () => {
    mockedRequest.mockResolvedValueOnce({
      id: 7,
      algorithm_type: 'voice_llm',
      param_code: 'wav_path',
      direction: 'output',
    });
    const result = await algorithmApi.updateParam(7, {
      paramCode: 'wav_path',
      direction: 'output',
      required: true,
    } as any);

    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [, url, body] = mockedRequest.mock.calls[0];
    expect(url).toBe('/algorithm/params/7');
    expect((body as any).direction).toBe('output');
    expect((body as any).required).toBe(true);
    expect((body as any).param_code).toBe('wav_path');
    // 响应转换保留 direction（回填编辑态不复位为 input）
    expect(result.direction).toBe('output');
  });
});
