/**
 * audioUtils —— 从标注提取用例参数值
 *
 * 提供 extractParamsFromAnnotations：按用例参数配置（param_code / annotation_code / field_path）
 * 从标注数组中提取参数值，与后端 CaseParameterExtractor 逻辑对齐（原 audioUtils.ts 内参数提取分组）。
 */

/**
 * 从标注 JSON 按用例参数配置提取参数值
 *
 * 遍历 caseParams 配置，用 annotation_code 找标注，用 field_path 从标注 data 取值。
 * 与后端 CaseParameterExtractor.extract_params_from_annotations 逻辑一致，
 * 但放在前端以便用户上传时预览/修改解析结果。
 *
 * @param annotations 上传音频时的标注数组 [{code, data, ...}]
 * @param caseParams  CaseAlgorithmParam 配置数组 [{param_code, annotation_code, field_path, ...}]
 * @param algorithmType 算法类型（annotation_code 为空时默认用此值）
 * @returns [{fieldCode, fieldValue}] 格式的参数列表（不含 inputAudio，音频在 round.audios 里）
 */
export const extractParamsFromAnnotations = (
  annotations: Array<{ code?: string; data?: any }>,
  caseParams: Array<Record<string, any>>,
  algorithmType: string
): Array<{ fieldCode: string; fieldValue: any }> => {
  if (!annotations?.length || !caseParams?.length || !algorithmType) return [];

  // API 返回驼峰（paramCode/fieldPath/annotationCode）
  const get = (obj: any, camel: string, snake?: string) =>
    obj[camel] ?? (snake ? obj[snake] : undefined);

  const result: Array<{ fieldCode: string; fieldValue: any }> = [];

  for (const param of caseParams) {
    const paramCode = get(param, 'paramCode', 'param_code');
    if (!paramCode) continue;

    const annCode = get(param, 'annotationCode', 'annotation_code') || algorithmType;
    const fieldPath = get(param, 'fieldPath', 'field_path') || paramCode;

    // 用 annotation_code 找标注
    let matched = annotations.filter(a => a.code === annCode);
    if (matched.length === 0) {
      // 匹配不到则尝试所有标注
      matched = annotations;
    }

    // 从标注 data 按 field_path 取值
    let value: any = undefined;
    for (const ann of matched) {
      if (!ann.data) continue;
      const data = ann.data;
      if (typeof data === 'string') {
        value = data;
        break;
      }
      if (data && typeof data === 'object') {
        // field_path 支持 'segments[].field' 格式；不含 '[]' 时自动补 'segments[].' 前缀进 segments 取值
        const effectivePath = fieldPath.includes('[]') ? fieldPath : `segments[].${fieldPath}`;
        if (effectivePath.includes('[].')) {
          const parts = effectivePath.split('[].');
          const arrKey = parts[0];
          const fieldKey = parts[1] || null;
          const arr = data[arrKey];
          if (Array.isArray(arr) && fieldKey) {
            // 兼容驼峰/下划线：标注 segment 的 key 可能是任一形式
            const getField = (seg: any, key: string) => {
              if (seg[key] !== undefined) return seg[key];
              // 驼峰转下划线
              const snake = key.replace(/([A-Z])/g, '_$1').toLowerCase();
              if (snake !== key && seg[snake] !== undefined) return seg[snake];
              // 下划线转驼峰
              const camel = snake.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
              if (camel !== key && seg[camel] !== undefined) return seg[camel];
              return undefined;
            };
            const collected = arr
              .filter((seg: any) => seg && typeof seg === 'object' && getField(seg, fieldKey) !== undefined && getField(seg, fieldKey) !== null)
              .map((seg: any) => getField(seg, fieldKey))
              // 过滤掉空数组/空字符串/空对象（如 interferers: [] 不应算作有效值）
              .filter((c: any) => !(c && typeof c === 'object' && typeof c.length === 'number' && c.length === 0) && !(typeof c === 'string' && c.length === 0));
            if (collected.length > 0) {
              value = collected.length === 1 ? collected[0] : collected;
              break;
            }
          }
        } else {
          if (fieldPath in data) {
            value = data[fieldPath];
            break;
          }
          // 尝试 text 字段作为 fallback
          if (fieldPath === paramCode && 'text' in data) {
            value = data.text;
            break;
          }
        }
      }
    }

    if (value !== undefined && value !== null) {
      result.push({ fieldCode: paramCode, fieldValue: value });
    }
  }

  return result;
};