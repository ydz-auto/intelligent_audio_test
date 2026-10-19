<template>
  <div class="pt-row-wrap">
    <div
      class="pt-row"
      :class="{ 'pt-row--leaf': node.level === 'leaf' }"
      :style="{ paddingLeft: `${depth * 16 + 8}px` }"
    >
      <!-- 展开/收起 -->
      <button
        v-if="node.children.length > 0"
        class="pt-chevron"
        :class="{ 'pt-chevron--open': expanded }"
        @click="emit('toggle-expand', node.key)"
      >
        <i class="fas fa-chevron-right"></i>
      </button>
      <span v-else class="pt-chevron pt-chevron--placeholder"></span>

      <!-- 节点三态勾选（R1/R2；叶行不显示节点勾选框） -->
      <label
        v-if="node.children.length > 0"
        class="pt-check"
        @click.stop
      >
        <input
          type="checkbox"
          class="pt-checkbox"
          :checked="state === 'checked'"
          :indeterminate="state === 'indeterminate'"
          @change="emit('toggle-node', node)"
        />
      </label>

      <span class="pt-icon" :class="iconClass"><i :class="iconName"></i></span>
      <span class="pt-name" :title="node.name">{{ node.name }}</span>
      <!-- INT-796 §3.7.1：用例级卡片元信息（CaseIdBadge + 算法徽章；tags/时长待 §11-7 落地后补） -->
      <CaseIdBadge
        v-if="node.level === 'case'"
        :case-id="node.id"
        class="pt-case-badge"
      />
      <span
        v-if="node.level === 'case' && node.algorithmType"
        class="pt-alg-badge"
        :title="`算法：${getAlgorithmName(node.algorithmType)}`"
      >
        {{ getAlgorithmName(node.algorithmType) }}
      </span>
      <span v-if="node.children.length > 0" class="pt-count">{{ node.count }} 条</span>
    </div>

    <!-- 结果行叶（resultType 级下钻） -->
    <div v-if="node.level === 'resultType' || (node.children.length === 0 && node.level === 'leaf')">
      <label
        v-for="rid in node.resultIds"
        :key="rid"
        class="pt-leaf"
        :style="{ paddingLeft: `${(depth + 1) * 16 + 8}px` }"
      >
        <input
          type="checkbox"
          class="pt-checkbox"
          :checked="selected.has(rid)"
          @change="emit('toggle-leaf', rid)"
        />
        <span class="pt-leaf-case">{{ leafText(rid, 'case') }}</span>
        <span class="pt-leaf-dim">{{ leafText(rid, 'dim') }}</span>
        <span v-if="leafMeta.get(rid)?.resultType" class="pt-leaf-rt">{{ leafMeta.get(rid)!.resultType }}</span>
        <span class="pt-leaf-status" :class="leafMeta.get(rid)?.executionStatus">
          {{ statusText(leafMeta.get(rid)?.executionStatus) }}
        </span>
        <span class="pt-leaf-eval" :class="leafMeta.get(rid)?.evaluated ? 'evaluated' : 'pending-eval'">
          {{ leafMeta.get(rid)?.evaluated ? '已评估' : '未评估' }}
        </span>
        <span v-if="leafMeta.get(rid)?.createdAt" class="pt-leaf-time">{{ formatTime(leafMeta.get(rid)!.createdAt) }}</span>
        <span v-if="alreadyAdded.has(rid)" class="pt-leaf-added"><i class="fas fa-cart-plus"></i> 已加购</span>
      </label>
    </div>

    <!-- 递归子级 -->
    <div v-if="expanded && node.children.length > 0">
      <PickTreeNodeRow
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :selected="selected"
        :expanded-keys="expandedKeys"
        :already-added="alreadyAdded"
        :leaf-meta="leafMeta"
        :depth="depth + 1"
        @toggle-node="(n) => emit('toggle-node', n)"
        @toggle-expand="(k) => emit('toggle-expand', k)"
        @toggle-leaf="(rid) => emit('toggle-leaf', rid)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/layouts/main.css'

/**
 * PickTreeNodeRow —— 挑选树节点行（递归组件）。
 * 节点三态由 pickTree.nodeState 派生；叶行勾选直接操作 result_id。
 */
import { computed } from 'vue';
import { nodeState } from './pickTree';
import type { PickTreeNode, NodeCheckState } from './pickTree';
import type { PickCandidate } from '../../../infrastructure/api/cherryPickApi';
import CaseIdBadge from '../../common/CaseIdBadge.vue';

/** 算法类型中文名（§3.6 裁定②「算法徽章」；与算法配置页同名映射同源，缺省回退原始值） */
const ALGORITHM_LABEL: Record<string, string> = {
  asr: 'ASR',
  tts: 'TTS',
  speaker_recognition: '说话人识别',
  speaker_verification: '声纹验证',
  speaker_identification: '说话人识别',
};

function getAlgorithmName(type: string | null | undefined): string {
  if (!type) return '';
  return ALGORITHM_LABEL[type] ?? type;
}

/** 叶行时间（mono 口径，YYYY-MM-DD HH:mm） */
function formatTime(iso?: string | null): string {
  if (!iso) return '';
  const t = iso.replace('T', ' ').slice(0, 16);
  return t;
}

const props = defineProps<{
  node: PickTreeNode;
  selected: ReadonlySet<number>;
  expandedKeys: ReadonlySet<string>;
  alreadyAdded: ReadonlySet<number>;
  leafMeta: Map<number, PickCandidate>;
  depth: number;
}>();

const emit = defineEmits<{
  (e: 'toggle-node', node: PickTreeNode): void;
  (e: 'toggle-expand', key: string): void;
  (e: 'toggle-leaf', resultId: number): void;
}>();

defineOptions({ name: 'PickTreeNodeRow' });

const state = computed<NodeCheckState>(() => nodeState(props.node, props.selected));
const expanded = computed(() => props.expandedKeys.has(props.node.key));

const iconClass = computed(() => ({
  'pt-icon--task': props.node.level === 'task',
  'pt-icon--case': props.node.level === 'case',
  'pt-icon--device': props.node.level === 'device' && props.node.kind === 'device',
  'pt-icon--api': props.node.level === 'device' && props.node.kind === 'api',
  'pt-icon--rt': props.node.level === 'resultType',
}));
const iconName = computed(() => {
  switch (props.node.level) {
    case 'task': return 'fas fa-tasks';
    case 'case': return 'fas fa-list-check';
    case 'device': return props.node.kind === 'api' ? 'fas fa-arrow-right-arrow-left' : 'fas fa-mobile-screen';
    case 'resultType': return 'fas fa-tag';
    default: return 'fas fa-dot-circle';
  }
});

function leafText(rid: number, field: 'case' | 'dim'): string {
  const m = props.leafMeta.get(rid);
  if (!m) return `#${rid}`;
  if (field === 'case') return m.caseName || m.caseId || `#${rid}`;
  return m.deviceId != null
    ? (m.deviceName || `设备 ${m.deviceId}`)
    : (m.apiName || `API ${m.apiId}`);
}

function statusText(status?: string | null): string {
  switch (status) {
    case 'completed': return '执行完成';
    case 'failed': return '执行失败';
    case 'stopped': return '已停止';
    case 'running': return '执行中';
    case 'pending': return '待执行';
    default: return status || '-';
  }
}
</script>

<style scoped>
.pt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--border-radius-md);
  cursor: pointer;
}
.pt-row:hover {
  background: var(--color-slate-50, #f8fafc);
}
.pt-row--leaf {
  font-size: 13px;
}
.pt-chevron {
  width: 16px;
  height: 16px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--color-slate-400, #94a3b8);
  transition: transform 0.15s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.pt-chevron--open {
  transform: rotate(90deg);
}
.pt-chevron--placeholder {
  visibility: hidden;
}
.pt-check {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.pt-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #ff6a00);
}
.pt-icon {
  width: 18px;
  color: var(--color-slate-400, #94a3b8);
  flex-shrink: 0;
  font-size: 13px;
}
.pt-icon--task { color: var(--primary, #ff6a00); }
.pt-icon--case { color: #3b82f6; }
.pt-icon--device { color: #10b981; }
.pt-icon--api { color: #8b5cf6; }
.pt-icon--rt { color: #f59e0b; }
.pt-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--foreground, #1e293b);
}
.pt-count {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--border-radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 11px;
  font-weight: 500;
}
/* INT-796 §3.7.1：用例级 CaseIdBadge / 算法徽章（卡片级元信息，§11-7 剩余项落地前最小呈现） */
.pt-case-badge {
  flex-shrink: 0;
  font-size: 11px;
  margin-left: 2px;
}
.pt-alg-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--border-radius-full);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-600, #475569);
  font-size: 11px;
  font-weight: 500;
}
.pt-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.pt-leaf:hover {
  background: var(--color-slate-50, #f8fafc);
}
.pt-leaf-case { color: var(--foreground, #1e293b); min-width: 90px; }
.pt-leaf-dim { color: var(--color-slate-500, #64748b); min-width: 80px; }
.pt-leaf-rt {
  padding: 0 6px;
  border-radius: var(--border-radius-sm);
  background: var(--color-amber-50, #fffbeb);
  color: #b45309;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}
/* P3（UX 审计）：状态徽章改走 tokens 与 TaskCard exec-status-badge 同源，去硬编码 hex */
.pt-leaf-status {
  padding: 1px 6px;
  border-radius: var(--border-radius-full);
  font-size: 11px;
}
.pt-leaf-status.completed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.pt-leaf-status.failed { background: var(--color-red-100); color: var(--color-red-600); }
.pt-leaf-status.stopped { background: var(--color-gray-100); color: var(--color-gray-500); }
.pt-leaf-eval {
  padding: 1px 6px;
  border-radius: var(--border-radius-full);
  font-size: 11px;
}
.pt-leaf-eval.evaluated { background: var(--color-blue-100); color: var(--color-blue-600); }
.pt-leaf-eval.pending-eval { background: var(--color-slate-100); color: var(--color-slate-500); }
.pt-leaf-added {
  color: var(--primary, #ff6a00);
  font-size: 11px;
}
.pt-leaf-time {
  color: var(--color-slate-400, #94a3b8);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  margin-left: auto;
}
</style>
