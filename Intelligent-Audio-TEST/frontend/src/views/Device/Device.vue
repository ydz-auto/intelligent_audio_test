<template>
  <div class="device-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-headphones"></i>
          设备管理
        </h2>
        <p class="page-description">管理语音测试使用的播放设备和测试设备</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="handleAddDevice">
          <i class="fas fa-plus btn-icon"></i>
          {{ addButtonText }}
        </button>
        <button class="btn btn-secondary" @click="scanDevices(activeTab)" v-if="activeTab !== DeviceTabType.API">
          <i class="fas fa-search btn-icon"></i>
          扫描设备
        </button>
        <button class="btn btn-secondary" @click="openGroupManager" v-if="activeTab === DeviceTabType.TEST">
          <i class="fas fa-layer-group btn-icon"></i>
          分组管理
        </button>

        <div class="dropdown">
          <button class="btn btn-secondary dropdown-toggle" @click="toggleDropdown('batchDropdown'); $event.stopPropagation()">
            <i class="fas fa-cogs btn-icon"></i>
            批量操作
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </button>
          <div id="batchDropdown" class="dropdown-menu" :class="{ active: dropdowns.batchDropdown }">
            <a href="#" @click.prevent="batchEnableDevices" class="dropdown-item">批量连接</a>
            <a href="#" @click.prevent="batchDisableDevices" class="dropdown-item">批量断开</a>
            <a href="#" @click.prevent="batchRebootDevices" class="dropdown-item">批量重启</a>
            <a href="#" @click.prevent="batchDeleteDevices" class="dropdown-item">批量删除</a>
            <a href="#" @click.prevent="batchHealthCheck" class="dropdown-item">批量健康度检查</a>
          </div>
        </div>
        <div class="dropdown">
          <button class="btn btn-secondary dropdown-toggle" @click="toggleDropdown('importExportDropdown'); $event.stopPropagation()">
            <i class="fas fa-exchange-alt btn-icon"></i>
            导入/导出
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </button>
          <div id="importExportDropdown" class="dropdown-menu" :class="{ active: dropdowns.importExportDropdown }">
            <a href="#" @click.prevent="importDevices" class="dropdown-item">导入设备</a>
            <a href="#" @click.prevent="exportDevices" class="dropdown-item">导出设备</a>
          </div>
        </div>
      </div>
    </div>

    <!-- 设备类型切换标签页 -->
    <div class="device-type-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.type"
        class="tab-btn"
        :class="{ active: activeTab === tab.type }"
        :data-device-type="tab.type"
        @click="switchDeviceType(tab.type)"
      >
        <i :class="tab.icon + ' tab-icon'"></i>
        {{ tab.label }}
      </button>
    </div>

    <!-- 设备状态概览 -->
    <div class="stats-grid">
      <div v-for="stat in stats" :key="stat.label" class="stat-card">
        <div class="stat-icon" :class="stat.iconClass">
          <i :class="stat.icon"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ stat.value }}</h3>
          <p class="stat-label">{{ stat.label }}</p>
        </div>
      </div>
    </div>

    <!-- 播放设备管理内容区域 -->
    <div id="playbackDeviceContent" v-show="activeTab === DeviceTabType.PLAYBACK">
      <div class="device-three-column-layout">
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-headphones"></i> 设备列表</h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input type="text" class="search-input" placeholder="搜索设备名称或型号..." v-model="searchQuery" @input="searchDevices">
                  </div>
                  <BadgeFilter
                    :options="DEVICE_STATUS_OPTIONS"
                    :model-value="statusFilter"
                    all-label="所有状态"
                    title="状态"
                    @update:model-value="setStatusFilter"
                  />
                  <BadgeFilter
                    :options="PLAYBACK_TYPE_OPTIONS"
                    :model-value="playbackTypeFilter"
                    all-label="所有类型"
                    title="播放类型"
                    @update:model-value="setPlaybackTypeFilter"
                  />
                </div>
              </div>
            </div>
            <div class="card-body">
              <div class="devices-grid">
                <div v-if="filteredPlaybackDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                <DeviceCard
                  v-else
                  v-for="device in filteredPlaybackDevices"
                  :key="device.id"
                  :device="device"
                  :selected="selectedDevices.includes(device.id)"
                  :status-text-map="deviceStatusText"
                  @toggle-select="toggleDeviceSelection(device.id)"
                  @edit="openEditModal(device.id)"
                  @delete="deleteDevice(device.id)"
                  @test="device.status === DeviceStatus.TESTING ? stopTest(device.id) : testDevice(device.id)"
                  @health-check="healthCheckDevice(device.id)"
                >
                  <template #meta="{ device }">
                    <div class="device-meta">
                      <span class="meta-item"><i class="fas fa-tags"></i> {{ device.category }}</span>
                      <span class="meta-item"><i class="fas fa-volume-up"></i> {{ device.type }}</span>
                      <span class="meta-item"><i class="fas fa-wifi"></i> {{ device.ip }}</span>
                    </div>
                  </template>
                  <template #specs="{ device }">
                    <div class="spec-item"><label>固件版本</label><span>{{ device.firmwareVersion }}</span></div>
                    <div class="spec-item"><label>最后在线</label><span>{{ device.lastOnline }}</span></div>
                    <div class="spec-item"><label>播放延迟</label><span :class="getDelayClass(device.delay)">{{ device.delay }}ms</span></div>
                    <div class="spec-item"><label>音量水平</label><span class="status-good">{{ device.volume }}dB</span></div>
                    <div class="spec-item"><label>连接稳定性</label><span class="status-good">{{ device.stability }}%</span></div>
                  </template>
                </DeviceCard>
              </div>
              <div class="pagination-container" v-if="playbackTotalItems > playbackPageSize">
                <PaginationComponent
                  :current-page="playbackCurrentPage"
                  :page-size="playbackPageSize"
                  :total-items="playbackTotalItems"
                  :total-pages="playbackTotalPages"
                  @prev-page="handlePlaybackPrevPage"
                  @next-page="handlePlaybackNextPage"
                  @go-to-page="handlePlaybackPageChange"
                  @page-size-change="handlePlaybackPageSizeChange"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 测试设备管理内容区域 -->
    <div id="testDeviceContent" v-show="activeTab === DeviceTabType.TEST">
      <div class="device-three-column-layout">
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-microphone"></i> 测试设备列表</h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input type="text" class="search-input" placeholder="搜索测试设备名称或型号..." v-model="searchQuery" @input="searchDevices">
                  </div>
                  <BadgeFilter
                    :options="DEVICE_STATUS_OPTIONS"
                    :model-value="statusFilter"
                    all-label="所有状态"
                    title="状态"
                    @update:model-value="setStatusFilter"
                  />
                  <div class="filter-select">
                    <select class="form-input" v-model="algorithmFilter" @change="filterDevices" id="algorithmFilter">
                      <option value="all">支持算法: 全部</option>
                      <option v-for="algo in algorithmTypeOptions" :key="algo.value" :value="algo.value">{{ algo.label }}</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="card-body">
              <div class="devices-grid">
                <div v-if="filteredTestDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                <DeviceCard
                  v-else
                  v-for="device in filteredTestDevices"
                  :key="device.id"
                  :device="device"
                  :selected="selectedDevices.includes(device.id)"
                  :status-text-map="deviceStatusText"
                  :show-operations="true"
                  @toggle-select="toggleDeviceSelection(device.id)"
                  @edit="openEditModal(device.id)"
                  @delete="deleteDevice(device.id)"
                  @test="device.status === DeviceStatus.TESTING ? stopTest(device.id) : testDevice(device.id)"
                  @health-check="healthCheckDevice(device.id)"
                  @operate="(op: string) => handleDeviceOperate(device.id, op)"
                >
                  <template #meta="{ device }">
                    <div class="device-meta">
                      <span class="meta-item"><i class="fas fa-tags"></i> {{ device.category }}</span>
                      <span class="meta-item"><i class="fas fa-microphone"></i> 测试设备</span>
                      <span class="meta-item"><i class="fas fa-wifi"></i> {{ device.ip }}</span>
                      <span class="meta-item"><i class="fas fa-serial"></i> {{ device.serialNumber }}</span>
                      <span class="meta-item" v-if="device.driverName || device.keywords"><i class="fas fa-key"></i> {{ device.driverName || device.keywords }}</span>
                    </div>
                  </template>
                  <template #specs="{ device }">
                    <div class="spec-item"><label>固件版本</label><span>{{ device.firmwareVersion }}</span></div>
                    <div class="spec-item"><label>最后在线</label><span>{{ device.lastOnline }}</span></div>
                    <div class="spec-item"><label>测试延迟</label><span :class="getDelayClass(device.delay)">{{ device.delay }}ms</span></div>
                    <div class="spec-item"><label>采样率</label><span class="status-good">{{ device.sampleRate }}kHz</span></div>
                    <div class="spec-item"><label>连接稳定性</label><span class="status-good">{{ device.stability }}%</span></div>
                  </template>
                </DeviceCard>
              </div>
              <div class="pagination-container" v-if="testTotalItems > testPageSize">
                <PaginationComponent
                  :current-page="testCurrentPage"
                  :page-size="testPageSize"
                  :total-items="testTotalItems"
                  :total-pages="testTotalPages"
                  @prev-page="handleTestPrevPage"
                  @next-page="handleTestNextPage"
                  @go-to-page="handleTestPageChange"
                  @page-size-change="handleTestPageSizeChange"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 测试API管理内容区域 -->
    <div id="apiDeviceContent" v-show="activeTab === DeviceTabType.API">
      <div class="device-three-column-layout">
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-exchange-alt"></i> 测试API列表</h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input type="text" class="search-input" placeholder="搜索测试API名称或URL..." v-model="searchQuery" @input="searchDevices">
                  </div>
                  <BadgeFilter
                    :options="DEVICE_STATUS_OPTIONS"
                    :model-value="statusFilter"
                    all-label="所有状态"
                    title="状态"
                    @update:model-value="setStatusFilter"
                  />
                  <div class="filter-select">
                    <select class="form-input" v-model="algorithmTypeFilter" @change="filterDevices" id="apiAlgorithmTypeFilter">
                      <option value="all">所有算法类型</option>
                      <option v-for="algo in algorithmTypeOptions" :key="algo.value" :value="algo.value">{{ algo.label }}</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="card-body">
              <div class="devices-grid">
                <div v-if="filteredAPIDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                <DeviceCard
                  v-else
                  v-for="device in filteredAPIDevices"
                  :key="device.id"
                  :device="device"
                  :selected="selectedDevices.includes(device.id)"
                  :status-text-map="deviceStatusText"
                  :show-test="false"
                  @toggle-select="toggleDeviceSelection(device.id)"
                  @edit="openEditModal(device.id)"
                  @delete="deleteDevice(device.id)"
                  @health-check="healthCheckDevice(device.id)"
                >
                  <template #meta="{ device }">
                    <div class="device-meta">
                      <span class="meta-item" v-if="device.algorithmType"><i class="fas fa-microchip"></i> {{ getAlgorithmTypeName(device.algorithmType) }}</span>
                      <span class="meta-item"><i class="fas fa-tags"></i> {{ device.category }}</span>
                      <span class="meta-item"><i class="fas fa-exchange-alt"></i> {{ device.method }}</span>
                      <span class="meta-item"><i class="fas fa-clock"></i> {{ device.responseTime }}ms</span>
                    </div>
                  </template>
                  <template #specs="{ device }">
                    <div class="spec-item"><label>API版本</label><span>{{ device.version }}</span></div>
                    <div class="spec-item"><label>最后测试时间</label><span>{{ device.lastTested }}</span></div>
                    <div class="spec-item"><label>成功率</label><span class="status-good">{{ device.successRate }}%</span></div>
                    <div class="spec-item"><label>认证类型</label><span>{{ device.authType }}</span></div>
                  </template>
                </DeviceCard>
              </div>
              <div class="pagination-container" v-if="apiTotalItems > apiPageSize">
                <PaginationComponent
                  :current-page="apiCurrentPage"
                  :page-size="apiPageSize"
                  :total-items="apiTotalItems"
                  :total-pages="apiTotalPages"
                  @prev-page="handleAPIPrevPage"
                  @next-page="handleAPINextPage"
                  @go-to-page="handleAPIPageChange"
                  @page-size-change="handleAPIPageSizeChange"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 设备分组管理弹窗（INT-80） -->
    <DeviceGroupManager
      v-model:visible="groupManagerVisible"
      :test-devices="testDevices"
      @changed="fetchAllDevices"
    />
  </div>
</template>

<script setup lang="ts">
import { useDevice } from './Device';
import { DeviceStatus, DeviceTabType } from '../../domain/enums';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import DeviceCard from './DeviceCard.vue';
import DeviceGroupManager from './DeviceGroupManager.vue';

const {
  tabs,
  activeTab,
  dropdowns,
  groupManagerVisible,
  searchQuery,
  statusFilter,
  playbackTypeFilter,
  algorithmFilter,
  algorithmTypeFilter,
  algorithmTypeOptions,
  getAlgorithmTypeName,
  deviceStatusText,
  playbackDevices,
  testDevices,
  apiDevices,
  selectedDevices,
  addButtonText,
  stats,
  filteredPlaybackDevices,
  filteredTestDevices,
  filteredAPIDevices,
  switchDeviceType,
  toggleDropdown,
  handleAddDevice,
  searchDevices,
  filterDevices,
  showDeviceDetails,
  getDelayClass,
  toggleDeviceSelection,
  resetAllStates,
  fetchAllDevices,
  openEditModal,
  deleteDevice,
  testDevice,
  stopTest,
  healthCheckDevice,
  scanDevices,
  batchEnableDevices,
  batchDisableDevices,
  batchRebootDevices,
  batchDeleteDevices,
  batchHealthCheck,
  importDevices,
  exportDevices,
  openGroupManager,
  handleDeviceOperate,
  playbackCurrentPage,
  playbackPageSize,
  playbackTotalItems,
  playbackTotalPages,
  handlePlaybackPageChange,
  handlePlaybackPageSizeChange,
  handlePlaybackPrevPage,
  handlePlaybackNextPage,
  testCurrentPage,
  testPageSize,
  testTotalItems,
  testTotalPages,
  handleTestPageChange,
  handleTestPageSizeChange,
  handleTestPrevPage,
  handleTestNextPage,
  apiCurrentPage,
  apiPageSize,
  apiTotalItems,
  apiTotalPages,
  handleAPIPageChange,
  handleAPIPageSizeChange,
  handleAPIPrevPage,
  handleAPINextPage
} = useDevice();

// ===== 徽章筛选选项（原下拉框硬编码迁移为常量）=====
const DEVICE_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: DeviceStatus.ONLINE, label: '在线' },
  { value: DeviceStatus.OFFLINE, label: '离线' },
  { value: DeviceStatus.TESTING, label: '测试中' },
];

const PLAYBACK_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '干声', label: '干声' },
  { value: '噪声', label: '噪声' },
];

function setStatusFilter(value: string | number) {
  // deviceState 中 statusFilter 类型收窄为 ViewMode.ALL 字面量，实际运行值为设备状态字符串，此处显式放宽
  statusFilter.value = String(value) as any;
}

function setPlaybackTypeFilter(value: string | number) {
  playbackTypeFilter.value = String(value) as any;
}
</script>

<style scoped>@import './Device.css';

/* 筛选栏：徽章筛选需占满可用宽度并允许换行 */
.card-actions {
  flex: 1;
  min-width: 0;
}

.filter-bar {
  flex-wrap: wrap !important;
  white-space: normal !important;
  align-items: center !important;
  gap: 12px 16px !important;
  width: 100% !important;
}


.middle-content{
    width: 100%;
}

.status-good{
    color: var(--success-color);
}

.dropdown{
    position: relative;
    display: inline-block;
}

.dropdown button{
    position: relative;
    z-index: 1001;
}

.device-type-tabs{
    display: flex;
    gap: 8px;
    margin-bottom: var(--spacing-xl);
    background-color: var(--background-secondary);
    padding: 4px;
    border-radius: var(--border-radius-lg);
}

@media (max-width: 768px){
.device-type-tabs {
        flex-direction: column;
}
}
/* device-three-column-layout - 自全局样式就近迁移 */
.device-three-column-layout{
    display: flex;
    flex-direction: column;
    gap: var(--spacing-lg);
    margin-bottom: var(--spacing-xl);
    transition: all var(--transition-normal);
}

/* middle-content - 自全局样式就近迁移 */


/* devices-grid - 自全局样式就近迁移 */
.devices-grid{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
    margin-top: 20px;
}

@media (max-width: 1200px){
.devices-grid {
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}
}

@media (max-width: 768px){
.devices-grid {
        grid-template-columns: 1fr;
}
}
/* device-meta - 自全局样式就近迁移 */
.device-meta{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}

</style>
