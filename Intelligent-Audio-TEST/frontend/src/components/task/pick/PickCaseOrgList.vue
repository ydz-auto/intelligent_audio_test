<template>
  <div class="pcol">
    <!-- 组织控件（常显：候选未返分组/标签字段时单兜底桶，控件不隐藏——§3.8.3 兜底口径） -->
    <PickCaseOrgControls
      :org="org"
      :sub-view="subView"
      :fallback-only="showFallbackHint"
      @update:org="(v) => emit('update:org', v)"
      @update:sub-view="(v) => emit('update:subView', v)"
    />

    <div v-if="roots.length === 0" class="pcol-empty">
      <i class="fas fa-inbox"></i>
      <p>无符合条件的用例</p>
    </div>
    <div v-else class="pcol-buckets">
      <div v-for="g in orgGroups" :key="g.key" class="pcol-bucket">
        <div class="pcol-bucket-header" :class="{ 'pcol-muted': isFallback(g.key) }">
          <span class="pcol-bucket-name">
            <i v-if="g.color" class="pcol-dot" :style="{ background: g.color }"></i>
            {{ g.label }}
          </span>
          <span class="pcol-bucket-count">{{ g.cases.length }} 个用例</span>
        </div>
        <div class="pcol-bucket-body">
          <!-- 平铺：用例卡直接铺于桶内 -->
          <template v-if="subView === 'flat'">
            <PickTree
              :roots="branchList(g.cases)"
              :selected="selected"
              :expanded-keys="expandedKeys"
              :already-added="alreadyAdded"
              :leaf-meta="leafMeta"
              @toggle-node="(n) => emit('toggle-node', n)"
              @toggle-expand="(k) => emit('toggle-expand', k)"
              @toggle-leaf="(rid) => emit('toggle-leaf', rid)"
            />
          </template>
          <!-- 交叉：分组视图内按标签 / 标签视图内按用例分组（子组头 + 计数） -->
          <template v-else>
            <div v-for="sg in crossGroups(g.cases)" :key="sg.key" class="pcol-subgroup">
              <div class="pcol-subgroup-header" :class="{ 'pcol-muted': isFallback(sg.key) }">
                <span class="pcol-subgroup-name">
                  <i v-if="sg.color" class="pcol-dot" :style="{ background: sg.color }"></i>
                  {{ sg.label }}
                </span>
                <span class="pcol-subgroup-count">{{ sg.cases.length }} 个用例</span>
              </div>
              <PickTree
                :roots="branchList(sg.cases)"
                :selected="selected"
                :expanded-keys="expandedKeys"
                :already-added="alreadyAdded"
                :leaf-meta="leafMeta"
                @toggle-node="(n) => emit('toggle-node', n)"
                @toggle-expand="(k) => emit('toggle-expand', k)"
                @toggle-leaf="(rid) => emit('toggle-leaf', rid)"
              />
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/layouts/main.css'

/**
 * PickCaseOrgList —— 用例视图组织列表（18_挑选合并交互重设计.md §3.8.3，INT-1110 返工 P1）。
 * 组织维度照用例管理页浏览习惯：分组视图（按用例分组聚合 +「未分组」兜底）｜标签视图
 * （按标签聚合 +「未设置标签」兜底）+ 平铺/交叉子视图（分组视图内按标签、标签视图内按用例分组）；
 * 交叉聚合复用 domain/lib/subViewAggregation.ts 同款纯函数。组织只影响用例层视觉分组，
 * 勾选联动 R1-R10 与共享 selectedResultIds 不变（桶内用例卡仍经 PickTree/PickTreeNodeRow 渲染）。
 */
import { computed } from 'vue';
import PickTree from './PickTree.vue';
import PickCaseOrgControls from './PickCaseOrgControls.vue';
import { buildPickCaseOrgBuckets, type PickOrgCaseItem, type PickCaseOrgInfo } from './pickTree';
import type { PickTreeNode } from './pickTree';
import type { PickCandidate } from '../../../infrastructure/api/cherryPickApi';
import {
  groupCasesByTag,
  groupCasesByCaseGroup,
  UNTAGGED_BUCKET_KEY,
  UNGROUPED_BUCKET_KEY,
  type CaseSubGroup,
} from '../../../domain/lib/subViewAggregation';

const props = withDefaults(defineProps<{
  /** 用例视图树根（顶层 = 用例级分支） */
  roots: PickTreeNode[];
  /** 选中叶 result_id 集（三态派生唯一真相；组织不触碰） */
  selected: ReadonlySet<number>;
  /** 展开的节点 key 集 */
  expandedKeys: ReadonlySet<string>;
  /** R10：已在购物车的 result_id 集（叶行「已加购」标记） */
  alreadyAdded?: ReadonlySet<number>;
  /** 叶行元数据（result_id → 候选行） */
  leafMeta?: Map<number, PickCandidate>;
  /** 组织维度（§3.8.3：分组视图/标签视图，会话态） */
  org: 'group' | 'tag';
  /** 子视图（平铺/交叉：分组视图内按标签、标签视图内按用例分组） */
  subView: 'flat' | 'byTag' | 'byGroup';
  /** §11-7 组织字段映射（caseId → tags/groupId/groupName；缺省全落「未分组」/「未设置标签」兜底桶） */
  caseOrgMap?: Map<string | number, PickCaseOrgInfo>;
}>(), {
  alreadyAdded: () => new Set<number>(),
  leafMeta: () => new Map<number, PickCandidate>(),
});

const emit = defineEmits<{
  (e: 'toggle-node', node: PickTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', resultId: number): void;
  (e: 'update:org', org: 'group' | 'tag'): void;
  (e: 'update:subView', subView: 'flat' | 'byTag' | 'byGroup'): void;
}>();

/** 组织桶（分组视图=按用例分组聚合，标签视图=按标签聚合；候选无组织字段 → 单一兜底桶） */
const orgGroups = computed(() => buildPickCaseOrgBuckets(props.roots, props.org, props.caseOrgMap));

/** 组织项 → 用例级分支（喂给 PickTree 渲染用例卡 + 卡内子树） */
function branchList(cases: PickOrgCaseItem[]): PickTreeNode[] {
  return cases.map((c) => c.branch);
}

/** 交叉聚合（桶内再按另一组织维度分组；无标签/无分组用例入兜底桶末尾） */
function crossGroups(cases: PickOrgCaseItem[]): CaseSubGroup<PickOrgCaseItem>[] {
  return props.org === 'group' ? groupCasesByTag(cases, []) : groupCasesByCaseGroup(cases);
}

/** 兜底桶弱化样式（「未设置标签」/「未分组」） */
function isFallback(key: string): boolean {
  return key === UNTAGGED_BUCKET_KEY || key === UNGROUPED_BUCKET_KEY;
}

/** §11-7 兜底提示：仅当候选无任何组织字段（全落单兜底桶）时显示 */
const showFallbackHint = computed(() => {
  const gs = orgGroups.value;
  return gs.length === 1 && isFallback(gs[0].key);
});
</script>

<style scoped>
.pcol {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* 组织控件样式见 PickCaseOrgControls.vue（挑选树与购物车四视图共用） */
.pcol-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.pcol-empty i {
  font-size: 36px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
}
.pcol-empty p {
  margin: 4px 0;
  font-size: 13px;
}
.pcol-buckets {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}
.pcol-bucket {
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-card);
  overflow: hidden;
  background: #fff;
}
.pcol-bucket-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: var(--color-slate-50, #f8fafc);
  border-bottom: 1px solid var(--color-slate-200, #e2e8f0);
}
.pcol-bucket-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, #1e293b);
}
.pcol-bucket-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 11px;
  font-weight: 500;
}
.pcol-bucket-body {
  padding: 6px 8px;
}
.pcol-subgroup + .pcol-subgroup {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--color-slate-200, #e2e8f0);
}
.pcol-subgroup-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}
.pcol-subgroup-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground, #1e293b);
}
.pcol-subgroup-count {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-slate-500, #64748b);
}
.pcol-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  margin-right: 4px;
  vertical-align: middle;
}
/* 兜底桶弱化（「未设置标签」/「未分组」） */
.pcol-muted .pcol-bucket-name,
.pcol-muted .pcol-subgroup-name {
  color: var(--color-slate-400, #94a3b8);
}
</style>
