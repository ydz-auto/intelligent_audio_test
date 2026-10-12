/**
 * 「确定」逐条补存参考参数回归锁定（INT-199）：
 * 算法定义编辑的整体保存被后端忽略（PUT definitions 的 Update schema 不收
 * reference_params），此前编辑分支完全依赖 blur 防抖逐条保存兜底——未失焦行
 * （防抖窗口内点确定）落库不可靠。saveReferenceParams 在确定时逐条补存：
 * 有 id 更新、无 id 有 code 新建，经行 id 与 blur 自动保存去重，幂等可重入；
 * 无 code 的不完整行跳过（对齐 blur 拒存语义）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { createReferenceParam, updateReferenceParam } = vi.hoisted(() => ({
  createReferenceParam: vi.fn(),
  updateReferenceParam: vi.fn(),
}));

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: {
    createReferenceParam,
    updateReferenceParam,
  },
}));
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({}),
}));

import { useAlgorithmParamOps } from '../useAlgorithmParamOps';

function setup(referenceParams: any[], mode = 'edit') {
  const formState = { type: 'voice_llm', referenceParams };
  const { saveReferenceParams } = useAlgorithmParamOps(
    formState,
    { value: 'device' },
    { value: mode },
    { value: 0 }
  );
  return { formState, saveReferenceParams };
}

describe('saveReferenceParams 「确定」逐条补存（INT-199）', () => {
  beforeEach(() => {
    createReferenceParam.mockReset();
    updateReferenceParam.mockReset();
  });

  it('有 id 行走更新分支：携带行 id 与当前算法 type，不触发 create', async () => {
    const row = { id: 7, code: 'volume', name: '音量', type: 'text', helpText: '提示', annotationCode: 'volume', annotationFormat: '', fieldPath: '', mergeMode: 'join' };
    const { saveReferenceParams } = setup([row]);

    await saveReferenceParams();

    expect(updateReferenceParam).toHaveBeenCalledTimes(1);
    expect(updateReferenceParam).toHaveBeenCalledWith(7, 'voice_llm', expect.objectContaining({ code: 'volume', name: '音量' }));
    expect(createReferenceParam).not.toHaveBeenCalled();
  });

  it('无 id 有 code 行走新建分支：携带 algorithmType，成功后回填 p.id（与 blur 去重的基础）', async () => {
    createReferenceParam.mockResolvedValue({ id: 42, code: 'gain' });
    const row: any = { code: 'gain', name: '增益', type: 'text' };
    const { formState, saveReferenceParams } = setup([row]);

    await saveReferenceParams();

    expect(createReferenceParam).toHaveBeenCalledTimes(1);
    expect(createReferenceParam).toHaveBeenCalledWith(expect.objectContaining({ code: 'gain', algorithmType: 'voice_llm' }));
    expect(row.id).toBe(42);
    expect(updateReferenceParam).not.toHaveBeenCalled();
  });

  it('无 code 的不完整新行跳过（不新建也不更新）', async () => {
    const { saveReferenceParams } = setup([{ code: '', name: '空行' }]);

    await saveReferenceParams();

    expect(createReferenceParam).not.toHaveBeenCalled();
    expect(updateReferenceParam).not.toHaveBeenCalled();
  });

  it('单行失败不中断后续行（编辑分支整体保存不被参考参数拖垮）', async () => {
    createReferenceParam.mockRejectedValueOnce(new Error('dup'));
    const rows = [{ code: 'bad_row' }, { code: 'good_row' }];
    const { formState, saveReferenceParams } = setup(rows);

    await saveReferenceParams();

    expect(createReferenceParam).toHaveBeenCalledTimes(2);
    expect(createReferenceParam).toHaveBeenLastCalledWith(expect.objectContaining({ code: 'good_row' }));
    expect(formState.referenceParams[0].id).toBeUndefined();
  });

  it('新建模式语义保持：无 id 行全部补存（原 savePendingReferenceParams 行为不回退）', async () => {
    createReferenceParam.mockResolvedValue({ id: 9 });
    const rows = [{ code: 'a' }, { code: 'b' }];
    const { formState, saveReferenceParams } = setup(rows, 'create');

    await saveReferenceParams();

    expect(createReferenceParam).toHaveBeenCalledTimes(2);
    expect(formState.referenceParams.map((p: any) => p.id)).toEqual([9, 9]);
    expect(updateReferenceParam).not.toHaveBeenCalled();
  });
});
