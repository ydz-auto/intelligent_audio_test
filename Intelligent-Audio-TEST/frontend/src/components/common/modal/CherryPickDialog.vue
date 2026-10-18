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
          <select v-model="filters.deviceId" class="cp-input" @change="onFilterChange"> (INT-738: 挑选合并向导——设备/执行状态/评估状态筛选变更重置页码回第 1 页（对齐 INT-339 P2-1 回归用例）)
            <option value="">全部设备</option>
            <option v-for="d in deviceOptions" :key="d.id" :value="String(d.id)">{{ d.name }}</option>
          </select>
          <input v-model="caseKeyword" class="cp-input" placeholder="按用例搜索" @input="debouncedLoad" />
          <select v-model="filters.executionStatus" class="cp-input" @change="onFilterChange"> (INT-738: 挑选合并向导——设备/执行状态/评估状态筛选变更重置页码回第 1 页（对齐 INT-339 P2-1 回归用例）)
            <option value="">全部执行状态</option>
            <option value="completed">执行完成</option>
            <option value="failed">执行失败</option>
            <option value="stopped">已停止</option>
          </select>
          <select v-model="filters.evaluationStatus" class="cp-input" @change="onFilterChange"> (INT-738: 挑选合并向导——设备/执行状态/评估状态筛选变更重置页码回第 1 页（对齐 INT-339 P2-1 回归用例）)
            <option value="">全部评估状态</option>
            <option value="evaluated">已评估</option>
            <option value="pending">未评估</option>
          </select>
        </div>

        <!-- INT-551：设备选项加载失败可见错误提示（原静默空下拉，用户误以为无设备） -->
        <div v-if="deviceError" class="cp-error-bar">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ deviceError }}</span>
          <button class="cp-btn cp-btn-sm" @click="loadOptions"><i class="fas fa-redo"></i> 重试</button>
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
          <!-- INT-551：候选加载失败保留旧数据 → 顶部可见错误条（INT-289 先例），不丢旧列表 -->
          <div v-if="candidatesError && candidates.length > 0" class="cp-error-bar">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ candidatesError }}</span>
            <button class="cp-btn cp-btn-sm" @click="loadCandidates"><i class="fas fa-redo"></i> 重试</button>
          </div>
          <div v-if="loadingCandidates" class="cp-empty"><i class="fas fa-spinner fa-spin"></i> 正在加载执行结果...</div>
          <!-- INT-551：候选加载失败且无旧数据 → 错误态（含重试），不再误导为空态 -->
          <div v-else-if="candidatesError && candidates.length === 0" class="cp-error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ candidatesError }}</span>
            <button class="cp-btn" @click="loadCandidates"><i class="fas fa-redo"></i> 重试</button>
          </div>
          <template v-else-if="groupedCandidates.length > 0">
            <div v-for="group in groupedCandidates" :key="group.taskId">
              <div class="cp-group-title">
                <i class="fas fa-source-branch"></i> {{ group.taskName }}
                <span class="cp-group-count">{{ group.items.length }} 条</span>
                <!-- INT-401：整组勾选/整组取消双向（三档粒度之二，原仅单向加选） -->
                <button class="cp-btn cp-btn-sm" @click="selectGroup(group)">整组勾选</button>
                <button class="cp-btn cp-btn-sm" @click="unselectGroup(group)">整组取消</button>
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
            </div>
          </template>
          <div v-else class="cp-empty">
            <i class="fas fa-inbox"></i> 无符合条件的执行结果（仅终态任务可挑选）
          </div>
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
                <!-- INT-401：跨任务配置不一致提示（§5.2/§11-③ 拍板强制确认，提交前弹确认） -->
                <div class="cp-preview-row warn" v-if="preview && preview.configInconsistent">
                  <span>配置差异</span>
                  <b>{{ preview.sourceTaskCount }} 个来源任务的任务级配置（{{ (preview.configFields || []).join('、') || '算法参数' }}）不一致，默认取首个来源任务，提交需确认</b>
                </div>
              </div>
              <input v-model="mergeName" class="cp-input" placeholder="新任务名称（必填）" />
              <input v-model="mergeDescription" class="cp-input" placeholder="新任务描述（可选）" />
              <!-- INT-401：merge 出口任务级配置表单（§5.2 创建弹窗允许编辑算法参数/标签等任务级配置） -->
              <div class="cp-config-toggle" @click="showMergeConfig = !showMergeConfig">
                <i class="fas" :class="showMergeConfig ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
                任务级配置（可选，默认取首个来源任务）
              </div>
              <div v-if="showMergeConfig" class="cp-config-fields">
                <input v-model="mergeAlgorithmType" class="cp-input" placeholder="算法类型覆盖（如 asr / tts / translation）" />
                <textarea v-model="mergeAlgorithmParams" class="cp-input cp-textarea" placeholder='算法参数覆盖（JSON，如 {"model":"xx"}）' rows="2"></textarea>
                <textarea v-model="mergeConfig" class="cp-input cp-textarea" placeholder='任务配置覆盖（JSON，可选）' rows="2"></textarea>
              </div>
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
        <button v-else class="cp-btn cp-btn-primary" :disabled="!action || submitting || cartCount === 0" @click="submitCheckout">
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
import { cherryPickApi, tasksApi, devicesApi } from '../../../infrastructure/api';
import type { PickCandidate, PickPreview, PickCheckoutAction } from '../../../infrastructure/api/cherryPickApi';
import { usePickCart } from '../../../composables/task/usePickCart';
import { useNotification } from '../../../composables/modal/useNotification';
import { useModalControl } from '../../../composables/modal/useModal';
import { MODAL_TYPES } from '../../../composables/modal/constants';

const props = defineProps<{
  /** INT-401：入口预筛选（任务详情「加入购物车」→ 打开向导直接定位该任务的执行结果） */
  presetTaskId?: number | string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  /** 下单成功（merge 出口携带新任务 ID，宿主跳转详情） */
  (e: 'checked-out', payload: { action: PickCheckoutAction; taskId?: number }): void;
}>();

const notification = useNotification();
const modalControl = useModalControl();
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
// INT-551：候选/设备加载失败错误态（原静默清空成误导性空态）
const candidatesError = ref('');
const deviceError = ref('');
const selectedResultIds = ref<Set<number>>(new Set());

// INT-401：任务详情「加入购物车」入口预筛选——打开向导即定位该任务的执行结果
// （设计 §9 入口应为结果列表级；设置早于 watch 注册，初始 loadCandidates 直接命中）
if (props.presetTaskId != null) {
  filters.taskId = String(props.presetTaskId);
}

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
  loadTimer = setTimeout(() => {
    // P2-1：筛选变更重置页码（防旧页码「无符合条件」误判）
    filters.page = 1;
    loadCandidates();
  }, 300);
}

/** P2-1：筛选变更重置页码到第 1 页再查询（设备/执行状态/评估状态共用） */
function onFilterChange() {
  filters.page = 1;
  loadCandidates();
}

async function loadCandidates() {
  loadingCandidates.value = true;
  candidatesError.value = '';
  try {
    const page = await cherryPickApi.listCandidates({
      taskIds: filters.taskId ? [Number(filters.taskId)] : [],
      deviceIds: filters.deviceId ? [Number(filters.deviceId)] : [],
      caseIds: [],
      caseKeyword: caseKeyword.value.trim() || undefined,
      executionStatus: filters.executionStatus || undefined,
      evaluationStatus: filters.evaluationStatus || undefined,
      page: filters.page,
      perPage: 50,
    });
    candidates.value = page.items ?? [];
    candidateTotal.value = page.total ?? 0;
  } catch (error: any) {
    // INT-551：失败保留旧数据 + 可见错误条（原静默清空成「无结果」误导空态）
    console.error('Failed to load pick candidates:', error);
    candidatesError.value = error?.message ? `加载执行结果失败：${error.message}` : '加载执行结果失败，请重试';
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
    // INT-401：设备下拉独立取设备列表（设计 §4 设备为筛选条件——点名维度；
    // 原实现从当前候选结果聚合，先有结果才有设备选项且跨任务筛选互相污染）
    try {
      deviceError.value = '';
      const devices = await devicesApi.getAllFlat({ per_page: 100 });
      deviceOptions.value = (devices ?? []).map((d: any) => ({
        id: Number(d.id), name: d.name ?? `设备 ${d.id}`,
      }));
    } catch (deviceErr: any) {
      // INT-551：设备选项失败可见错误提示（原静默空下拉，用户误以为无设备）
      console.error('Failed to load device options:', deviceErr);
      deviceError.value = deviceErr?.message ? `设备列表加载失败：${deviceErr.message}` : '设备列表加载失败，请重试';
    }
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

/** INT-401：反选（§4.1 正选后反选剔除）——只反选当前页候选，保留其他页已选项。
 *  原实现从当前页重建集合，会丢掉跨页已选（分页场景缺陷）。 */
function invertSelection() {
  const next = new Set(selectedResultIds.value);
  for (const item of candidates.value) {
    if (next.has(item.resultId)) next.delete(item.resultId); else next.add(item.resultId);
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

/** INT-401：整组取消（三档粒度双向，原仅单向加选） */
function unselectGroup(group: { items: PickCandidate[] }) {
  const next = new Set(selectedResultIds.value);
  for (const item of group.items) next.delete(item.resultId);
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
  // INT-286：另存挑选集改 INPUT_CONFIRM 表单模态，替换原生 window.prompt
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
    return; // 用户取消
  }
  if (!name) return;
  try {
    const outcome = await saveAsSet(name);
    // INT-738：toast 读 camelCase itemCount（infrastructure 层已收敛 snake_case，原 item_count 恒 undefined） (INT-738: UX设计-VUE 任务域实施——/tasks 四页签收敛（收藏收编筛选）+ 移除统计卡与三图 + 任务详情「生成 AI 报告」入口契约 + 挑选合并文案/单测修正)
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


// ===== 步骤 3：下单 =====

const action = ref<PickCheckoutAction>('merge');
const preview = ref<PickPreview | null>(null);
const mergeName = ref('');
const mergeDescription = ref('');
const reexecuteName = ref('');
const submitting = ref(false);
// INT-401：merge 出口任务级配置（§5.2 创建弹窗允许编辑算法参数/配置）
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
      // §5.2/§11-③（INT-400 #14）：跨任务配置不一致强制确认提示——比默认取首源严
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
          return; // 用户取消
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
      // INT-401：重新评估出口携带首个来源任务 ID，宿主跳转该任务详情查看评估进度（§9）
      emit('checked-out', { action: 'reevaluate', taskId: result.submittedTaskIds?.[0] });
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
