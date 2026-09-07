<template>
  <div class="batch-dimension-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">{{ selectionMode === 'selected' ? '您勾选了' : '将对' }} {{ caseCount }} 个用例设置评价维度</p>
    </div>

    <div class="modal-body">
      <!-- 轮次范围模式选择 -->
      <div class="scope-section">
        <label>单轮评估维度 - 轮次范围</label>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" :value="'all'" v-model="roundMode" />
            <span>所有轮次（统一设置）</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'specific'" v-model="roundMode" />
            <span>指定轮次（统一设置）</span>
          </label>
          <label class="radio-label">
            <input type="radio" :value="'per_round'" v-model="roundMode" />
            <span>逐轮设置（每轮可不同）</span>
          </label>
        </div>
        <p class="mode-hint" v-if="roundMode === 'per_round'">提示：逐轮设置模式下，未选维度的轮次将被清空</p>
        <p class="mode-hint" v-else>提示：不选任何维度点确定即清除选中轮次的评估维度</p>
      </div>
      <div class="scope-section" v-if="roundMode === 'specific'">
        <label>选择轮次</label>
        <div class="round-checkboxs">
          <label v-for="rn in availableRoundNumbers" :key="rn"
                 :class="{ checked: roundNumbers.includes(rn) }"
                 @click="toggleRoundNumber(rn)">
            第{{ rn }}轮
          </label>
          <label :class="{ checked: roundNumbers.includes(-1) }" @click="toggleRoundNumber(-1)">
            最后一轮
          </label>
        </div>
        <p class="level-hint">"最后一轮"会根据每个用例的实际轮次数动态解析</p>
      </div>

      <!-- 统一模式：所有/指定轮次共用同一套维度 -->
      <template v-if="roundMode === 'all' || roundMode === 'specific'">
        <div class="form-group">
          <label>单轮评价维度</label>
          <div class="dimension-cloud-container">
            <div
              v-for="dim in filteredAvailableDimensions"
              :key="dim.id"
              class="dimension-tag"
              :class="{ 'selected': isDimensionSelected(dim) }"
              @click="toggleDimension(dim)"
            >
              {{ dim.name }}
            </div>
          </div>
          <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
        </div>

        <div v-if="selectedDimensions.length > 0" class="form-group">
          <label>维度权重和阈值配置</label>
          <div class="dimension-config-list">
            <div v-for="(dim, index) in selectedDimensions" :key="dim.id" class="dimension-config-item">
              <div class="dimension-config-header">
                <span class="dimension-config-name">{{ dim.name }}</span>
                <button type="button" class="btn btn-xs btn-danger" @click="removeDimension(index)">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="dimension-config-fields">
                <div class="form-row">
                  <div class="form-group">
                    <label>权重（0-100）</label>
                    <input type="number" v-model.number="dimConfigs[dim.id].weight" class="form-input" min="0" max="100" />
                  </div>
                  <div class="form-group">
                    <label>阈值（0-100）</label>
                    <input type="number" v-model.number="dimConfigs[dim.id].threshold" class="form-input" min="0" max="100" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 逐轮设置模式：每个轮次独立配置维度 -->
      <template v-if="roundMode === 'per_round'">
        <div class="per-round-container">
          <div class="round-tabs">
            <div
              v-for="rn in availableRoundNumbers"
              :key="rn"
              class="round-tab"
              :class="{ active: activeRoundTab === rn }"
              @click="activeRoundTab = rn"
            >
              第{{ rn }}轮
              <span class="round-tab-count" v-if="getRoundSelectedDimensions(rn).length > 0">{{ getRoundSelectedDimensions(rn).length }}</span>
              <span v-if="availableRoundNumbers.length > 1" class="round-tab-close" @click.stop="removeRound(rn)">
                <i class="fas fa-times"></i>
              </span>
            </div>
            <button type="button" class="round-tab-add" @click="addRound">
              <i class="fas fa-plus"></i> 添加轮次
            </button>
            <!-- 最后一轮特殊标签 -->
            <div
              class="round-tab round-tab-special"
              :class="{ active: activeRoundTab === -1 }"
              @click="activeRoundTab = -1"
            >
              <i class="fas fa-flag"></i> 最后一轮
              <span class="round-tab-count" v-if="getRoundSelectedDimensions(-1).length > 0">{{ getRoundSelectedDimensions(-1).length }}</span>
            </div>
          </div>

          <div class="round-content" v-if="activeRoundTab">
            <div class="form-group">
              <label>{{ activeRoundTab === -1 ? '最后一轮 - 评价维度' : `第${activeRoundTab}轮 - 评价维度` }}</label>
              <div class="dimension-cloud-container">
                <div
                  v-for="dim in filteredAvailableDimensions"
                  :key="dim.id"
                  class="dimension-tag"
                  :class="{ 'selected': isRoundDimensionSelected(activeRoundTab, dim) }"
                  @click="toggleRoundDimension(activeRoundTab, dim)"
                >
                  {{ dim.name }}
                </div>
              </div>
              <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
            </div>

            <div v-if="getRoundSelectedDimensions(activeRoundTab).length > 0" class="form-group">
              <label>{{ activeRoundTab === -1 ? '最后一轮 - 维度权重和阈值配置' : `第${activeRoundTab}轮 - 维度权重和阈值配置` }}</label>
              <div class="dimension-config-list">
                <div v-for="(dim, index) in getRoundSelectedDimensions(activeRoundTab)" :key="dim.id" class="dimension-config-item">
                  <div class="dimension-config-header">
                    <span class="dimension-config-name">{{ dim.name }}</span>
                    <button type="button" class="btn btn-xs btn-danger" @click="removeRoundDimension(activeRoundTab, index)">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                  <div class="dimension-config-fields">
                    <div class="form-row">
                      <div class="form-group">
                        <label>权重（0-100）</label>
                        <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].weight" class="form-input" min="0" max="100" />
                      </div>
                      <div class="form-group">
                        <label>阈值（0-100）</label>
                        <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].threshold" class="form-input" min="0" max="100" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <p v-else class="empty-hint">请从上方选择评价维度</p>

            <p v-if="activeRoundTab === -1" class="last-round-hint">
              <i class="fas fa-info-circle"></i> "最后一轮"会根据每个用例的实际轮次数动态解析（如2轮用例→第2轮，3轮用例→第3轮）
            </p>
          </div>

          <!-- 快速操作工具栏 -->
          <div class="per-round-toolbar">
            <button type="button" class="btn btn-xs btn-secondary" @click="copyFromRound(activeRoundTab)" :disabled="allRoundTabs.length <= 1">
              从其他轮次复制
            </button>
            <button type="button" class="btn btn-xs btn-secondary" @click="clearRound(activeRoundTab)" :disabled="getRoundSelectedDimensions(activeRoundTab).length === 0">
              清空当前轮次
            </button>
            <button type="button" class="btn btn-xs btn-secondary" @click="applyToAllRounds(activeRoundTab)" :disabled="getRoundSelectedDimensions(activeRoundTab).length === 0 || allRoundTabs.length <= 1">
              应用到所有轮次
            </button>
          </div>

          <!-- 复制来源选择 -->
          <div class="copy-source" v-if="showCopySource">
            <span>从</span>
            <select v-model="copySourceRound" class="form-input copy-source-select">
              <option v-for="rn in allRoundTabs.filter(r => r !== activeRoundTab)" :key="rn" :value="rn">{{ rn === -1 ? '最后一轮' : `第${rn}轮` }}</option>
            </select>
            <span>复制</span>
            <button type="button" class="btn btn-xs btn-primary" @click="doCopyFromRound">确定</button>
            <button type="button" class="btn btn-xs btn-secondary" @click="showCopySource = false">取消</button>
          </div>
        </div>
      </template>

      <!-- 多轮整体评估维度 -->
      <div class="scope-section multi-section">
        <label>多轮整体评估维度（跨轮次聚合） <span class="optional-tag">可选</span></label>
        <p class="section-desc">这些维度基于所有轮次的整体表现进行评估，与单轮维度独立配置。不选任何维度将清空已有的整体评估维度</p>
        <div class="dimension-cloud-container">
          <div
            v-for="dim in filteredAvailableDimensions"
            :key="'multi-' + dim.id"
            class="dimension-tag"
            :class="{ 'selected': isMultiDimensionSelected(dim) }"
            @click="toggleMultiDimension(dim)"
          >
            {{ dim.name }}
          </div>
        </div>
        <p v-if="filteredAvailableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>

        <div v-if="multiSelectedDimensions.length > 0" class="form-group" style="margin-top: 12px;">
          <label>整体评估 - 权重和阈值配置</label>
          <div class="dimension-config-list">
            <div v-for="(dim, index) in multiSelectedDimensions" :key="'multi-cfg-' + dim.id" class="dimension-config-item">
              <div class="dimension-config-header">
                <span class="dimension-config-name">{{ dim.name }}</span>
                <button type="button" class="btn btn-xs btn-danger" @click="removeMultiDimension(index)">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="dimension-config-fields">
                <div class="form-row">
                  <div class="form-group">
                    <label>权重（0-100）</label>
                    <input type="number" v-model.number="multiDimConfigs[dim.id].weight" class="form-input" min="0" max="100" />
                  </div>
                  <div class="form-group">
                    <label>阈值（0-100）</label>
                    <input type="number" v-model.number="multiDimConfigs[dim.id].threshold" class="form-input" min="0" max="100" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * BatchDimensionModal —— 组合根（聚合口）
 *
 * 原超大 script 已按职责拆分至同目录 BatchDimensionModal.*.ts：
 * - state:     共享响应式状态与轮次管理（增删轮次、初始化轮次状态）
 * - selection: 统一 / 逐轮 / 多轮整体评估的维度勾选交互（含轮次复制/清空/批量应用）
 * - loaders:   维度数据加载与 Domain→展示标签归一
 * - save:      提交载荷组装与 confirm / cancel 事件
 * - types / constants: 类型契约与常量配置
 * 本文件仅负责模块组装与模板绑定，对外 props / emits 接口保持不变。
 */
import { onMounted } from 'vue'
import { useDimensions } from '../../../composables/shared/useDimensions'
import { TestType } from '@/domain/enums'
import { createBatchDimensionState } from './BatchDimensionModal.state'
import { createDimensionLoader } from './BatchDimensionModal.loaders'
import { createDimensionSelection } from './BatchDimensionModal.selection'
import { createDimensionSubmit } from './BatchDimensionModal.save'
import type { Props, Emits } from './BatchDimensionModal.types'

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置评价维度',
  caseCount: 0,
  algorithmType: '',
  testType: TestType.E2E,
  maxRoundNumbers: 3,
  selectionMode: 'all'
})

const emit = defineEmits<Emits>()

// ===== 共享状态与轮次管理 =====
const state = createBatchDimensionState(props)
const {
  roundMode,
  roundNumbers,
  availableRoundNumbers,
  selectedDimensions,
  dimConfigs,
  activeRoundTab,
  roundDimConfigs,
  showCopySource,
  copySourceRound,
  multiSelectedDimensions,
  multiDimConfigs,
  allRoundTabs,
  addRound,
  removeRound
} = state

// ===== 维度数据加载 =====
const { fetchAllDimensions, fetchDimensionsByAlgorithmType, getDimensionsByAlgorithmType } = useDimensions()
const { loadDimensions } = createDimensionLoader({ props, state, fetchAllDimensions, fetchDimensionsByAlgorithmType })

// ===== 勾选交互（统一 / 逐轮 / 多轮整体评估） =====
const {
  filteredAvailableDimensions,
  toggleRoundNumber,
  isDimensionSelected,
  toggleDimension,
  removeDimension,
  isRoundDimensionSelected,
  toggleRoundDimension,
  getRoundSelectedDimensions,
  removeRoundDimension,
  copyFromRound,
  doCopyFromRound,
  clearRound,
  applyToAllRounds,
  isMultiDimensionSelected,
  toggleMultiDimension,
  removeMultiDimension
} = createDimensionSelection({ props, state, getDimensionsByAlgorithmType })

// ===== 保存提交 =====
const { handleConfirm, handleCancel } = createDimensionSubmit({ props, emit, state })

onMounted(async () => {
  await loadDimensions()
})
</script>

<style scoped>
@import './BatchDimensionModal.css';
</style>