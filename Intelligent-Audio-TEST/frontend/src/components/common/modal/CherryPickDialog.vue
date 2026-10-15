<template>
  <div class="cp-overlay" @click.self="$emit('close')">
    <div class="cp-dialog">
      <!-- 头部：流程指示（挑选 → 购物车 → 下单） -->
      <div class="cp-header">
        <h3><i class="fas fa-shopping-cart"></i> {{ stepTitle }}</h3>
        <div class="cp-steps">
          <span v-for="(s, i) in STEPS" :key="s.key"
                class="cp-step" :class="{ active: step === s.key, done: stepIndex > i }"
                @click="goStep(s.key)">
            <i v-if="stepIndex > i" class="fas fa-check"></i> {{ s.label }}
          </span>
        </div>
        <button class="cp-close" @click="$emit('close')"><i class="fas fa-times"></i></button>
      </div>

      <!-- 步骤 1：挑选（多条件筛选 + 正选/反选 + 三档粒度） -->
      <div v-if="step === 'pick'" class="cp-body">
        <!-- 来源任务/设备/用例/状态筛选（多条件 AND，设备+用例为点名维度） -->
        <div class="cp-filters">
          <select v-model="filters.taskId" class="cp-input" @change="loadCandidates">
            <option value="">全部来源任务</option>
            <option v-for="t in pickableTasks" :key="t.id" :value="String(t.id)">{{ t.name }}</option>
          </select>
          <select v-model="filters.deviceId" class="cp-input" @change="loadCandidates">
            <option value="">全部设备</option>
            <option v-for="d in deviceOptions" :key="d.id" :value="String(d.id)">{{ d.name }}</option>
          </select>
          <input v-model="caseKeyword" class="cp-input" placeholder="按用例搜索" @input="debouncedLoad" />
          <select v-model="filters.executionStatus" class="cp-input" @change="loadCandidates">
            <option value="">全部执行状态</option>
            <option value="completed">执行完成</option>
            <option value="failed">执行失败</option>
            <option value="stopped">已停止</option>
          </select>
          <select v-model="filters.evaluationStatus" class="cp-input" @change="loadCandidates">
            <option value="">全部评估状态</option>
            <option value="evaluated">已评估</option>
            <option value="pending">未评估</option>
          </select>
        </div>

        <!-- 工具栏：正选/反选（§4.1）+ 批量粒度 -->
        <div class="cp-toolbar">
          <span class="cp-toolbar-info">已选 {{ selectedResultIds.size }} 条 / 共 {{ candidates.length }} 条（本页）</span>
          <button class="cp-btn" @click="selectAllVisible"><i class="fas fa-check-square"></i> 全选本页</button>
          <button class="cp-btn" @click="invertSelection"><i class="fas fa-exchange-alt"></i> 反选</button>
          <button class="cp-btn" @click="clearSelection"><i class="fas fa-eraser"></i> 清空选择</button>
        </div>

        <!-- 候选列表（结果粒度；按来源任务分组展示） -->
        <div class="cp-list">
          <div v-if="loadingCandidates" class="cp-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载执行结果...</div>
          <div v-else-if="candidates.length === 0" class="cp-empty">
            <i class="fas fa-inbox"></i> 无符合条件的执行结果（仅终态任务可挑选）
          </div>
          <template v-for="group in groupedCandidates" :key="group.taskId">
            <div class="cp-group-title">
              <i class="fas fa-source-branch"></i> {{ group.taskName }}
              <span class="cp-group-count">{{ group.items.length }} 条</span>
              <button class="cp-btn cp-btn-sm" @click="selectGroup(group)">整组勾选</button>
            </div>
            <label v-for="item in group.items" :key="item.resultId" class="cp-row">
              <input type="checkbox" class="cp-checkbox"
                     :checked="selectedResultIds.has(item.resultId)"
                     @change="toggleResult(item.resultId)" />
              <span class="cp-row-case">{{ item.caseId }}</span>
              <span class="cp-row-meta">设备 {{ item.deviceId ?? '-' }}</span>
              <span class="cp-row-badge" :class="item.executionStatus">{{ executionText(item.executionStatus) }}</span>
              <span class="cp-row-badge" :class="item.evaluated ? 'evaluated' : 'pending-eval'">
                {{ item.evaluated ? '已评估' : '未评估' }}
              </span>
              <span class="cp-row-time">{{ formatTime(item.createdAt) }}</span>
            </label>
          </template>
        </div>
        <div class="cp-pagination" v-if="candidateTotal > candidates.length">
          <button class="cp-btn" :disabled="filters.page <= 1" @click="filters.page--; loadCandidates()">上一页</button>
          <span>第 {{ filters.page }} 页</span>
          <button class="cp-btn" @click="filters.page++; loadCandidates()">下一页</button>
        </div>
      </div>

      <!-- 步骤 2：购物车（按来源任务分组 + 另存挑选集） -->
      <div v-else-if="step === 'cart'" class="cp-body">
        <div class="cp-toolbar">
          <span class="cp-toolbar-info">共 {{ cartCount }} 条（{{ invalidCount }} 条失效）</span>
          <button class="cp-btn" v-if="invalidCount > 0" @click="removeInvalid">
            <i class="fas fa-trash-alt"></i> 一键移除失效条目
          </button>
          <button class="cp-btn" @click="clearAll"><i class="fas fa-trash"></i> 清空购物车</button>
          <button class="cp-btn cp-btn-primary" @click="openSaveSet"><i class="fas fa-save"></i> 另存为挑选集</button>
        </div>

        <div class="cp-list">
          <div v-if="cartLoading" class="cp-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载购物车...</div>
          <div v-else-if="cartCount === 0" class="cp-empty"><i class="fas fa-shopping-cart"></i> 购物车为空</div>
          <template v-for="group in cart.groups" :key="group.sourceTaskId">
            <div class="cp-group-title">
              <i class="fas fa-source-branch"></i> {{ group.sourceTaskName }}
              <span class="cp-group-count">{{ group.items.length }} 条</span>
            </div>
            <div v-for="item in group.items" :key="item.itemId" class="cp-row" :class="{ invalid: item.invalid }">
              <span class="cp-row-case">{{ item.sourceCaseId }}</span>
              <span class="cp-row-meta">设备 {{ item.sourceDeviceId ?? '-' }}</span>
              <span class="cp-row-badge" :class="item.executionStatus">{{ executionText(item.executionStatus) }}</span>
              <span v-if="item.invalid" class="cp-row-badge invalid-badge">已失效</span>
              <button class="cp-btn cp-btn-sm" @click="removeOne(item.itemId)"><i class="fas fa-times"></i> 移除</button>
            </div>
          </template>
        </div>

        <!-- 挑选集（另存/恢复两向） -->
        <div class="cp-sets" v-if="sets.length > 0">
          <h4><i class="fas fa-layer-group"></i> 我的挑选集</h4>
          <div v-for="s in sets" :key="s.setId" class="cp-set-row">
            <span class="cp-set-name">{{ s.name }}</span>
            <span class="cp-group-count">{{ s.itemCount }} 条</span>
            <button class="cp-btn cp-btn-sm" @click="restoreSet(s.setId)"><i class="fas fa-undo"></i> 恢复进购物车</button>
            <button class="cp-btn cp-btn-sm" @click="onRemoveSet(s.setId)"><i class="fas fa-trash-alt"></i></button>
          </div>
        </div>
      </div>

      <!-- 步骤 3：下单（三出口向导） -->
      <div v-else class="cp-body">
        <div class="cp-checkouts">
          <!-- 出口 a：合并生成新任务 -->
          <div class="cp-checkout-card" :class="{ active: action === 'merge' }" @click="action = 'merge'">
            <div class="cp-checkout-head">
              <i class="fas fa-object-group"></i> 合并生成新任务
              <span class="cp-checkout-desc">挑选结果合并为新任务 + 报告，源任务保持原样</span>
            </div>
            <div v-if="action === 'merge'" class="cp-checkout-form" @click.stop>
              <div class="cp-preview" v-if="preview">
                <div class="cp-preview-row"><span>结果总数</span><b>{{ preview.totalResults }}</b></div>
                <div class="cp-preview-row"><span>来源任务</span><b>{{ preview.sourceTaskCount }} 个</b></div>
                <div class="cp-preview-row"><span>设备</span><b>{{ preview.deviceNames.join('、') || '-' }}</b></div>
                <div class="cp-preview-row"><span>用例数</span><b>{{ preview.caseCount }}</b></div>
                <div class="cp-preview-row" v-if="preview.duplicates.length > 0">
                  <span>重复提示</span>
                  <b>{{ preview.duplicates.length }} 组同设备同用例多来源结果（默认全保留并标注来源）</b>
                </div>
                <div class="cp-preview-row warn" v-if="invalidCount > 0">
                  <span>失效条目</span><b>{{ invalidCount }} 条（下单时自动跳过）</b>
                </div>
              </div>
              <input v-model="mergeName" class="cp-input" placeholder="新任务名称（必填）" />
              <input v-model="mergeDescription" class="cp-input" placeholder="新任务描述（可选）" />
            </div>
          </div>

          <!-- 出口 b：重新执行 -->
          <div class="cp-checkout-card" :class="{ active: action === 'reexecute' }" @click="action = 'reexecute'">
            <div class="cp-checkout-head">
              <i class="fas fa-redo"></i> 重新执行
              <span class="cp-checkout-desc">按所选结果的用例×设备集合创建重执行任务并启动</span>
            </div>
            <div v-if="action === 'reexecute'" class="cp-checkout-form" @click.stop>
              <input v-model="reexecuteName" class="cp-input" placeholder="重执行任务名称（可选，默认自动命名）" />
            </div>
          </div>

          <!-- 出口 c：重新评估 -->
          <div class="cp-checkout-card" :class="{ active: action === 'reevaluate' }" @click="action = 'reevaluate'">
            <div class="cp-checkout-head">
              <i class="fas fa-sync-alt"></i> 重新评估
              <span class="cp-checkout-desc">对所选结果按来源任务逐个发起重新评估（不重跑执行）</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作 -->
      <div class="cp-footer">
        <button v-if="step !== 'pick'" class="cp-btn" @click="prevStep"><i class="fas fa-arrow-left"></i> 上一步</button>
        <span class="cp-footer-spacer"></span>
        <button v-if="step === 'pick'" class="cp-btn cp-btn-primary" :disabled="selectedResultIds.size === 0" @click="commitPick">
          <i class="fas fa-cart-plus"></i> 加入购物车（{{ selectedResultIds.size }}）
        </button>
        <button v-else-if="step === 'cart'" class="cp-btn cp-btn-primary" :disabled="cartCount === 0" @click="goStep('checkout')">
          <i class="fas fa-flag-checkered"></i> 去下单
        </button>
        <button v-else class="cp-btn cp-btn-primary" :disabled="!action || submitting" @click="submitCheckout">
          <i class="fas" :class="submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
          {{ submitting ? '下单中...' : '提交下单' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CherryPickDialog —— 挑选合并三步向导（INT-339：挑选 → 购物车 → 下单）。
 *
 * 挑选交互（§4.1）：正选/反选；三档粒度（单条勾选 / 按分组整组 / 按维度筛选批量）；
 * 多条件 AND 筛选（来源任务/设备/用例/执行·评估状态，设备+用例为点名维度）。
 * 下单三出口（§3）：合并生成新任务 / 重新执行 / 重新评估。
 * 页面文案一律中文（§1.2：站内不出现 Cherry-Pick 字样）。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { cherryPickApi, tasksApi } from '../../../infrastructure/api';
import type { PickCandidate, PickPreview, PickCheckoutAction } from '../../../infrastructure/api/cherryPickApi';
import { usePickCart } from '../../../composables/task/usePickCart';
import { useNotification } from '../../../composables/modal/useNotification';

const emit = defineEmits<{
  (e: 'close'): void;
  /** 下单成功（merge 出口携带新任务 ID，宿主跳转详情） */
  (e: 'checked-out', payload: { action: PickCheckoutAction; taskId?: number }): void;
}>();

const notification = useNotification();
const {
  cart, cartLoading, cartCount, invalidCount, sets,
  refreshCart, addToCart, removeItem, removeItems, clearCart,
  refreshSets, saveAsSet, restoreSetToCart, deleteSet,
} = usePickCart();

const STEPS = [
  { key: 'pick', label: '挑选' },
  { key: 'cart', label: '购物车' },
  { key: 'checkout', label: '下单' },
] as const;
type StepKey = (typeof STEPS)[number]['key'];
const step = ref<StepKey>('pick');
const stepIndex = computed(() => STEPS.findIndex(s => s.key === step.value));
const stepTitle = computed(() => ({ pick: '挑选执行结果', cart: '我的购物车', checkout: '下单' }[step.value]));

function goStep(key: StepKey) {
  step.value = key;
  if (key === 'cart') refreshCart();
  if (key === 'checkout') loadPreview();
}
function prevStep() {
  step.value = step.value === 'checkout' ? 'cart' : 'pick';
}

// ===== 步骤 1：挑选 =====

const pickableTasks = ref<Array<{ id: number; name: string }>>([]);
const deviceOptions = ref<Array<{ id: number; name: string }>>([]);
const filters = reactive({
  taskId: '', deviceId: '', executionStatus: '', evaluationStatus: '',
  page: 1,
});
const caseKeyword = ref('');
const candidates = ref<PickCandidate[]>([]);
const candidateTotal = ref(0);
const loadingCandidates = ref(false);
const selectedResultIds = ref<Set<number>>(new Set());

/** 按来源任务分组（§3 挑选按任务分组展示） */
const groupedCandidates = computed(() => {
  const map = new Map<number, { taskId: number; taskName: string; items: PickCandidate[] }>();
  for (const item of candidates.value) {
    if (!map.has(item.taskId)) {
      map.set(item.taskId, { taskId: item.taskId, taskName: item.taskName, items: [] });
    }
    map.get(item.taskId)!.items.push(item);
  }
  return [...map.values()];
});

const groupedSelection = computed(() => groupedCandidates.value.filter(g => g.items.length > 0));

let loadTimer: ReturnType<typeof setTimeout> | null = null;
function debouncedLoad() {
  if (loadTimer) clearTimeout(loadTimer);
  loadTimer = setTimeout(loadCandidates, 300);
}

async function loadCandidates() {
  loadingCandidates.value = true;
  try {
    const page = await cherryPickApi.listCandidates({
      taskIds: filters.taskId ? [Number(filters.taskId)] : [],
      deviceIds: filters.deviceId ? [Number(filters.deviceId)] : [],
      caseIds: caseKeyword.value ? [caseKeyword.value] : [],
      executionStatus: filters.executionStatus || undefined,
      evaluationStatus: filters.evaluationStatus || undefined,
      page: filters.page,
      perPage: 50,
    });
    candidates.value = page.items ?? [];
    candidateTotal.value = page.total ?? 0;
  } catch (error) {
    console.error('Failed to load pick candidates:', error);
    candidates.value = [];
  } finally {
    loadingCandidates.value = false;
  }
}

/** 可挑选来源任务（仅终态）+ 设备选项（进入弹窗时加载） */
async function loadOptions() {
  try {
    const data = await tasksApi.getAll({ perPage: 100, status: undefined }) as any;
    const FINISHED = ['completed', 'failed', 'stopped'];
    pickableTasks.value = (data.items ?? [])
      .filter((t: any) => FINISHED.includes(String(t.status)))
      .map((t: any) => ({ id: Number(t.id), name: t.name }));
    // 设备选项从候选结果聚合（点名维度：某台设备的执行结果）
    const deviceMap = new Map<number, string>();
    for (const item of candidates.value) {
      if (item.deviceId != null && !deviceMap.has(item.deviceId)) {
        deviceMap.set(item.deviceId, `设备 ${item.deviceId}`);
      }
    }
    deviceOptions.value = [...deviceMap.entries()].map(([id, name]) => ({ id, name }));
  } catch (error) {
    console.error('Failed to load pick options:', error);
  }
}

// ===== 正选/反选（§4.1）=====

function toggleResult(resultId: number) {
  const next = new Set(selectedResultIds.value);
  if (next.has(resultId)) next.delete(resultId); else next.add(resultId);
  selectedResultIds.value = next;
}

function selectAllVisible() {
  const next = new Set(selectedResultIds.value);
  for (const item of candidates.value) next.add(item.resultId);
  selectedResultIds.value = next;
}

function invertSelection() {
  const next = new Set<number>();
  for (const item of candidates.value) {
    if (!selectedResultIds.value.has(item.resultId)) next.add(item.resultId);
  }
  selectedResultIds.value = next;
}

function clearSelection() {
  selectedResultIds.value = new Set();
}

/** 按分组整组选（§4.1 三档粒度之二） */
function selectGroup(group: { items: PickCandidate[] }) {
  const next = new Set(selectedResultIds.value);
  for (const item of group.items) next.add(item.resultId);
  selectedResultIds.value = next;
}

// ===== 步骤 2：购物车 =====

async function commitPick() {
  if (selectedResultIds.value.size === 0) return;
  try {
    const outcome = await addToCart([...selectedResultIds.value]);
    const added = outcome.added?.length ?? 0;
    if (outcome.missing?.length) {
      notification.warning(`已加入 ${added} 条，${outcome.missing.length} 条源结果已失效未加入`);
    } else {
      notification.success(`已加入购物车 ${added} 条`);
    }
    selectedResultIds.value = new Set();
    step.value = 'cart';
  } catch (error: any) {
    notification.error(error?.message || '加入购物车失败');
  }
}

async function removeOne(itemId: number) {
  try {
    await removeItem(itemId);
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

async function clearAll() {
  try {
    await clearCart();
    notification.success('购物车已清空');
  } catch (error: any) {
    notification.error(error?.message || '清空失败');
  }
}

async function openSaveSet() {
  const name = window.prompt('挑选集名称（同名允许重复保存）', `挑选集_${new Date().toISOString().slice(0, 10)}`);
  if (!name) return;
  try {
    const outcome = await saveAsSet(name);
    notification.success(`挑选集「${outcome.name}」已保存（${outcome.item_count} 条）`);
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


// ===== 步骤 3：下单 =====

const action = ref<PickCheckoutAction>('merge');
const preview = ref<PickPreview | null>(null);
const mergeName = ref('');
const mergeDescription = ref('');
const reexecuteName = ref('');
const submitting = ref(false);

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
      const result = await cherryPickApi.checkout({
        action: 'merge',
        name: mergeName.value.trim(),
        description: mergeDescription.value || undefined,
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
      emit('checked-out', { action: 'reevaluate' });
      emit('close');
    }
  } catch (error: any) {
    notification.error(error?.message || '下单失败');
  } finally {
    submitting.value = false;
  }
}

// ===== 展示辅助 =====

function executionText(status?: string | null) {
  switch (status) {
    case 'completed': return '执行完成';
    case 'failed': return '执行失败';
    case 'stopped': return '已停止';
    case 'running': return '执行中';
    case 'pending': return '待执行';
    default: return status || '-';
  }
}

function formatTime(iso?: string | null) {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}

onMounted(async () => {
  await Promise.all([loadCandidates(), loadOptions(), refreshCart(), refreshSets()]);
});

// 筛选任务变化后刷新设备选项（候选集合变化）
watch(() => filters.taskId, () => {
  filters.page = 1;
  loadCandidates().then(loadOptions);
});
</script>

<style scoped>
@import './CherryPickDialog.css';
</style>
