<template>
  <div class="cpw">
    <!-- 头部：流程指示（挑选 → 购物车 → 复核 → 下单）+ 返回列表 -->
    <div class="cpw-header">
      <div class="cpw-steps">
        <span
          v-for="(s, i) in STEPS"
          :key="s.key"
          class="cpw-step"
          :class="{ active: step === s.key, done: stepIndex > i }"
          @click="goStep(s.key)"
        >
          <i v-if="stepIndex > i" class="fas fa-check"></i>
          <i v-else :class="s.icon"></i>
          {{ s.label }}
        </span>
      </div>
      <button class="cpw-back" @click="emit('close')"><i class="fas fa-arrow-left"></i> 返回列表</button>
    </div>

    <!-- 步骤 1：挑选 -->
    <div v-if="step === 'pick'" class="cpw-body">
      <!-- 筛选栏 -->
      <div class="cpw-filter-bar">
        <input
          v-model="filters.caseKeyword"
          class="cpw-input"
          placeholder="搜索用例名称或 ID"
          @input="debouncedLoad"
        />
        <select v-model="filters.taskIds" class="cpw-input" multiple size="1" :title="taskIdsLabel">
          <option v-for="t in pickableTasks" :key="t.id" :value="String(t.id)">{{ t.name }}</option>
        </select>
        <select v-model="filters.deviceIds" class="cpw-input" multiple size="1" :title="deviceIdsLabel">
          <option v-for="d in deviceOptions" :key="d.id" :value="String(d.id)">{{ d.name }}</option>
        </select>
        <select v-model="filters.resultTypes" class="cpw-input" multiple size="1" :title="resultTypesLabel">
          <option v-for="rt in resultTypeOptions" :key="rt" :value="rt">{{ rt }}</option>
        </select>
        <select v-model="filters.executionStatus" class="cpw-input">
          <option value="">全部执行状态</option>
          <option value="completed">执行完成</option>
          <option value="failed">执行失败</option>
          <option value="stopped">已停止</option>
        </select>
        <select v-model="filters.evaluationStatus" class="cpw-input">
          <option value="">全部评估状态</option>
          <option value="evaluated">已评估</option>
          <option value="pending">未评估</option>
        </select>
        <select v-model="filters.timeRange" class="cpw-input">
          <option value="all">全部时间</option>
          <option value="today">今日</option>
          <option value="yesterday">昨日</option>
          <option value="week">近7天</option>
          <option value="month">近30天</option>
        </select>
        <button class="cpw-btn" @click="resetFilters"><i class="fas fa-undo"></i> 重置</button>
      </div>

      <!-- 视图切换（INT-796 §3.6 裁定③：树形｜用例视角｜平铺；默认树形，多任务绝不默认平铺） -->
      <div class="cpw-toolbar">
        <div class="cpw-view-switch">
          <button class="cpw-btn" :class="{ active: viewMode === 'tree' }" @click="viewMode = 'tree'"><i class="fas fa-sitemap"></i> 树形</button>
          <button class="cpw-btn" :class="{ active: viewMode === 'case' }" @click="viewMode = 'case'"><i class="fas fa-list-check"></i> 用例视角</button>
          <button class="cpw-btn" :class="{ active: viewMode === 'flat' }" @click="viewMode = 'flat'"><i class="fas fa-list"></i> 平铺</button>
          <button class="cpw-btn" @click="expandAll"><i class="fas fa-angles-down"></i> 全部展开</button>
          <button class="cpw-btn" @click="collapseAll"><i class="fas fa-angles-up"></i> 全部收起</button>
        </div>
        <span class="cpw-toolbar-info">已选 {{ selectedResultIds.size }} 条 / 共 {{ visibleTotal }} 条</span>
      </div>

      <!-- 树形（任务视角）/ 用例视角 / 平铺 -->
      <div v-if="viewMode === 'tree'" class="cpw-tree">
        <PickTree
          :roots="treeRoots"
          :selected="selectedResultIds"
          :expanded-keys="expandedKeys"
          :already-added="resultIdSet"
          :leaf-meta="leafMeta"
          @toggle-node="onToggleNode"
          @toggle-expand="onToggleExpand"
          @toggle-leaf="onToggleLeaf"
        />
      </div>
      <div v-else-if="viewMode === 'case'" class="cpw-tree">
        <PickTree
          :roots="caseViewRoots"
          :selected="selectedResultIds"
          :expanded-keys="expandedKeys"
          :already-added="resultIdSet"
          :leaf-meta="leafMeta"
          @toggle-node="onToggleNode"
          @toggle-expand="onToggleExpand"
          @toggle-leaf="onToggleLeaf"
        />
      </div>
      <div v-else class="cpw-flat">
        <div v-if="loadingCandidates" class="cpw-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载执行结果…</div>
        <div v-else-if="filteredCandidates.length === 0" class="cpw-empty">
          <i class="fas fa-inbox"></i>
          <p>无符合条件的执行结果</p>
          <p class="cpw-empty-hint">仅已完成、执行失败、已停止的终态任务可挑选，默认剔除已删除用例的结果</p>
        </div>
        <label v-for="item in filteredCandidates" :key="item.resultId" class="cpw-leaf">
          <input type="checkbox" class="cpw-checkbox"
                 :checked="selectedResultIds.has(item.resultId)"
                 @change="onToggleLeaf(item.resultId)" />
          <span class="cpw-leaf-case">{{ item.caseName || item.caseId }}</span>
          <span class="cpw-leaf-dim">{{ item.deviceId != null ? (item.deviceName || `设备 ${item.deviceId}`) : (item.apiName || `API ${item.apiId}`) }}</span>
          <span v-if="item.resultType" class="cpw-leaf-rt">{{ item.resultType }}</span>
          <span class="cpw-leaf-status" :class="item.executionStatus">{{ statusText(item.executionStatus) }}</span>
          <span class="cpw-leaf-eval" :class="item.evaluated ? 'evaluated' : 'pending-eval'">{{ item.evaluated ? '已评估' : '未评估' }}</span>
          <span v-if="resultIdSet.has(item.resultId)" class="cpw-leaf-added"><i class="fas fa-cart-plus"></i> 已加购</span>
        </label>
      </div>

      <div v-if="candidateTotal > candidates.length" class="cpw-pagination">
        <button class="cpw-btn" :disabled="filters.page <= 1" @click="filters.page--; loadCandidates()">上一页</button>
        <span>第 {{ filters.page }} 页 / 共 {{ pages }} 页</span>
        <button class="cpw-btn" :disabled="filters.page >= pages" @click="filters.page++; loadCandidates()">下一页</button>
      </div>

      <!-- 已选汇总条（sticky） -->
      <div class="cpw-summary-bar">
        <span class="cpw-summary-info">
          已选 {{ selectedResultIds.size }} 条结果 · 来自 {{ selectedTaskCount }} 个任务 · 覆盖 {{ selectedDeviceCount }} 台设备
        </span>
        <button class="cpw-btn" @click="selectAllCurrentFilter"><i class="fas fa-check-double"></i> 全选当前筛选</button>
        <button class="cpw-btn" @click="invertCurrent"><i class="fas fa-exchange-alt"></i> 反选</button>
        <button class="cpw-btn" @click="clearSelection"><i class="fas fa-eraser"></i> 清空</button>
        <button class="cpw-btn cpw-btn-primary" :disabled="selectedResultIds.size === 0" @click="commitPick">
          <i class="fas fa-cart-plus"></i> 加入购物车（{{ selectedResultIds.size }}）
        </button>
      </div>
    </div>

    <!-- 步骤 2：购物车 -->
    <div v-else-if="step === 'cart'" class="cpw-body">
      <div class="cpw-toolbar">
        <span class="cpw-toolbar-info">共 {{ cartCount }} 条（{{ invalidCount }} 条失效）</span>
        <button v-if="selectedItemIds.size > 0" class="cpw-btn cpw-btn-danger" @click="removeSelectedItems">
          <i class="fas fa-trash"></i> 移除已选（{{ selectedItemIds.size }}）
        </button>
        <button v-if="invalidCount > 0" class="cpw-btn" @click="removeInvalid">
          <i class="fas fa-trash-alt"></i> 移除失效条目（{{ invalidCount }}）
        </button>
        <button class="cpw-btn" @click="clearAllCart"><i class="fas fa-trash"></i> 清空购物车</button>
        <button class="cpw-btn" @click="openSaveSet"><i class="fas fa-save"></i> 另存为挑选集</button>
      </div>

      <div v-if="cartLoading" class="cpw-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载购物车…</div>
      <div v-else-if="cartCount === 0" class="cpw-empty"><i class="fas fa-shopping-cart"></i> 购物车为空</div>
      <div v-else class="cpw-cart-tree">
        <CartTree
          :roots="cartTreeRoots"
          :selected="selectedItemIds"
          :expanded-keys="cartExpandedKeys"
          :leaf-meta="cartLeafMeta"
          :manageable="true"
          @toggle-node="onToggleCartNode"
          @toggle-expand="onToggleCartExpand"
          @toggle-leaf="toggleCartItem"
          @remove-leaf="onRemoveCartLeaf"
          @remove-group="onRemoveCartGroupNode"
        />
      </div>

      <div class="cpw-sets" v-if="sets.length > 0">
        <h4><i class="fas fa-layer-group"></i> 我的挑选集</h4>
        <div v-for="s in sets" :key="s.setId" class="cpw-set-row">
          <span class="cpw-set-name">{{ s.name }}</span>
          <span class="pt-count">{{ s.itemCount }} 条</span>
          <button class="cpw-btn cpw-btn-sm" @click="restoreSet(s.setId)"><i class="fas fa-undo"></i> 恢复进购物车</button>
          <button class="cpw-btn cpw-btn-sm" @click="onRemoveSet(s.setId)"><i class="fas fa-trash-alt"></i></button>
        </div>
      </div>
    </div>

    <!-- 步骤 3：复核 -->
    <div v-else-if="step === 'review'" class="cpw-body">
      <div class="cpw-review-summary">
        <div class="cpw-stat-badge"><b>{{ preview?.totalResults ?? 0 }}</b><span>结果（条）</span></div>
        <div class="cpw-stat-badge"><b>{{ preview?.sourceTaskCount ?? 0 }}</b><span>来源任务</span></div>
        <div class="cpw-stat-badge"><b>{{ preview?.deviceIds?.length ?? 0 }}</b><span>设备（台）</span></div>
        <div class="cpw-stat-badge"><b>{{ preview?.caseCount ?? 0 }}</b><span>用例（个）</span></div>
      </div>

      <div v-if="invalidCount > 0" class="cpw-alert cpw-alert--warn">
        <i class="fas fa-triangle-exclamation"></i>
        {{ invalidCount }} 条购物车条目已失效（源结果被删除），下单时将跳过，可一键移除
        <button class="cpw-btn cpw-btn-sm" @click="removeInvalid">移除失效条目（{{ invalidCount }}）</button>
      </div>
      <div v-if="preview?.duplicates?.length" class="cpw-alert cpw-alert--info">
        <i class="fas fa-circle-info"></i>
        同设备同用例存在多来源结果 {{ preview.duplicates.length }} 组，合并将全部保留并标注来源
      </div>
      <div v-if="preview?.configInconsistent" class="cpw-alert cpw-alert--warn">
        <i class="fas fa-triangle-exclamation"></i>
        {{ preview.sourceTaskCount }} 个来源任务的任务级配置（{{ (preview.configFields || []).join('、') || '算法参数' }}）不一致，新任务默认取首个来源任务配置，可展开「任务级配置」覆盖
      </div>

      <div v-if="cartCount === 0" class="cpw-empty"><i class="fas fa-shopping-cart"></i> 购物车为空</div>
      <div v-else class="cpw-cart-tree">
        <CartTree
          :roots="cartTreeRoots"
          :selected="selectedItemIds"
          :expanded-keys="cartExpandedKeys"
          :leaf-meta="cartLeafMeta"
          :manageable="true"
          @toggle-node="onToggleCartNode"
          @toggle-expand="onToggleCartExpand"
          @toggle-leaf="toggleCartItem"
          @remove-leaf="onRemoveCartLeaf"
          @remove-group="onRemoveCartGroupNode"
        />
      </div>
    </div>

    <!-- 步骤 4：下单 -->
    <div v-else class="cpw-body">
      <div class="cpw-checkouts">
        <div class="cpw-checkout-card" :class="{ active: action === 'merge' }" @click="action = 'merge'">
          <div class="cpw-checkout-head">
            <i class="fas fa-object-group"></i> 合并生成新任务
            <span class="cpw-checkout-desc">挑选结果合并为新任务与报告，源任务保持原样</span>
          </div>
          <div v-if="action === 'merge'" class="cpw-checkout-form" @click.stop>
            <div class="cpw-preview" v-if="preview">
              <div class="cpw-preview-row"><span>结果总数</span><b>{{ preview.totalResults }}</b></div>
              <div class="cpw-preview-row"><span>来源任务</span><b>{{ preview.sourceTaskCount }} 个</b></div>
              <div class="cpw-preview-row"><span>设备</span><b>{{ preview.deviceNames.join('、') || '-' }}</b></div>
              <div class="cpw-preview-row"><span>用例数</span><b>{{ preview.caseCount }}</b></div>
              <div class="cpw-preview-row" v-if="preview.duplicates.length > 0">
                <span>重复提示</span>
                <b>{{ preview.duplicates.length }} 组同设备同用例多来源结果（默认全保留并标注来源）</b>
              </div>
              <div class="cpw-preview-row warn" v-if="invalidCount > 0">
                <span>失效条目</span><b>{{ invalidCount }} 条（下单时自动跳过）</b>
              </div>
              <div class="cpw-preview-row warn" v-if="preview.configInconsistent">
                <span>配置差异</span>
                <b>{{ preview.sourceTaskCount }} 个来源任务的任务级配置（{{ (preview.configFields || []).join('、') || '算法参数' }}）不一致，默认取首个来源任务，提交需确认</b>
              </div>
            </div>
            <input v-model="mergeName" class="cpw-input" placeholder="新任务名称（必填）" />
            <input v-model="mergeDescription" class="cpw-input" placeholder="新任务描述（可选）" />
            <div class="cpw-config-toggle" @click="showMergeConfig = !showMergeConfig">
              <i class="fas" :class="showMergeConfig ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
              任务级配置（可选，默认取首个来源任务）
            </div>
            <div v-if="showMergeConfig" class="cpw-config-fields">
              <input v-model="mergeAlgorithmType" class="cpw-input" placeholder="算法类型覆盖（如 asr / tts / translation）" />
              <textarea v-model="mergeAlgorithmParams" class="cpw-input cpw-textarea" placeholder='算法参数覆盖（JSON，如 {"model":"xx"}）' rows="2"></textarea>
              <textarea v-model="mergeConfig" class="cpw-input cpw-textarea" placeholder='任务配置覆盖（JSON，可选）' rows="2"></textarea>
            </div>
          </div>
        </div>

        <div class="cpw-checkout-card" :class="{ active: action === 'reexecute' }" @click="action = 'reexecute'">
          <div class="cpw-checkout-head">
            <i class="fas fa-redo"></i> 重新执行
            <span class="cpw-checkout-desc">按所选结果的用例×设备集合创建重执行任务并启动</span>
          </div>
          <div v-if="action === 'reexecute'" class="cpw-checkout-form" @click.stop>
            <input v-model="reexecuteName" class="cpw-input" placeholder="重执行任务名称（可选，默认自动命名）" />
          </div>
        </div>

        <div class="cpw-checkout-card" :class="{ active: action === 'reevaluate' }" @click="action = 'reevaluate'">
          <div class="cpw-checkout-head">
            <i class="fas fa-sync-alt"></i> 重新评估
            <span class="cpw-checkout-desc">对所选结果按来源任务逐个发起重新评估（不重跑执行）</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="cpw-footer">
      <button v-if="step !== 'pick'" class="cpw-btn" @click="prevStep"><i class="fas fa-arrow-left"></i> 上一步</button>
      <span class="cpw-footer-spacer"></span>
      <button v-if="step === 'pick'" class="cpw-btn cpw-btn-primary" :disabled="selectedResultIds.size === 0" @click="commitPick">
        <i class="fas fa-cart-plus"></i> 加入购物车（{{ selectedResultIds.size }}）
      </button>
      <button v-else-if="step === 'cart'" class="cpw-btn cpw-btn-primary" :disabled="cartCount === 0" @click="goStep('review')">
        <i class="fas fa-clipboard-check"></i> 去复核（{{ cartCount }}）
      </button>
      <button v-else-if="step === 'review'" class="cpw-btn cpw-btn-primary" :disabled="cartCount === 0" @click="goStep('checkout')">
        <i class="fas fa-flag-checkered"></i> 确认下单（{{ cartCount }}）
      </button>
      <button v-else class="cpw-btn cpw-btn-primary" :disabled="!action || submitting || cartCount === 0" @click="submitCheckout">
        <i class="fas" :class="submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
        {{ submitting ? '下单中…' : '确认下单' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

/**
 * CherryPickWizard —— 挑选合并四步向导（INT-577 §5：挑选 → 购物车 → 复核 → 下单）。
 *
 * 挑选：多级树勾选（R1-R10 由 pickTree.ts 承载）+ 筛选器 + 树形/平铺切换；
 * 购物车：树形分组 + 移除矩阵（单条/整组/批量/失效/清空）+ 另存挑选集；
 * 复核：preview 摘要 + 失效/重复/配置不一致 Alert + 可编辑；
 * 下单：三出口（合并生成新任务[默认]/重新执行/重新评估）+ 任务级配置覆盖 + 强制确认。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { cherryPickApi, tasksApi, devicesApi } from '../../../infrastructure/api';
import type { PickCandidate, PickPreview, PickCheckoutAction, PickCartItem } from '../../../infrastructure/api/cherryPickApi';
import { usePickCart } from '../../../composables/task/usePickCart';
import { useNotification } from '../../../composables/modal/useNotification';
import { useModalControl } from '../../../composables/modal/useModal';
import { MODAL_TYPES } from '../../../composables/modal/constants';
import PickTree from './PickTree.vue';
import CartTree from './CartTree.vue';
import { buildPickTree, buildPickCaseViewTree, toggleNode, selectAll, invertSelection, collectLeafResultIds, type PickTreeNode } from './pickTree';
import { buildCartTree, toggleCartNode, type CartTreeNode } from './cartTree';

const STEPS = [
  { key: 'pick', label: '挑选', icon: 'fas fa-hand-pointer' },
  { key: 'cart', label: '购物车', icon: 'fas fa-cart-shopping' },
  { key: 'review', label: '复核', icon: 'fas fa-clipboard-check' },
  { key: 'checkout', label: '下单', icon: 'fas fa-paper-plane' },
] as const;
type StepKey = (typeof STEPS)[number]['key'];

const props = defineProps<{
  /** INT-577 §2.2：批量「加入挑选」预选任务（任务级粒度整任务加购，等价旧合并任务入口） */
  presetTaskIds?: (number | string)[];
  /** 直达步骤（购物车抽屉「去复核」→ review；缺省 pick） */
  initialStep?: StepKey;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'checked-out', payload: { action: PickCheckoutAction; taskId?: number }): void;
}>();

const notification = useNotification();
const modalControl = useModalControl();
const {
  cart, cartLoading, cartCount, invalidCount, sets, resultIdSet, cartRevision,
  refreshCart, addToCart, removeItem, removeItems, clearCart,
  refreshSets, saveAsSet, restoreSetToCart, deleteSet,
} = usePickCart();

const step = ref<StepKey>(props.initialStep ?? 'pick');
const stepIndex = computed(() => STEPS.findIndex((s) => s.key === step.value));

function goStep(key: StepKey) {
  step.value = key;
  if (key === 'cart') refreshCart();
  if (key === 'review' || key === 'checkout') loadPreview();
}
function prevStep() {
  if (step.value === 'checkout') step.value = 'review';
  else if (step.value === 'review') step.value = 'cart';
  else if (step.value === 'cart') step.value = 'pick';
}

// ===== 步骤 1：挑选 =====

const pickableTasks = ref<Array<{ id: number; name: string }>>([]);
const deviceOptions = ref<Array<{ id: number; name: string }>>([]);
// INT-577 §10 #5：筛选会话级记忆（sessionStorage，刷新保留、跨会话不持久化）
const FILTERS_STORAGE_KEY = 'int577-pick-filters-v1';
const filters = reactive<{
  caseKeyword: string;
  taskIds: string[];
  deviceIds: string[];
  resultTypes: string[];
  executionStatus: string;
  evaluationStatus: string;
  timeRange: string;
  page: number;
}>({
  caseKeyword: '',
  taskIds: [],
  deviceIds: [],
  resultTypes: [],
  executionStatus: '',
  evaluationStatus: '',
  timeRange: 'all',
  page: 1,
});

function loadStoredFilters() {
  try {
    const raw = sessionStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return;
    const stored = JSON.parse(raw) as Partial<typeof filters>;
    if (stored && typeof stored === 'object') {
      filters.caseKeyword = String(stored.caseKeyword ?? '');
      filters.taskIds = Array.isArray(stored.taskIds) ? stored.taskIds.map(String) : [];
      filters.deviceIds = Array.isArray(stored.deviceIds) ? stored.deviceIds.map(String) : [];
      filters.resultTypes = Array.isArray(stored.resultTypes) ? stored.resultTypes.map(String) : [];
      filters.executionStatus = String(stored.executionStatus ?? '');
      filters.evaluationStatus = String(stored.evaluationStatus ?? '');
      filters.timeRange = String(stored.timeRange ?? 'all');
    }
  } catch {
    // 存储异常不阻断挑选（容错口径）
  }
}
let filterSaveTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleFilterSave() {
  if (filterSaveTimer) clearTimeout(filterSaveTimer);
  filterSaveTimer = setTimeout(() => {
    try {
      sessionStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify({
        caseKeyword: filters.caseKeyword,
        taskIds: filters.taskIds,
        deviceIds: filters.deviceIds,
        resultTypes: filters.resultTypes,
        executionStatus: filters.executionStatus,
        evaluationStatus: filters.evaluationStatus,
        timeRange: filters.timeRange,
      }));
    } catch {
      // 存储异常不阻断（容错口径）
    }
  }, 400);
}
loadStoredFilters();
const candidates = ref<PickCandidate[]>([]);
const candidateTotal = ref(0);
const pages = ref(0);
const loadingCandidates = ref(false);
const selectedResultIds = ref<Set<number>>(new Set());
const expandedKeys = ref<Set<string>>(new Set());
/** INT-796 §3.6 裁定①/③：默认树形（任务视角）；用例视角/平铺仅显式切换 */
const viewMode = ref<'tree' | 'case' | 'flat'>('tree');

/** 结果类型客户端过滤（UX 审计 P2 修复）：后端候选查询不下发 result_type 参数，
 * 取审计建议方案①——loadCandidates 后按 filters.resultTypes 过滤候选行/树；
 * 筛选与勾选解耦（§6.2）不变，已选项跨筛选保留。 */
const filteredCandidates = computed(() => {
  if (!filters.resultTypes.length) return candidates.value;
  return candidates.value.filter((c) => filters.resultTypes.includes(c.resultType ?? 'default'));
});
/** 展示计数：结果类型客户端过滤时以过滤后当前页为准（跨页全选降级口径），否则后端 total */
const visibleTotal = computed(() =>
  filters.resultTypes.length ? filteredCandidates.value.length : candidateTotal.value);

const treeRoots = computed(() => buildPickTree(filteredCandidates.value));
/** INT-796 §3.7.3：用例视角树（跨任务按用例聚合；与任务视角共享同一 selectedResultIds） */
const caseViewRoots = computed(() => buildPickCaseViewTree(filteredCandidates.value));
/** 累计候选元数据（跨页累加不清理：跨页已选结果的任务/设备计数、R10 标记均可用） */
const knownMeta = ref<Map<number, PickCandidate>>(new Map());
const leafMeta = computed(() => knownMeta.value);
const resultTypeOptions = computed(() => {
  const set = new Set<string>();
  for (const c of candidates.value) {
    if (c.resultType) set.add(c.resultType);
  }
  return [...set].sort();
});
const taskIdsLabel = computed(() => filters.taskIds.length ? `来源任务：${filters.taskIds.length} 个` : '来源任务');
const deviceIdsLabel = computed(() => filters.deviceIds.length ? `设备：${filters.deviceIds.length} 个` : '设备');
const resultTypesLabel = computed(() => filters.resultTypes.length ? `结果类型：${filters.resultTypes.length} 个` : '结果类型');

/** 已选来源任务/设备去重计数（汇总条；跨页已选经 knownMeta 累计元数据推算） */
const selectedTaskCount = computed(() => {
  const s = new Set<number>();
  for (const rid of selectedResultIds.value) {
    const m = knownMeta.value.get(rid);
    if (m) s.add(m.taskId);
  }
  return s.size;
});
const selectedDeviceCount = computed(() => {
  const s = new Set<string>();
  for (const rid of selectedResultIds.value) {
    const m = knownMeta.value.get(rid);
    if (m) s.add(`d:${m.deviceId ?? 'api:' + (m.apiId ?? '')}`);
  }
  return s.size;
});

/** 预选任务：任务级整任务预选（批量「加入挑选」入口，R7 语义） */
if (props.presetTaskIds?.length) {
  filters.taskIds = props.presetTaskIds.map(String);
}

let loadTimer: ReturnType<typeof setTimeout> | null = null;
function debouncedLoad() {
  if (loadTimer) clearTimeout(loadTimer);
  loadTimer = setTimeout(loadCandidates, 300);
}

async function loadCandidates() {
  loadingCandidates.value = true;
  try {
    const page = await cherryPickApi.listCandidates({
      taskIds: filters.taskIds.length ? filters.taskIds.map(Number) : [],
      deviceIds: filters.deviceIds.length ? filters.deviceIds.map(Number) : [],
      caseKeyword: filters.caseKeyword.trim() || undefined,
      executionStatus: filters.executionStatus || undefined,
      evaluationStatus: filters.evaluationStatus || undefined,
      startDate: timeRangeStart(),
      endDate: timeRangeEnd(),
      page: filters.page,
      perPage: 50,
    });
    candidates.value = page.items ?? [];
    candidateTotal.value = page.total ?? 0;
    // 后端候选接口返 page/per_page（无 pages），页数本地推算
    pages.value = Math.max(1, Math.ceil((page.total ?? 0) / (page.perPage || 50)));
    // 跨页累加候选元数据（不清理：跨页已选计数/树叶元数据依赖）
    const meta = new Map(knownMeta.value);
    for (const c of candidates.value) meta.set(c.resultId, c);
    knownMeta.value = meta;
    // 筛选与勾选解耦（§6.2）：筛选变化不清空已选项；仅收起至任务级
    collapseAll();
  } catch (error) {
    console.error('Failed to load pick candidates:', error);
    candidates.value = [];
  } finally {
    loadingCandidates.value = false;
  }
}

function timeRangeStart(): string | undefined {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  switch (filters.timeRange) {
    case 'today': return today.toISOString();
    case 'yesterday': return new Date(today.getTime() - 86400000).toISOString();
    case 'week': return new Date(today.getTime() - 7 * 86400000).toISOString();
    case 'month': return new Date(today.getTime() - 30 * 86400000).toISOString();
    default: return undefined;
  }
}
function timeRangeEnd(): string | undefined {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return filters.timeRange === 'yesterday' ? today.toISOString() : undefined;
}

async function loadOptions() {
  try {
    const data = await tasksApi.getAll({ perPage: 100, status: undefined }) as any;
    const FINISHED = ['completed', 'failed', 'stopped'];
    pickableTasks.value = (data.items ?? [])
      .filter((t: any) => FINISHED.includes(String(t.status)))
      .map((t: any) => ({ id: Number(t.id), name: t.name }));
    try {
      const devices = await devicesApi.getAllFlat({ per_page: 100 });
      deviceOptions.value = (devices ?? []).map((d: any) => ({
        id: Number(d.id), name: d.name ?? `设备 ${d.id}`,
      }));
    } catch (deviceErr) {
      console.error('Failed to load device options:', deviceErr);
      deviceOptions.value = [];
    }
  } catch (error) {
    console.error('Failed to load pick options:', error);
  }
}

// ===== 勾选联动（R1-R10） =====

function onToggleNode(node: PickTreeNode) {
  selectedResultIds.value = toggleNode(node, selectedResultIds.value);
}

function onToggleLeaf(resultId: number) {
  const next = new Set(selectedResultIds.value);
  if (next.has(resultId)) next.delete(resultId); else next.add(resultId);
  selectedResultIds.value = next;
}

function onToggleExpand(key: string) {
  const next = new Set(expandedKeys.value);
  if (next.has(key)) next.delete(key); else next.add(key);
  expandedKeys.value = next;
}

function expandAll() {
  const keys = new Set<string>();
  const roots = viewMode.value === 'case' ? caseViewRoots.value : treeRoots.value;
  const walk = (nodes: PickTreeNode[]) => {
    for (const n of nodes) {
      if (n.children.length) keys.add(n.key);
      walk(n.children);
    }
  };
  walk(roots);
  expandedKeys.value = keys;
}

function collapseAll() {
  expandedKeys.value = new Set();
}

function clearSelection() {
  selectedResultIds.value = new Set();
}

function invertCurrent() {
  const leaves = viewMode.value === 'tree'
    ? collectLeafResultIds(treeRoots.value)
    : viewMode.value === 'case'
      ? collectLeafResultIds(caseViewRoots.value)
      : filteredCandidates.value.map((c) => c.resultId);
  selectedResultIds.value = invertSelection(leaves, selectedResultIds.value);
}

/** R9 全选当前筛选：跨页全选（§11-4 select-all，未落地前降级当前已加载）。
 * 结果类型为客户端过滤（P2 修复口径）：后端 select-all 不支持 result_type 下发，
 * 命中集合以当前已加载且已过滤的树为准（跨页全选降级，与展示一致）。 */
async function selectAllCurrentFilter() {
  if (filters.resultTypes.length) {
    selectedResultIds.value = selectAll(collectLeafResultIds(treeRoots.value), selectedResultIds.value);
    return;
  }
  try {
    const res = await cherryPickApi.selectAllCandidates({
      taskIds: filters.taskIds.length ? filters.taskIds.map(Number) : [],
      deviceIds: filters.deviceIds.length ? filters.deviceIds.map(Number) : [],
      caseKeyword: filters.caseKeyword.trim() || undefined,
      executionStatus: filters.executionStatus || undefined,
      evaluationStatus: filters.evaluationStatus || undefined,
      startDate: timeRangeStart(),
      endDate: timeRangeEnd(),
    });
    selectedResultIds.value = selectAll(res.resultIds ?? [], selectedResultIds.value);
  } catch (error) {
    console.error('select-all failed, fallback to current page:', error);
    selectedResultIds.value = selectAll(
      collectLeafResultIds(treeRoots.value), selectedResultIds.value);
  }
}

async function commitPick() {
  if (selectedResultIds.value.size === 0) return;
  try {
    const outcome = await addToCart([...selectedResultIds.value]);
    const added = outcome.added?.length ?? 0;
    if (outcome.missing?.length) {
      notification.warning(`已加入 ${added} 条，${outcome.missing.length} 条源结果已失效未加入`);
    } else if (outcome.duplicated?.length) {
      notification.success(`已加入购物车 ${added} 条（重复 ${outcome.duplicated.length} 条已跳过）`);
    } else {
      notification.success(`已加入购物车 ${added} 条`);
    }
    selectedResultIds.value = new Set();
    step.value = 'cart';
    await refreshCart();
  } catch (error: any) {
    notification.error(error?.message || '加入购物车失败');
  }
}

function resetFilters() {
  filters.caseKeyword = '';
  filters.taskIds = [];
  filters.deviceIds = [];
  filters.resultTypes = [];
  filters.executionStatus = '';
  filters.evaluationStatus = '';
  filters.timeRange = 'all';
  filters.page = 1;
  loadCandidates();
}

// ===== 步骤 2/3：购物车 =====

/** 购物车树（§4.2 任务→用例→设备/API→result_type 分组，与挑选页同构） */
const cartTreeRoots = computed(() => buildCartTree(cart.value.groups));
const cartLeafMeta = computed(() => {
  const m = new Map<number, PickCartItem>();
  for (const g of cart.value.groups) {
    for (const it of g.items) m.set(it.itemId, it);
  }
  return m;
});
const cartExpandedKeys = ref<Set<string>>(new Set());
/** 购物车树节点自动展开（进入步骤即展开一层便于核对） */
watch(cartTreeRoots, (roots) => {
  const next = new Set(cartExpandedKeys.value);
  for (const r of roots) next.add(r.key);
  cartExpandedKeys.value = next;
}, { immediate: true });

const selectedItemIds = ref<Set<number>>(new Set());

function toggleCartItem(itemId: number) {
  const next = new Set(selectedItemIds.value);
  if (next.has(itemId)) next.delete(itemId); else next.add(itemId);
  selectedItemIds.value = next;
}

function onToggleCartNode(node: CartTreeNode) {
  selectedItemIds.value = toggleCartNode(node, selectedItemIds.value);
}

function onToggleCartExpand(key: string) {
  const next = new Set(cartExpandedKeys.value);
  if (next.has(key)) next.delete(key); else next.add(key);
  cartExpandedKeys.value = next;
}

async function removeOne(itemId: number) {
  try {
    await removeItem(itemId);
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

/** 叶单条移除（CartTree remove-leaf） */
function onRemoveCartLeaf(itemId: number) {
  removeOne(itemId);
}

/** 节点「移除该组」（CartTree remove-group；将移除该节点下全部条目，确认后批量） */
async function onRemoveCartGroupNode(node: CartTreeNode) {
  const label = node.level === 'task' ? '来源任务' : node.level === 'case' ? '用例' : node.level === 'device' ? (node.kind === 'api' ? 'API' : '设备') : '结果类型';
  let confirmed = false;
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '移除该组',
      content: `将移除该${label}「${node.name}」下的 ${node.count} 条结果，是否继续？`,
      confirmText: '移除',
      cancelText: '取消',
    });
  } catch {
    return;
  }
  if (!confirmed) return;
  try {
    await removeItems([...node.itemIds]);
    // 该节点 item_id 已移除，从选中集剔除残留
    const next = new Set(selectedItemIds.value);
    for (const id of node.itemIds) next.delete(id);
    selectedItemIds.value = next;
    notification.success(`已移除 ${node.count} 条`);
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function removeSelectedItems() {
  try {
    await removeItems([...selectedItemIds.value]);
    selectedItemIds.value = new Set();
    notification.success('已移除');
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function removeInvalid() {
  if (cart.value.invalidItemIds.length === 0) return;
  try {
    await removeItems(cart.value.invalidItemIds);
    notification.success('失效条目已移除');
  } catch (error: any) {
    notification.error(error?.message || '移除失败');
  }
}

async function clearAllCart() {
  let confirmed = false;
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '清空购物车',
      content: `将清空购物车全部 ${cartCount.value} 条结果，是否继续？`,
      confirmText: '清空',
      cancelText: '取消',
    });
  } catch {
    return;
  }
  if (!confirmed) return;
  try {
    await clearCart();
    notification.success('购物车已清空');
  } catch (error: any) {
    notification.error(error?.message || '清空失败');
  }
}

async function openSaveSet() {
  let name = '';
  try {
    const result = await modalControl.open(MODAL_TYPES.INPUT_CONFIRM, {
      title: '另存挑选集',
      label: '挑选集名称',
      initialValue: `挑选集_${new Date().toISOString().slice(0, 10)}`,
      hint: '同名允许重复保存',
      confirmText: '保存',
    });
    name = String(result?.value ?? '').trim();
  } catch {
    return;
  }
  if (!name) return;
  try {
    const outcome = await saveAsSet(name);
    notification.success(`挑选集「${outcome.name}」已保存（${outcome.itemCount} 条）`);
  } catch (error: any) {
    notification.error(error?.message || '另存挑选集失败');
  }
}

async function onRemoveSet(setId: number) {
  try {
    await deleteSet(setId);
  } catch (error: any) {
    notification.error(error?.message || '删除挑选集失败');
  }
}

async function restoreSet(setId: number) {
  try {
    const outcome = await restoreSetToCart(setId);
    notification.success(`已恢复 ${outcome.added?.length ?? 0} 条进购物车`);
  } catch (error: any) {
    notification.error(error?.message || '挑选集恢复失败');
  }
}

// ===== 步骤 3/4：复核 + 下单 =====

const preview = ref<PickPreview | null>(null);
const action = ref<PickCheckoutAction>('merge');
const mergeName = ref('');
const mergeDescription = ref('');
const reexecuteName = ref('');
const submitting = ref(false);
const showMergeConfig = ref(false);
const mergeAlgorithmType = ref('');
const mergeAlgorithmParams = ref('');
const mergeConfig = ref('');

async function loadPreview() {
  try {
    preview.value = await cherryPickApi.preview();
  } catch (error: any) {
    preview.value = null;
    notification.warning(error?.message || '合并预览失败（购物车可能为空）');
  }
}

async function submitCheckout() {
  submitting.value = true;
  try {
    if (action.value === 'merge') {
      if (!mergeName.value.trim()) {
        notification.warning('请填写新任务名称');
        return;
      }
      if (preview.value?.configInconsistent) {
        let confirmed = false;
        try {
          confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
            title: '跨任务配置不一致',
            content: `所选结果来自 ${preview.value.sourceTaskCount} 个来源任务，其任务级配置（${(preview.value.configFields ?? []).join('、') || '算法参数'}）不一致。合并新任务将默认取首个来源任务配置，您可展开「任务级配置」覆盖。是否继续合并？`,
            confirmText: '继续合并',
            cancelText: '返回修改',
          });
        } catch {
          return;
        }
        if (!confirmed) return;
      }
      let algorithmParams: Record<string, unknown> | undefined;
      let config: Record<string, unknown> | undefined;
      try {
        algorithmParams = mergeAlgorithmParams.value.trim()
          ? JSON.parse(mergeAlgorithmParams.value)
          : undefined;
      } catch {
        notification.warning('算法参数需为合法 JSON');
        return;
      }
      try {
        config = mergeConfig.value.trim() ? JSON.parse(mergeConfig.value) : undefined;
      } catch {
        notification.warning('任务配置需为合法 JSON');
        return;
      }
      const result = await cherryPickApi.checkout({
        action: 'merge',
        name: mergeName.value.trim(),
        description: mergeDescription.value || undefined,
        algorithm_type: mergeAlgorithmType.value.trim() || undefined,
        algorithm_params: algorithmParams,
        config,
      });
      notification.success(`挑选合并任务已创建（ID ${result.taskId}），可手动生成报告`);
      await refreshCart();
      emit('checked-out', { action: 'merge', taskId: result.taskId });
      emit('close');
    } else if (action.value === 'reexecute') {
      const result = await cherryPickApi.checkout({
        action: 'reexecute',
        name: reexecuteName.value || undefined,
      });
      if (result.started === false) {
        notification.warning(result.taskId ? `重执行任务已创建（ID ${result.taskId}），自动启动失败，请手动启动` : '下单完成');
      } else {
        notification.success(`重执行任务已创建并启动（ID ${result.taskId}）`);
      }
      await refreshCart();
      emit('checked-out', { action: 'reexecute', taskId: result.taskId });
      emit('close');
    } else {
      const result = await cherryPickApi.checkout({ action: 'reevaluate' });
      const failed = result.failed?.length ?? 0;
      if (failed > 0) {
        notification.warning(`已对 ${result.submittedTaskIds?.length ?? 0} 个来源任务发起重新评估，${failed} 个失败（条目已保留）`);
      } else {
        notification.success(`已对 ${result.submittedTaskIds?.length ?? 0} 个来源任务发起重新评估`);
      }
      await refreshCart();
      emit('checked-out', { action: 'reevaluate', taskId: result.submittedTaskIds?.[0] });
      emit('close');
    }
  } catch (error: any) {
    notification.error(error?.message || '下单失败');
  } finally {
    submitting.value = false;
  }
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

onMounted(async () => {
  await Promise.all([loadCandidates(), loadOptions(), refreshCart(), refreshSets()]);
});

// 筛选变化 → 回第一页重拉（勾选保持，§6.2 筛选与勾选解耦）+ 会话级记忆持久化
watch(
  () => [filters.taskIds, filters.deviceIds, filters.resultTypes, filters.executionStatus, filters.evaluationStatus, filters.timeRange, filters.caseKeyword],
  () => {
    filters.page = 1;
    scheduleFilterSave();
    loadCandidates();
  },
);

// 购物车变化（加购/移除/清空/下单）→ 复核摘要重拉（§6.3 复核摘要实时刷新）
watch(() => cartRevision.value, () => {
  if (step.value === 'review' || step.value === 'checkout') loadPreview();
});
</script>

<style scoped>
.cpw {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 420px;
}
.cpw-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-slate-50, #f8fafc);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-slate-200, #e2e8f0);
}
.cpw-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cpw-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-md);
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-500, #64748b);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}
.cpw-step.active {
  background: var(--primary, #ff6a00);
  color: #fff;
}
.cpw-step.done {
  background: var(--color-emerald-100);
  color: var(--color-emerald-600);
}
.cpw-back {
  border: none;
  background: none;
  color: var(--color-slate-500, #64748b);
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.cpw-back:hover {
  color: var(--primary, #ff6a00);
}
.cpw-body {
  min-height: 320px;
}
.cpw-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px;
  background: var(--color-slate-50, #f8fafc);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-slate-200, #e2e8f0);
  margin-bottom: 12px;
}
.cpw-input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  font-size: 13px;
  background: #fff;
  color: var(--foreground, #1e293b);
}
.cpw-input:focus {
  outline: none;
  border-color: var(--primary, #ff6a00);
}
.cpw-textarea {
  height: auto;
  padding: 8px 10px;
  resize: vertical;
  font-family: var(--font-mono, monospace);
}
.cpw-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.cpw-view-switch {
  display: flex;
  align-items: center;
  gap: 4px;
}
.cpw-toolbar-info {
  font-size: 13px;
  color: var(--color-slate-500, #64748b);
}
.cpw-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-md);
  background: #fff;
  color: var(--foreground, #1e293b);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cpw-btn:hover {
  border-color: var(--primary, #ff6a00);
  color: var(--primary, #ff6a00);
}
.cpw-btn.active {
  border-color: var(--primary, #ff6a00);
  background: var(--accent, #fff7ed);
  color: var(--primary, #ff6a00);
}
.cpw-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.cpw-btn-primary {
  background: var(--primary, #ff6a00);
  border-color: var(--primary, #ff6a00);
  color: #fff;
}
.cpw-btn-primary:hover {
  background: var(--primary-hover, #e55d00);
  color: #fff;
}
.cpw-btn-danger {
  border-color: var(--destructive, #dc2626);
  color: var(--destructive, #dc2626);
}
.cpw-btn-danger:hover {
  background: var(--color-red-100);
}
.cpw-btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}
.cpw-tree {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  padding: 8px 0;
}
.cpw-flat {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  padding: 8px 0;
}
.cpw-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--color-slate-400, #94a3b8);
}
.cpw-empty i {
  font-size: 36px;
  color: var(--color-slate-300, #cbd5e1);
  margin-bottom: 8px;
}
.cpw-empty-hint {
  font-size: var(--font-size-xs);
  color: var(--color-slate-400, #94a3b8);
}
.cpw-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}
.cpw-leaf:hover {
  background: var(--color-slate-50, #f8fafc);
}
.cpw-leaf-case { color: var(--foreground, #1e293b); min-width: 90px; }
.cpw-leaf-dim { color: var(--color-slate-500, #64748b); min-width: 80px; }
.cpw-leaf-rt {
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: var(--color-amber-50, #fffbeb);
  color: var(--color-amber-700);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}
/* P3（UX 审计）：状态徽章改走 tokens 与 TaskCard exec-status-badge 同源，去硬编码 hex */
.cpw-leaf-status {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 11px;
}
.cpw-leaf-status.completed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.cpw-leaf-status.failed { background: var(--color-red-100); color: var(--color-red-600); }
.cpw-leaf-status.stopped { background: var(--color-gray-100); color: var(--color-gray-500); }
.cpw-leaf-eval {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 11px;
}
.cpw-leaf-eval.evaluated { background: var(--color-blue-100); color: var(--color-blue-600); }
.cpw-leaf-eval.pending-eval { background: var(--color-slate-100); color: var(--color-slate-500); }
.cpw-leaf-added {
  color: var(--primary, #ff6a00);
  font-size: 11px;
}
.cpw-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #ff6a00);
}
.cpw-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px 0;
  font-size: 13px;
  color: var(--color-slate-500, #64748b);
}
.cpw-summary-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  box-shadow: 0 -2px 8px color-mix(in srgb, var(--color-slate-900) 4%, transparent);
  margin-top: 12px;
}
.cpw-summary-info {
  flex: 1;
  font-size: 13px;
  color: var(--color-slate-600, #475569);
}
.cpw-cart-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cpw-cart-group {
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.cpw-cart-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-slate-50, #f8fafc);
  border-bottom: 1px solid var(--color-slate-200, #e2e8f0);
}
.cpw-cart-group-icon {
  color: var(--primary, #ff6a00);
}
.cpw-cart-group-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground, #1e293b);
}
.cpw-cart-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
}
.cpw-cart-row.invalid {
  background: var(--color-red-50);
}
.cpw-cart-row:hover {
  background: var(--color-slate-50, #f8fafc);
}
.cpw-cart-row-case { color: var(--foreground, #1e293b); min-width: 90px; }
.cpw-cart-row-dim { color: var(--color-slate-500, #64748b); min-width: 80px; }
.cpw-cart-row-invalid {
  color: var(--destructive, #dc2626);
  font-size: 11px;
}
.cpw-sets {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-slate-200, #e2e8f0);
}
.cpw-sets h4 {
  font-size: 13px;
  color: var(--color-slate-600, #475569);
  margin-bottom: 8px;
}
.cpw-set-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  font-size: 13px;
}
.cpw-set-name {
  flex: 1;
}
.cpw-review-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.cpw-stat-badge {
  flex: 1;
  min-width: 100px;
  padding: 12px;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-md);
  background: var(--color-slate-50, #f8fafc);
  text-align: center;
}
.cpw-stat-badge b {
  display: block;
  font-size: 22px;
  color: var(--primary, #ff6a00);
}
.cpw-stat-badge span {
  font-size: 12px;
  color: var(--color-slate-500, #64748b);
}
.cpw-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.cpw-alert--warn {
  background: var(--color-amber-50);
  border: 1px solid var(--color-amber-200);
  color: var(--color-amber-800);
}
.cpw-alert--info {
  background: var(--color-blue-50);
  border: 1px solid var(--color-blue-200);
  color: var(--color-blue-700);
}
.cpw-checkouts {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cpw-checkout-card {
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: var(--radius-xl);
  padding: 12px 16px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cpw-checkout-card.active {
  border-color: var(--primary, #ff6a00);
  background: var(--accent, #fff7ed);
}
.cpw-checkout-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground, #1e293b);
}
.cpw-checkout-desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--color-slate-500, #64748b);
}
.cpw-checkout-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--color-slate-200, #e2e8f0);
}
.cpw-preview-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding: 3px 0;
}
.cpw-preview-row span { color: var(--color-slate-500, #64748b); }
.cpw-preview-row.warn b { color: var(--color-amber-800); }
.cpw-config-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-slate-600, #475569);
  cursor: pointer;
  user-select: none;
}
.cpw-config-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cpw-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--color-slate-200, #e2e8f0);
}
.cpw-footer-spacer {
  flex: 1;
}
</style>
