/**
 * normalizeMappings source 值回归锁定（INT-210 打回缺陷 1）：
 * 合法 source 集合必须与后端一致（algorithm_service config_cache.py VALID_SOURCES
 * 含 case_config）。此前集合缺 case_config，模态窗加载即把存量评估映射
 * source='case_config' 强转为 'case'，「确定」整体保存随之落库改写——
 * evaluation_service 按 source 分支取数，case_config 从用例配置取结构性字段，
 * 改写后评估数据缺失。
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {},
}));
vi.mock('@/composables/modal/useModal', () => ({
  useModalControl: () => ({}),
  MODAL_TYPES: {},
}));
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({}),
}));

import { normalizeMappings } from '../useAlgorithmCrudOps';

describe('normalizeMappings source 合法值集合', () => {
  it('保留存量 source=case_config（打回缺陷 1 回归：不得强转为 case）', () => {
    const result = normalizeMappings({
      evaluation: [
        { id: 1682, source: 'case_config', sourceParam: 'audios', dimensionId: 5, targetParam: 'played_audios', transformType: 'none', sourceDirection: 'output' },
      ],
    });

    expect(result.evaluation).toHaveLength(1);
    expect(result.evaluation[0].source).toBe('case_config');
    expect(result.evaluation[0].sourceParam).toBe('audios');
    expect(result.evaluation[0].targetParam).toBe('played_audios');
  });

  it('五个合法 source 原值保留：case/case_config/reference/device/api', () => {
    const sources = ['case', 'case_config', 'reference', 'device', 'api'];
    const result = normalizeMappings({
      evaluation: sources.map((s, i) => ({ id: i + 1, source: s, sourceParam: `p${i}`, targetParam: `t${i}` })),
    });

    expect(result.evaluation.map((m: any) => m.source)).toEqual(sources);
  });

  it('非法/缺失 source 仍兜底为 case（原有语义不变）', () => {
    const result = normalizeMappings({
      evaluation: [
        { id: 1, source: 'evaluation', sourceParam: 'a', targetParam: 'b' },
        { id: 2, source: '', sourceParam: 'a', targetParam: 'b' },
        { id: 3, sourceParam: 'a', targetParam: 'b' },
      ],
    });

    expect(result.evaluation.map((m: any) => m.source)).toEqual(['case', 'case', 'case']);
  });

  it('空输入产出空分组（device/api/evaluation 三组齐备）', () => {
    expect(normalizeMappings(null)).toEqual({ device: [], api: [], evaluation: [] });
    expect(normalizeMappings(undefined)).toEqual({ device: [], api: [], evaluation: [] });
    expect(normalizeMappings({ device: [], api: [], evaluation: [] })).toEqual({
      device: [],
      api: [],
      evaluation: [],
    });
  });
});
