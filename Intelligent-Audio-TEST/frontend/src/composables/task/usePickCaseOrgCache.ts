// -*- coding: utf-8 -*-
/**
 * 购物车 / 复核用例层组织字段会话缓存（INT-1831）。
 *
 * 购物车接口快照（GET /tasks/cherry-picks/cart）只到 source_case_id / 名称级，
 * 不带 tags / group_name；而候选行（/candidates）已返组织字段（INT-1130 §11-7）。
 * 因此在挑选侧载入候选时把 case_id → 组织字段记入本会话缓存，购物车 / 复核四视图
 * 的用例层组织层（分组视图 / 标签视图）据此聚合；缓存未命中（历史购物车条目）走
 * 「未分组」/「未设置标签」兜底桶，不新增后端请求、不改购物车契约。
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
