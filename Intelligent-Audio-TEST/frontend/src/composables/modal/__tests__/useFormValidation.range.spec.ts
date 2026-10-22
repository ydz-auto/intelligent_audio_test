/**
 * INT-1388 回归：useFormValidation 数值范围（min/max）与跨字段校验
 *
 * 修复 P3-1：评估维度表单「权重/小数位数超范围、结果 min>max 提交被拦」——
 * 根因是 useFormValidation 只校验必填/正则，未按字段定义的 min/max 拦截非法数值。
 * 本测试锁定：number 类型且有 min/max 的字段越界返回红字、合法值通过、跨字段（resultMin<=resultMax）拦截。
 */
import { describe, it, expect } from 'vitest';
import { useFormValidation } from '../useFormValidation';

describe('useFormValidation 数值范围校验（INT-1388 P3-1）', () => {
  it('weight 超出 max 拦截，提示红字', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'weight', label: '权重', type: 'number', required: true, min: 1, max: 10 },
    ];
    const ok = validateForm(fields, { weight: 99 });
    expect(ok).toBe(false);
    expect(errors.weight).toBe('权重不能大于 10');
  });

  it('weight 低于 min 拦截', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'weight', label: '权重', type: 'number', required: true, min: 1, max: 10 },
    ];
    validateForm(fields, { weight: 0 });
    expect(errors.weight).toBe('权重不能小于 1');
  });

  it('decimalPlaces 超出 max 拦截', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'decimalPlaces', label: '小数位数', type: 'number', required: true, min: 0, max: 4 },
    ];
    validateForm(fields, { decimalPlaces: 99 });
    expect(errors.decimalPlaces).toBe('小数位数不能大于 4');
  });

  it('合法范围内的数值通过', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'weight', label: '权重', type: 'number', required: true, min: 1, max: 10 },
      { key: 'decimalPlaces', label: '小数位数', type: 'number', required: true, min: 0, max: 4 },
    ];
    const ok = validateForm(fields, { weight: 5, decimalPlaces: 2 });
    expect(ok).toBe(true);
    expect(errors).toEqual({});
  });

  it('空值不触发范围校验（必填另行处理）', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'weight', label: '权重', type: 'number', required: false, min: 1, max: 10 },
    ];
    const ok = validateForm(fields, { weight: '' });
    expect(ok).toBe(true);
    expect(errors).toEqual({});
  });

  it('跨字段校验：resultMin > resultMax 拦截（红字提示）', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'resultMin', label: '结果最小值', type: 'number', required: true,
        validate: (values: Record<string, any>) => {
          const min = Number(values.resultMin);
          const max = Number(values.resultMax);
          if (!isNaN(min) && !isNaN(max) && values.resultMin !== '' && values.resultMax !== '' && min > max) {
            return '结果最小值不能大于结果最大值';
          }
          return null;
        } },
      { key: 'resultMax', label: '结果最大值', type: 'number', required: true,
        validate: (values: Record<string, any>) => {
          const min = Number(values.resultMin);
          const max = Number(values.resultMax);
          if (!isNaN(min) && !isNaN(max) && values.resultMin !== '' && values.resultMax !== '' && min > max) {
            return '结果最小值不能大于结果最大值';
          }
          return null;
        } },
    ];
    const ok = validateForm(fields, { resultMin: 200, resultMax: 1 });
    expect(ok).toBe(false);
    expect(errors.resultMin).toBe('结果最小值不能大于结果最大值');
    expect(errors.resultMax).toBe('结果最小值不能大于结果最大值');
  });

  it('跨字段合法（resultMin <= resultMax）通过', () => {
    const { errors, validateForm } = useFormValidation();
    const fields = [
      { key: 'resultMin', label: '结果最小值', type: 'number', required: true },
      { key: 'resultMax', label: '结果最大值', type: 'number', required: true },
    ];
    const ok = validateForm(fields, { resultMin: 0, resultMax: 100 });
    expect(ok).toBe(true);
  });
});
