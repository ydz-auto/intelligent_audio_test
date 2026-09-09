<script setup lang="ts">
import { useDimensionConfigPanel, type DimensionConfigPanelProps, type DimensionConfigPanelEmit } from './DimensionConfigPanel'

const props = withDefaults(defineProps<DimensionConfigPanelProps>(), {
  modelValue: () => ({}),
  loading: false,
  error: '',
  required: false,
  searchQuery: '',
  maxRoundNumbers: 3
})

const emit = defineEmits<DimensionConfigPanelEmit>()

const {
  RoundMode,
  LAST_ROUND,
  roundMode,
  roundNumbers,
  selectedDimensions,
  dimConfigs,
  multiSelectedDimensions,
  multiDimConfigs,
  activeRoundTab,
  availableRoundNumbers,
  allRoundTabs,
  localSearchQuery,
  roundDimConfigs,
  showCopySource,
  copySourceRound,
  toggleRoundNumber,
  isDimensionSelected,
  toggleDimension,
  removeDimension,
  isRoundDimensionSelected,
  toggleRoundDimension,
  getRoundSelectedDimensions,
  removeRoundDimension,
  addRound,
  removeRound,
  copyFromRound,
  doCopyFromRound,
  clearRound,
  applyToAllRounds,
  isMultiDimensionSelected,
  toggleMultiDimension,
  removeMultiDimension,
  emitUpdate,
  hasDimensions,
  dimensionCount
} = useDimensionConfigPanel(props, emit)
</script>

<template>
  <div class="dimension-config-panel">
    <!-- 轮次范围模式选择 -->
    <div class="scope-section">
      <label>单轮评估维度 - 轮次范围</label>
      <div class="radio-group">
        <label class="radio-label">
          <input type="radio" :value="RoundMode.ALL" v-model="roundMode" />
          <span>所有轮次（统一设置）</span>
        </label>
        <label class="radio-label">
          <input type="radio" :value="RoundMode.SPECIFIC" v-model="roundMode" />
          <span>指定轮次（统一设置）</span>
        </label>
        <label class="radio-label">
          <input type="radio" :value="RoundMode.PER_ROUND" v-model="roundMode" />
          <span>逐轮设置（每轮可不同）</span>
        </label>
      </div>
      <p class="mode-hint" v-if="roundMode === RoundMode.ALL">所有轮次共用同一套评估维度，每轮独立评分。不选任何维度点确定即清空已有的评估维度</p>
      <p class="mode-hint" v-else-if="roundMode === RoundMode.SPECIFIC">仅对选中的轮次统一设置评估维度，其他轮次不受影响。不选任何维度点确定即清空选中轮次的评估维度</p>
      <p class="mode-hint" v-else>每轮可独立选择不同的评估维度，未选维度的轮次将被清空</p>
    </div>

    <!-- 指定轮次选择 -->
    <div class="scope-section" v-if="roundMode === RoundMode.SPECIFIC">
      <label>选择轮次</label>
      <div class="round-checkboxs">
        <label
          v-for="rn in availableRoundNumbers"
          :key="rn"
          :class="{ checked: roundNumbers.includes(rn) }"
          @click="toggleRoundNumber(rn)"
        >
          第{{ rn }}轮
        </label>
        <label :class="{ checked: roundNumbers.includes(LAST_ROUND) }" @click="toggleRoundNumber(LAST_ROUND)">
          最后一轮
        </label>
      </div>
      <p class="level-hint">"最后一轮"会根据每个用例的实际轮次数动态解析</p>
    </div>

    <!-- 统一模式：所有/指定轮次共用同一套维度 -->
    <template v-if="roundMode === RoundMode.ALL || roundMode === RoundMode.SPECIFIC">
      <!-- 搜索工具栏 + 已选计数 -->
      <div class="dimension-toolbar">
        <input
          type="text"
          class="form-input"
          placeholder="搜索评估维度"
          :value="localSearchQuery"
          @input="localSearchQuery = ($event.target as HTMLInputElement).value"
          @click.stop
        >
        <div class="dimension-summary" :class="{ 'has-error': required && !hasDimensions }">
            已选 {{ dimensionCount }} 项
          </div>
      </div>

      <div class="form-group">
        <label>单轮评价维度</label>
        <div class="dimension-cloud-container" v-if="!loading">
          <div
            v-for="dim in availableDimensions"
            :key="dim.id"
            class="dimension-tag"
            :class="{ 'selected': isDimensionSelected(dim) }"
            @click.stop.prevent="toggleDimension(dim)"
          >
            {{ dim.name }}
          </div>
          <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
        </div>
        <div class="dimension-loading" v-else>加载中...</div>
        <p class="option-hint" v-if="error">{{ error }}</p>
        <p class="option-hint error" v-if="required && !hasDimensions">请至少选择一个评估维度</p>
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
                  <input type="number" v-model.number="dimConfigs[dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
                <div class="form-group">
                  <label>阈值（0-100）</label>
                  <input type="number" v-model.number="dimConfigs[dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 逐轮设置模式：每个轮次独立配置维度 -->
    <template v-if="roundMode === RoundMode.PER_ROUND">
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
            <span class="round-tab-close" @click.stop="removeRound(rn)">
              <i class="fas fa-times"></i>
            </span>
          </div>
          <button type="button" class="round-tab-add" @click="addRound">
            <i class="fas fa-plus"></i> 添加轮次
          </button>
          <div
            class="round-tab round-tab-special"
            :class="{ active: activeRoundTab === LAST_ROUND }"
            @click="activeRoundTab = LAST_ROUND"
          >
            <i class="fas fa-flag"></i> 最后一轮
            <span class="round-tab-count" v-if="getRoundSelectedDimensions(LAST_ROUND).length > 0">{{ getRoundSelectedDimensions(LAST_ROUND).length }}</span>
          </div>
        </div>

        <div class="round-content" v-if="activeRoundTab">
          <!-- 搜索工具栏 + 已选计数 -->
          <div class="dimension-toolbar">
            <input
              type="text"
              class="form-input"
              placeholder="搜索评估维度"
              :value="localSearchQuery"
              @input="localSearchQuery = ($event.target as HTMLInputElement).value"
              @click.stop
            >
            <div class="dimension-summary" :class="{ 'has-error': required && !hasDimensions }">
              已选 {{ dimensionCount }} 项
            </div>
          </div>

          <div class="form-group">
            <label>{{ activeRoundTab === LAST_ROUND ? '最后一轮 - 评价维度' : `第${activeRoundTab}轮 - 评价维度` }}</label>
            <div class="dimension-cloud-container" v-if="!loading">
              <div
                v-for="dim in availableDimensions"
                :key="dim.id"
                class="dimension-tag"
                :class="{ 'selected': isRoundDimensionSelected(activeRoundTab, dim) }"
                @click.stop.prevent="toggleRoundDimension(activeRoundTab, dim)"
              >
                {{ dim.name }}
              </div>
              <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
            </div>
            <div class="dimension-loading" v-else>加载中...</div>
            <p class="option-hint" v-if="error">{{ error }}</p>
            <p class="option-hint error" v-if="required && !hasDimensions">请至少选择一个评估维度</p>
          </div>

          <div v-if="getRoundSelectedDimensions(activeRoundTab).length > 0" class="form-group">
            <label>{{ activeRoundTab === LAST_ROUND ? '最后一轮 - 维度权重和阈值配置' : `第${activeRoundTab}轮 - 维度权重和阈值配置` }}</label>
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
                      <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                    </div>
                    <div class="form-group">
                      <label>阈值（0-100）</label>
                      <input type="number" v-model.number="roundDimConfigs[activeRoundTab][dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">请从上方选择评价维度</p>

          <p v-if="activeRoundTab === LAST_ROUND" class="last-round-hint">
            <i class="fas fa-info-circle"></i> "最后一轮"会根据每个用例的实际轮次数动态解析（如2轮用例→第2轮，3轮用例→第3轮）
          </p>
        </div>

        <!-- 快速操作工具栏 -->
        <div class="per-round-toolbar">
          <button type="button" class="btn btn-xs btn-secondary" @click="copyFromRound" :disabled="allRoundTabs.length <= 1">
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
            <option v-for="rn in allRoundTabs.filter(r => r !== activeRoundTab)" :key="rn" :value="rn">{{ rn === LAST_ROUND ? '最后一轮' : `第${rn}轮` }}</option>
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
      <div class="dimension-cloud-container" v-if="!loading">
        <div
          v-for="dim in availableDimensions"
          :key="'multi-' + dim.id"
          class="dimension-tag"
          :class="{ 'selected': isMultiDimensionSelected(dim) }"
          @click.stop.prevent="toggleMultiDimension(dim)"
        >
          {{ dim.name }}
        </div>
        <p v-if="availableDimensions.length === 0" class="empty-hint">暂无可用的评价维度</p>
      </div>
      <div class="dimension-loading" v-else>加载中...</div>

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
                  <input type="number" v-model.number="multiDimConfigs[dim.id].weight" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
                <div class="form-group">
                  <label>阈值（0-100）</label>
                  <input type="number" v-model.number="multiDimConfigs[dim.id].threshold" class="form-input" min="0" max="100" @input="emitUpdate" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import './DimensionConfigPanel.css';
</style>
