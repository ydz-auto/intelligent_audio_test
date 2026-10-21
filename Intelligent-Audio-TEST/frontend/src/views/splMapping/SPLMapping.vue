<template>
  <div class="spl-mapping-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary);">
          <i class="fas fa-sliders-h"></i>
          声压级映射管理
        </h2>
        <p class="page-description">
          设备 SPL（E2E 物理域）与 API/Realtime RMS-SPL（数字域）双口径映射管理，三口径对称（08 §六）
        </p>
      </div>
      <div class="header-right" v-if="activeTab === SplTabType.DEVICE">
        <button class="btn btn-primary" @click="openAddMappingModal">
          <i class="fas fa-plus btn-icon"></i>
          添加增益映射
        </button>
        <button class="btn btn-secondary" @click="importMappingData">
          <i class="fas fa-upload btn-icon"></i>
          导入映射数据
        </button>
      </div>
      <div class="header-right" v-else>
        <button class="btn btn-primary" @click="apiRms.openAddMappingModal()">
          <i class="fas fa-plus btn-icon"></i>
          添加 RMS-SPL 映射
        </button>
      </div>
    </div>

    <!-- 口径页签：设备 SPL（E2E）| API/Realtime RMS-SPL（数字域）—— INT-300 -->
    <div class="spl-domain-tabs">
      <button
        v-for="tab in SPL_TABS"
        :key="tab.type"
        class="domain-tab-btn"
        :class="{ active: activeTab === tab.type }"
        @click="switchTab(tab.type)"
      >
        <i :class="tab.icon"></i>
        {{ tab.label }}
      </button>
    </div>

    <!-- ============ 分区一：设备 SPL（E2E 物理域，原实现不动） ============ -->
    <div v-show="activeTab === SplTabType.DEVICE">
      <!-- 声压级映射概览 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon device-icon">
            <i class="fas fa-sliders-h"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ stats.total }}</h3>
            <p class="stat-label">增益映射数</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon active-icon">
            <i class="fas fa-check-circle"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ stats.calibrated }}</h3>
            <p class="stat-label">已校准</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon inactive-icon">
            <i class="fas fa-times-circle"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ stats.uncalibrated }}</h3>
            <p class="stat-label">未校准</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon test-icon">
            <i class="fas fa-headphones"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ stats.associatedDevices }}</h3>
            <p class="stat-label">关联设备数</p>
          </div>
        </div>
      </div>

      <!-- 映射关系列表 -->
      <div class="spl-mapping-section">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-list"></i>
              映射关系列表
            </h3>
            <div class="card-actions">
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input type="text" class="search-input" placeholder="搜索映射名称或设备..." v-model="searchTerm" @input="searchMappings">
              </div>
              <!-- INT-293：原生 select 迁移 BadgeFilter（对齐 Device.vue 筛选栏视觉） -->
              <div class="filter-bar">
                <BadgeFilter
                  :options="CALIBRATION_STATUS_OPTIONS"
                  :model-value="calibrationFilter"
                  all-label="所有状态"
                  title="状态"
                  @update:model-value="onCalibrationFilterChange"
                />
                <BadgeFilter
                  :options="deviceFilterOptions"
                  :model-value="deviceFilter"
                  all-label="所有设备"
                  title="设备"
                  @update:model-value="onDeviceFilterChange"
                />
              </div>
            </div>
          </div>
          <div class="card-body">
            <!-- INT-289 加载态：首载无数据时展示 spinner（刷新保留旧数据不闪） -->
            <div v-if="loading && paginatedMappings.length === 0" class="spl-mapping-loading">
              <span class="loading-spinner"></span> 正在加载映射列表...
            </div>
            <!-- INT-289 空态：加载完成后无映射时给出引导文案，与错误态区分 -->
            <div v-else-if="!loading && paginatedMappings.length === 0" class="spl-mapping-empty">
              <i class="fas fa-info-circle"></i>
              <p>暂无增益映射。点击右上角「添加增益映射」创建，或「导入映射数据」批量导入。</p>
            </div>
            <!-- 映射卡片网格 -->
            <div v-else class="mapping-grid">
              <!-- 增益映射卡片 -->
              <div class="mapping-card" v-for="(mapping, index) in paginatedMappings" :key="mapping.id">
                <div class="mapping-card-header">
                  <h4 class="mapping-name">{{ mapping.name }}</h4>
                  <span class="status-badge" :class="mapping.calibrationStatus">{{ mapping.calibrationStatus === 'calibrated' ? '已校准' : '未校准' }}</span>
                </div>
                <div class="mapping-card-content">
                  <div class="mapping-info">
                    <p><strong>关联设备：</strong>{{ mapping.deviceName }}{{ mapping.deviceModel ? ` (${mapping.deviceModel})` : '' }}</p>
                    <p v-if="mapping.description"><strong>描述：</strong>{{ mapping.description }}</p>
                    <p><strong>校准点数：</strong>{{ mapping.calibrationPointsCount || 0 }}</p>
                    <p><strong>更新时间：</strong>{{ mapping.measurementDate || '未校准' }}</p>
                  </div>
                  <div class="mapping-details">
                    <div class="detail-item">
                      <span class="detail-label">增益偏移范围</span>
                      <span class="detail-value">{{ mapping.gainOffsetMin !== null && mapping.gainOffsetMax !== null ? `${mapping.gainOffsetMin} ~ ${mapping.gainOffsetMax}` : '-' }} dB</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">SPL范围</span>
                      <span class="detail-value">{{ mapping.minOffsetSpl ? mapping.minOffsetSpl.toFixed(0) : '-' }}-{{ mapping.maxOffsetSpl ? mapping.maxOffsetSpl.toFixed(0) : '-' }} dB</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">基础电平</span>
                      <span class="detail-value">{{ mapping.baseLevel !== null ? mapping.baseLevel.toFixed(1) : '-' }} dBFS</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">最终电平范围</span>
                      <span class="detail-value">{{ mapping.finalLevelMin !== null && mapping.finalLevelMax !== null ? (mapping.finalLevelMin.toFixed(1) + ' ~ ' + mapping.finalLevelMax.toFixed(1)) : '-' }} dBFS</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">测量距离</span>
                      <span class="detail-value">{{ mapping.distance }} 米</span>
                    </div>
                  </div>
                  <div class="mapping-chart">
                    <canvas :id="'chart-' + mapping.id"></canvas>
                  </div>
                  <div class="mapping-actions">
                    <button class="btn btn-primary" @click="editMapping(mapping)">
                      <i class="fas fa-edit btn-icon"></i>
                      编辑
                    </button>
                    <button class="btn btn-secondary" @click="viewMappingDetails(mapping)">
                      <i class="fas fa-eye btn-icon"></i>
                      详情
                    </button>
                    <button class="btn btn-danger" @click="handleDeleteMapping(mapping.id)">
                      <i class="fas fa-trash btn-icon"></i>
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页控件 -->
      <div class="pagination-container" v-if="totalItems > pageSize">
        <PaginationComponent
          :current-page="currentPage"
          :page-size="pageSize"
          :total-items="totalItems"
          :total-pages="totalPages"
          @prev-page="handlePrevPage"
          @next-page="handleNextPage"
          @go-to-page="handlePageChange"
          @page-size-change="handlePageSizeChange"
        />
      </div>

      <!-- INT-293：映射总数超过单次拉取上限时的截断提示（不再静默截断） -->
      <div v-if="mappingListTruncated" class="spl-truncated-hint">
        <i class="fas fa-info-circle"></i>
        <p>映射总数超过 {{ SPL_MAPPING_FETCH_LIMIT }} 条，列表仅展示前 {{ SPL_MAPPING_FETCH_LIMIT }} 条，请使用上方的状态/设备筛选定位。</p>
      </div>
    </div>

    <!-- ============ 分区二：API/Realtime RMS-SPL（数字域）—— INT-300 ============ -->
    <div v-show="activeTab === SplTabType.API_RMS">
      <!-- 概览 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon device-icon">
            <i class="fas fa-exchange-alt"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ apiRms.stats.value.total }}</h3>
            <p class="stat-label">RMS-SPL 映射数</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon active-icon">
            <i class="fas fa-check-circle"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ apiRms.stats.value.calibrated }}</h3>
            <p class="stat-label">已校准</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon inactive-icon">
            <i class="fas fa-times-circle"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ apiRms.stats.value.uncalibrated }}</h3>
            <p class="stat-label">未校准</p>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon test-icon">
            <i class="fas fa-network-wired"></i>
          </div>
          <div class="stat-content">
            <h3 class="stat-number">{{ apiRms.stats.value.associatedApis }}</h3>
            <p class="stat-label">关联 API 数</p>
          </div>
        </div>
      </div>

      <!-- 映射表格 -->
      <div class="spl-mapping-section">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-list"></i>
              RMS-SPL 映射列表
            </h3>
            <div class="card-actions">
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input type="text" class="search-input" placeholder="搜索映射名称/API..." v-model="apiRms.searchTerm.value" @input="apiRms.filterMappings()">
              </div>
              <!-- INT-293：原生 select 迁移 BadgeFilter（对齐 Device.vue 筛选栏视觉） -->
              <div class="filter-bar">
                <BadgeFilter
                  :options="CALIBRATION_STATUS_OPTIONS"
                  :model-value="apiRms.calibrationFilter.value"
                  all-label="所有状态"
                  title="状态"
                  @update:model-value="onApiCalibrationFilterChange"
                />
                <BadgeFilter
                  :options="apiFilterOptions"
                  :model-value="apiRms.apiFilter.value"
                  all-label="所有 API"
                  title="API"
                  @update:model-value="onApiFilterChange"
                />
              </div>
            </div>
          </div>
          <div class="card-body">
            <div class="rms-table-wrapper">
              <table class="rms-spl-table">
                <thead>
                  <tr>
                    <th>映射名称</th>
                    <th>关联 API</th>
                    <th>参考基准</th>
                    <th>校准点数</th>
                    <th>增益限幅</th>
                    <th>状态</th>
                    <th>默认</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="apiRms.loading.value">
                    <td colspan="8" class="table-empty">
                      <span class="loading-spinner"></span> 加载中...
                    </td>
                  </tr>
                  <tr v-else-if="apiRms.filteredMappings.value.length === 0">
                    <td colspan="8" class="table-empty">
                      <i class="fas fa-info-circle"></i>
                      暂无 RMS-SPL 映射。点击右上角「添加 RMS-SPL 映射」为被测 API 配置数字域灵敏度。
                    </td>
                  </tr>
                  <tr v-else v-for="mapping in apiRms.paginatedMappings.value" :key="mapping.id">
                    <td class="cell-name">{{ mapping.name || `映射 #${mapping.id}` }}</td>
                    <td>{{ apiRms.apiName(mapping.apiId) }}</td>
                    <td>
                      {{ mapping.referenceSpl ?? '-' }} dB /
                      {{ mapping.referenceGainLinear ?? '-' }}
                    </td>
                    <td>{{ mapping.calibrationPoints?.length ?? 0 }}</td>
                    <td>{{ mapping.minGainLinear ?? '-' }} ~ {{ mapping.maxGainLinear ?? '-' }}</td>
                    <td>
                      <span class="status-badge" :class="mapping.calibrationStatus">
                        {{ CALIBRATION_STATUS_LABELS[mapping.calibrationStatus ?? ''] || (mapping.calibrationStatus || '未校准') }}
                      </span>
                    </td>
                    <td>
                      <span v-if="apiRms.isDefaultMapping(mapping)" class="default-badge">
                        <i class="fas fa-star"></i> 默认
                      </span>
                      <span v-else class="text-muted">-</span>
                    </td>
                    <td class="cell-actions">
                      <button class="btn btn-small btn-primary" @click="apiRms.openCalibrationModal(mapping)" title="数字校准（点集全量替换并置已校准）">
                        <i class="fas fa-bullseye"></i> 校准
                      </button>
                      <button
                        class="btn btn-small"
                        :class="apiRms.isDefaultMapping(mapping) ? 'btn-warning' : 'btn-secondary'"
                        @click="apiRms.toggleDefaultMapping(mapping)"
                        :title="apiRms.isDefaultMapping(mapping) ? '清除默认映射' : '设为该 API 当前默认映射'"
                      >
                        <i :class="apiRms.isDefaultMapping(mapping) ? 'fas fa-star-half-alt' : 'fas fa-star'"></i>
                        {{ apiRms.isDefaultMapping(mapping) ? '清除默认' : '设默认' }}
                      </button>
                      <button class="btn btn-small btn-secondary" @click="apiRms.viewMappingDetails(mapping)">
                        <i class="fas fa-eye"></i> 详情
                      </button>
                      <button class="btn btn-small btn-secondary" @click="apiRms.openEditMappingModal(mapping)">
                        <i class="fas fa-edit"></i> 编辑
                      </button>
                      <button class="btn btn-small btn-danger" @click="apiRms.handleDeleteMapping(mapping)">
                        <i class="fas fa-trash"></i> 删除
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页控件（INT-330 缺陷3：API 分区对齐设备侧分页交互） -->
      <div class="pagination-container" v-if="apiRms.totalItems.value > apiRms.pageSize.value">
        <PaginationComponent
          :current-page="apiRms.currentPage.value"
          :page-size="apiRms.pageSize.value"
          :total-items="apiRms.totalItems.value"
          :total-pages="apiRms.totalPages.value"
          @go-to-page="apiRms.goToPage"
          @prev-page="apiRms.prevPage"
          @next-page="apiRms.nextPage"
          @page-size-change="apiRms.setPageSize"
        />
      </div>

      <!-- 校准点明细（每条映射的校准历史对齐设备侧卡片） -->
      <div class="spl-mapping-section" v-if="calibratedMappings.length > 0">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-history"></i>
              校准点明细（已校准映射）
            </h3>
          </div>
          <div class="card-body">
            <div class="calibration-detail-grid">
              <div class="calibration-detail-card" v-for="mapping in calibratedMappings" :key="`detail-${mapping.id}`">
                <div class="detail-card-header">
                  <h5>{{ mapping.name || `映射 #${mapping.id}` }}</h5>
                  <span class="status-badge calibrated">已校准</span>
                </div>
                <p class="detail-api">{{ apiRms.apiName(mapping.apiId) }}</p>
                <div class="detail-points">
                  <div class="detail-point" v-for="(p, idx) in sortedPoints(mapping)" :key="idx">
                    <span class="point-spl">{{ p.targetSpl }} dB</span>
                    <i class="fas fa-arrow-right point-arrow"></i>
                    <span class="point-gain">{{ p.gainLinear }}</span>
                    <span class="point-db">({{ gainToDb(p.gainLinear) }})</span>
                    <span class="point-rms" v-if="p.rmsDbfs != null">{{ p.rmsDbfs }} dBFS</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 三口径对称提示（对齐 INT-263 验收手册 F1-F5） -->
      <div class="symmetric-hint">
        <i class="fas fa-balance-scale"></i>
        <p>
          三口径对称：E2E 物理映射挂播放设备（device_service spl_mappings）；API/Realtime 数字 RMS 映射挂被测 API
          （api_rms_spl_mappings，非实时/流式/Realtime 通用）。执行时按被测设备类型查不同映射表：
          API 配 SPL → RMS 补偿（归一 -30 dBFS）× 映射增益（未校准按参考线性近似），结果与 E2E 同基准可比。
        </p>
      </div>
    </div>

    <!-- 全局模态框将在此处自动渲染 -->
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/progress.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/tasks/stats.css"
import "../../assets/styles/device/device.css"
import { useSplMapping, SPL_MAPPING_FETCH_LIMIT } from '../../composables/device/useSplMapping';
import { useApiRmsSpl, CALIBRATION_STATUS_LABELS } from '../../composables/apiTest/useApiRmsSpl';
import { onMounted, ref, computed } from 'vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import { CalibrationStatus } from '../../domain/enums';
import type { ApiCalibrationPoint } from '../../domain';

/** SPL 页面口径页签类型（enum 化，禁止魔法字符串） */
const SplTabType = {
  /** 设备 SPL（E2E 物理域） */
  DEVICE: 'device',
  /** API/Realtime RMS-SPL（数字域） */
  API_RMS: 'apiRms',
} as const;
type SplTabTypeValue = typeof SplTabType[keyof typeof SplTabType];

const SPL_TABS: Array<{ type: SplTabTypeValue; label: string; icon: string }> = [
  { type: SplTabType.DEVICE, label: '设备 SPL（E2E）', icon: 'fas fa-sliders-h' },
  { type: SplTabType.API_RMS, label: 'API/Realtime RMS-SPL', icon: 'fas fa-exchange-alt' },
];

const activeTab = ref<SplTabTypeValue>(SplTabType.DEVICE);

function switchTab(type: SplTabTypeValue) {
  activeTab.value = type;
  // 首次切到数字域分区时懒加载数据
  if (type === SplTabType.API_RMS && !apiRmsLoaded) {
    apiRmsLoaded = true;
    apiRms.initData();
  }
}

let apiRmsLoaded = false;

const {
  searchTerm,
  calibrationFilter,
  deviceFilter,
  paginatedMappings,
  stats,
  playbackDevices,
  loading,
  mappingListTruncated,
  showModal,
  showDetailsModal,
  searchMappings,
  filterMappings,
  filterByDevice,
  openAddMappingModal,
  editMapping,
  viewMappingDetails,
  handleDeleteMapping,
  importMappingData,
  fetchDevices,
  initModalWatchers,
  initData,
  initCharts,
  // 分页相关
  currentPage,
  pageSize,
  totalItems,
  totalPages,
  handlePageChange,
  handlePageSizeChange,
  handlePrevPage,
  handleNextPage
} = useSplMapping();

const apiRms = useApiRmsSpl();

// ===== 徽章筛选（INT-293：原生 select 迁移 BadgeFilter，选项与回调本地收敛） =====
/** 校准状态筛选选项（设备域与数字域共用同一口径） */
const CALIBRATION_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'calibrated', label: '已校准' },
  { value: 'uncalibrated', label: '未校准' },
];

/** 设备筛选选项（playbackDevices → {value: string, label}） */
const deviceFilterOptions = computed(() =>
  playbackDevices.value.map(d => ({
    value: String(d.id),
    label: `${d.name}${d.model ? ` (${d.model})` : ''}`
  }))
);

/** API 筛选选项（数字域：apiRms.apiList → {value: string, label}） */
const apiFilterOptions = computed(() =>
  apiRms.apiList.value.map(a => ({
    value: String(a.id),
    label: `${a.name}${a.vendor ? ` (${a.vendor})` : ''}`
  }))
);

/** 设备域状态徽章选中 → 收窄为字面量联合后触发服务端筛选 */
function onCalibrationFilterChange(value: string | number) {
  calibrationFilter.value = String(value) as 'all' | 'calibrated' | 'uncalibrated';
  filterMappings();
}

function onDeviceFilterChange(value: string | number) {
  deviceFilter.value = String(value);
  filterByDevice();
}

/** 数字域状态/API 徽章选中 → 触发 apiRms 服务端筛选 */
function onApiCalibrationFilterChange(value: string | number) {
  apiRms.calibrationFilter.value = String(value) as 'all' | 'calibrated' | 'uncalibrated';
  apiRms.filterMappings();
}

function onApiFilterChange(value: string | number) {
  apiRms.apiFilter.value = String(value);
  apiRms.filterByApi();
}

/** 已校准映射（校准点明细区） */
const calibratedMappings = computed(() =>
  (apiRms.mappingData.value || []).filter(m => m.calibrationStatus === CalibrationStatus.CALIBRATED && (m.calibrationPoints?.length ?? 0) > 0)
);

/** 按 target_spl 升序展示校准点 */
function sortedPoints(mapping: { calibrationPoints?: ApiCalibrationPoint[] }): ApiCalibrationPoint[] {
  return [...(mapping.calibrationPoints ?? [])].sort((a, b) => a.targetSpl - b.targetSpl);
}

/** 线性增益 → dB 展示 */
function gainToDb(gain: number | undefined): string {
  if (gain == null || !Number.isFinite(gain) || gain <= 0) return '-';
  return `${(20 * Math.log10(gain)).toFixed(1)}dB`;
}

onMounted(async () => {
  await Promise.all([
    initData(),
    fetchDevices()
  ]);
  initModalWatchers();
  initCharts();
});
</script>

<style scoped>
@import './splMapping.css';

/* 徽章筛选替换原生 select 后：card-actions 允许换行（splMapping.css 原为 nowrap），
   对齐 Device.vue 筛选栏视觉 */
.card-actions {
    flex-wrap: wrap !important;
    white-space: normal !important;
    row-gap: 10px;
}

/* 映射总数超过单次拉取上限时的截断提示 */
.spl-truncated-hint {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-top: 16px;
    padding: 10px 14px;
    background: color-mix(in srgb, var(--color-ant-gold-6, #faad14) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-ant-gold-6, #faad14) 40%, transparent);
    border-radius: var(--radius-control, 8px);
    font-size: 12px;
    color: var(--muted-foreground);
}

.spl-truncated-hint i {
    color: var(--warning, #faad14);
    margin-top: 2px;
    flex-shrink: 0;
}

.spl-truncated-hint p {
    margin: 0;
    line-height: 1.6;
}


/* active-icon - 自全局样式就近迁移 */
.active-icon {
    background: color-mix(in srgb, var(--success) 10%, transparent);
    color: var(--success);
}
/* test-icon - 自全局样式就近迁移 */
.test-icon {
    background: color-mix(in srgb, var(--color-ant-gold-6) 10%, transparent);
    color: var(--warning);
}

/* ===== 口径页签（INT-300 双分区）—— 对齐 Device.vue 页签形态 ===== */
.spl-domain-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0;
}

.domain-tab-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 20px;
    border: none;
    background: transparent;
    color: var(--muted-foreground);
    font-size: 14px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all var(--transition-normal);
}

.domain-tab-btn:hover {
    color: var(--primary);
}

.domain-tab-btn.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
    font-weight: 600;
}

/* ===== RMS-SPL 映射表格 ===== */
.rms-table-wrapper {
    overflow-x: auto;
}

.rms-spl-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.rms-spl-table th,
.rms-spl-table td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}

.rms-spl-table th {
    background: var(--muted, #f7f8fa);
    color: var(--muted-foreground);
    font-weight: 600;
}

.rms-spl-table tbody tr:hover {
    background: color-mix(in srgb, var(--primary) 4%, transparent);
}

.cell-name {
    font-weight: 500;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
}

.default-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: var(--radius-control, 8px);
    font-size: 11px;
    background: color-mix(in srgb, var(--color-ant-gold-6, #faad14) 12%, transparent);
    color: var(--warning, #faad14);
}

.text-muted {
    color: var(--text-light);
}

.cell-actions {
    display: flex;
    gap: 4px;
    flex-wrap: nowrap;
}

.cell-actions .btn {
    padding: 4px 8px;
    font-size: 12px;
}

.table-empty {
    text-align: center;
    padding: 28px 12px !important;
    color: var(--text-light);
}

/* ===== 校准点明细 ===== */
.calibration-detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
}

.calibration-detail-card {
    border: 1px solid var(--border);
    border-radius: var(--radius-control, 8px);
    padding: 14px 16px;
    background: var(--background);
}

.detail-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}

.detail-card-header h5 {
    margin: 0;
    font-size: 14px;
    color: var(--foreground);
}

.detail-api {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--text-light);
}

.detail-points {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.detail-point {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-variant-numeric: tabular-nums;
}

.point-spl {
    font-weight: 600;
    color: var(--primary);
    min-width: 64px;
}

.point-arrow {
    color: var(--text-light);
    font-size: 10px;
}

.point-gain {
    color: var(--foreground);
    font-weight: 500;
}

.point-db {
    color: var(--muted-foreground);
}

.point-rms {
    margin-left: auto;
    color: var(--text-light);
}

/* ===== 三口径对称提示 ===== */
.symmetric-hint {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    margin-top: 20px;
    padding: 12px 16px;
    background: color-mix(in srgb, var(--primary) 5%, transparent);
    border-left: 3px solid var(--primary);
    border-radius: var(--radius-control, 8px);
}

.symmetric-hint i {
    color: var(--primary);
    margin-top: 2px;
}

.symmetric-hint p {
    margin: 0;
    font-size: 12px;
    color: var(--muted-foreground);
    line-height: 1.7;
}

/* btn-warning（清除默认按钮态） */
.btn-warning {
    background: color-mix(in srgb, var(--color-ant-gold-6, #faad14) 12%, transparent);
    color: var(--warning, #faad14);
    border: 1px solid color-mix(in srgb, var(--color-ant-gold-6, #faad14) 40%, transparent);
}
</style>
