// -*- coding: utf-8 -*-
/**
 * 购物车 / 预览用例层组织字段会话缓存（INT-1831）。
 *
 * 购物车条目自身已随接口返回用例级组织字段（GET /tasks/cherry-picks/cart 的
 * items[] 带 tags / group_id / group_name），四视图组织层以条目字段为主
 * （cartTree.resolveCartCaseOrgMap）。本缓存只是补充：挑选侧载入候选
 * （/candidates，INT-1130 §11-7）时把 case_id → 组织字段记入，供条目缺字段的
 * 历史快照兜底；全缺时仍走「未分组」/「未设置标签」兜底桶，不新增后端请求。
 */
import { computed, ref } from 'vue';
import type { PickCaseOrgInfo } from '../../components/task/pick/pickTree';

/** 会话级缓存（模块单例，跨组件共享，与 usePickCart 同模式） */
const caseOrgCache = ref<Map<string, PickCaseOrgInfo>>(new Map());

/** 候选行组织字段子集（PickCandidate / 来源结果行均结构兼容） */
export interface CaseOrgSource {
  caseId: string
  tags?: string[] | null
  groupId?: string | number | null
  groupName?: string | null
}

/** 记入用例组织字段（重复命中覆盖为最新值；空字段不写、保留已有真值） */
export function rememberCaseOrg(rows: Iterable<CaseOrgSource>): void {
  const next = new Map(caseOrgCache.value);
  let changed = false;
  for (const row of rows) {
    if (!row.caseId) continue;
    const tags = row.tags ?? [];
    const groupName = row.groupName ?? null;
    const groupId = row.groupId != null ? String(row.groupId) : null;
    if (tags.length === 0 && groupName == null && groupId == null) continue;
    const prev = next.get(row.caseId);
    if (prev && (prev.tags?.length ?? 0) >= tags.length && prev.groupName === groupName && prev.groupId === groupId) {
      continue;
    }
    next.set(row.caseId, { tags, groupId, groupName });
    changed = true;
  }
  if (changed) caseOrgCache.value = next;
}

/** 清空会话缓存（测试/退出登录场景） */
export function resetCaseOrgCache(): void {
  caseOrgCache.value = new Map();
}

export function usePickCaseOrgCache() {
  const caseOrgMap = computed<ReadonlyMap<string, PickCaseOrgInfo>>(() => caseOrgCache.value);
  return { caseOrgMap, rememberCaseOrg, resetCaseOrgCache };
}
