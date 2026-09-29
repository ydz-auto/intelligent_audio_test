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
        <button class="btn btn-secondary" @click="scanDevices(activeTab)" v-if="activeTab !== 'api'">
          <i class="fas fa-search btn-icon"></i>
          扫描设备
        </button>

        <div class="dropdown">
          <button class="btn btn-secondary dropdown-toggle" @click="toggleDropdown('batchDropdown'); $event.stopPropagation()">
            <i class="fas fa-cogs btn-icon"></i>
            批量操作
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </button>
          <div id="batchDropdown" class="dropdown-menu" :class="{ active: dropdowns.batchDropdown }">
            <a href="#" @click.prevent="batchEnableDevices" class="dropdown-item">批量启用</a>
            <a href="#" @click.prevent="batchDisableDevices" class="dropdown-item">批量禁用</a>
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
    <div id="playbackDeviceContent" v-show="activeTab === 'playback'">
      <div class="device-three-column-layout">
        <!-- 中间设备列表区 -->
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">
                <i class="fas fa-headphones"></i>
                设备列表
              </h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input 
                      type="text" 
                      class="search-input" 
                      placeholder="搜索设备名称或型号..." 
                      v-model="searchQuery"
                      @input="searchDevices"
                    >
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
                <!-- 算法筛选（徽章单选） -->
                <div class="algorithm-filter-row">
                  <AlgorithmFilter :options="algorithmTypeOptions" v-model="algorithmFilter" title="支持算法" />
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- 设备卡片网格 - 滚动加载分页 -->
              <InfiniteScrollList
                :items="allFilteredPlaybackDevices"
                :page-size="playbackPageSize"
              >
                <template #default="{ items }">
                  <div class="devices-grid">
                    <div
                      v-for="device in items"
                      :key="device.id"
                      class="device-card fade-in"
                      @click="toggleDeviceSelection(device.id)"
                      :class="{ 'highlighted': selectedDevices.includes(device.id) }"
                    >
                      <div class="device-card-header">
                        <div class="device-select">
                          <input type="checkbox" class="device-checkbox" :value="device.id" v-model="selectedDevices" @click.stop>
                        </div>
                        <div class="device-status">
                          <span class="status-badge" :class="device.status">
                            <i :class="device.status === 'testing' ? 'fas fa-play-circle testing-indicator' : 'fas fa-circle online-indicator'"></i>
                            {{ deviceStatusText[device.status] }}
                          </span>
                        </div>
                      </div>
                      <div class="device-card-content">
                        <div class="device-info">
                          <h3 class="device-name">{{ device.name }}</h3>
                          <p class="device-model">{{ device.model }}</p>
                          <div class="device-description" v-if="device.description" style="margin-top: 8px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">
                            {{ device.description }}
                          </div>
                          <div class="device-algorithms" v-if="device.supportedAlgorithms && device.supportedAlgorithms.length > 0">
                            <span class="algo-label">支持算法:</span>
                            <AlgorithmTag :algorithms="device.supportedAlgorithms" :max-display="3" />
                          </div>
                          <div class="device-meta">
                            <span class="meta-item">
                              <i class="fas fa-tags"></i>
                              {{ device.category }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-volume-up"></i>
                              {{ device.type }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-wifi"></i>
                              {{ device.ip }}
                            </span>
                          </div>
                        </div>
                        <div class="device-specs">
                          <div class="spec-item">
                            <label>固件版本</label>
                            <span>{{ device.firmwareVersion }}</span>
                          </div>
                          <div class="spec-item">
                            <label>最后在线</label>
                            <span>{{ device.lastOnline }}</span>
                          </div>
                          <div class="spec-item">
                            <label>播放延迟</label>
                            <span :class="getDelayClass(device.delay)">{{ device.delay }}ms</span>
                          </div>
                          <div class="spec-item">
                            <label>音量水平</label>
                            <span class="status-good">{{ device.volume }}dB</span>
                          </div>
                          <div class="spec-item">
                            <label>连接稳定性</label>
                            <span class="status-good">{{ device.stability }}%</span>
                          </div>
                        </div>
                      </div>
                      <div class="device-card-footer">
                        <div class="connection-controls">
                          <button class="btn btn-secondary" @click="openEditModal(device.id); $event.stopPropagation();">
                            <i class="fas fa-edit btn-icon"></i>
                            编辑
                          </button>
                          <button class="btn btn-danger" @click="deleteDevice(device.id); $event.stopPropagation();">
                            <i class="fas fa-trash btn-icon"></i>
                            删除
                          </button>
                          <button
                            class="btn gradient-btn"
                            :class="device.status === 'testing' ? 'btn-danger' : 'btn-success'"
                            :disabled="device.status === 'offline'"
                            @click="device.status === 'testing' ? stopTest(device.id) : testDevice(device.id); $event.stopPropagation();"
                          >
                            <i :class="device.status === 'testing' ? 'fas fa-stop btn-icon' : 'fas fa-play btn-icon'"
                            ></i>
                            {{ device.status === 'testing' ? '停止测试' : device.status === 'offline' ? '离线' : '测试' }}
                          </button>
                          <button
                            class="btn btn-info"
                            @click="healthCheckDevice(device.id); $event.stopPropagation();"
                          >
                            <i class="fas fa-heartbeat btn-icon"></i>
                            健康检查
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #empty>
                  <div class="no-devices">
                    <i class="fas fa-info-circle"></i>
                    <p>无可用设备</p>
                  </div>
                </template>
              </InfiniteScrollList>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 测试设备管理内容区域 -->
    <div id="testDeviceContent" v-show="activeTab === 'test'">
      <div class="device-three-column-layout">
        <!-- 中间测试设备区 -->
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">
                <i class="fas fa-microphone"></i>
                测试设备列表
              </h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input 
                      type="text" 
                      class="search-input" 
                      placeholder="搜索测试设备名称或型号..." 
                      v-model="searchQuery"
                      @input="searchDevices"
                    >
                  </div>
                  <BadgeFilter
                    :options="DEVICE_STATUS_OPTIONS"
                    :model-value="statusFilter"
                    all-label="所有状态"
                    title="状态"
                    @update:model-value="setStatusFilter"
                  />
                </div>
                <!-- 算法筛选（徽章单选） -->
                <div class="algorithm-filter-row">
                  <AlgorithmFilter :options="algorithmTypeOptions" v-model="algorithmFilter" title="支持算法" />
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- 测试设备卡片网格 - 滚动加载分页 -->
              <InfiniteScrollList
                :items="allFilteredTestDevices"
                :page-size="testPageSize"
              >
                <template #default="{ items }">
                  <div class="devices-grid">
                    <div
                      v-for="device in items"
                      :key="device.id"
                      class="device-card fade-in"
                      @click="toggleDeviceSelection(device.id)"
                      :class="{ 'highlighted': selectedDevices.includes(device.id) }"
                    >
                      <div class="device-card-header">
                        <div class="device-select">
                          <input type="checkbox" class="device-checkbox" :value="device.id" v-model="selectedDevices" @click.stop>
                        </div>
                        <div class="device-status">
                          <span class="status-badge" :class="device.status">
                            <i :class="device.status === 'testing' ? 'fas fa-play-circle testing-indicator' : 'fas fa-circle online-indicator'"></i>
                            {{ deviceStatusText[device.status] }}
                          </span>
                        </div>
                      </div>
                      <div class="device-card-content">
                        <div class="device-info">
                          <h3 class="device-name">{{ device.name }}</h3>
                          <p class="device-model">{{ device.model }}</p>
                          <div class="device-description" v-if="device.description" style="margin-top: 8px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">
                            {{ device.description }}
                          </div>
                          <div class="device-algorithms" v-if="device.supportedAlgorithms && device.supportedAlgorithms.length > 0">
                            <span class="algo-label">支持算法:</span>
                            <AlgorithmTag :algorithms="device.supportedAlgorithms" :max-display="3" />
                          </div>
                          <div class="device-meta">
                            <span class="meta-item">
                              <i class="fas fa-tags"></i>
                              {{ device.category }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-microphone"></i>
                              测试设备
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-wifi"></i>
                              {{ device.ip }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-serial"></i>
                              {{ device.serialNumber }}
                            </span>
                            <span class="meta-item" v-if="device.driverName || device.keywords">
                              <i class="fas fa-key"></i>
                              {{ device.driverName || device.keywords }}
                            </span>
                          </div>
                        </div>
                        <div class="device-specs">
                          <div class="spec-item">
                            <label>固件版本</label>
                            <span>{{ device.firmwareVersion }}</span>
                          </div>
                          <div class="spec-item">
                            <label>最后在线</label>
                            <span>{{ device.lastOnline }}</span>
                          </div>
                          <div class="spec-item">
                            <label>测试延迟</label>
                            <span :class="getDelayClass(device.delay)">{{ device.delay }}ms</span>
                          </div>
                          <div class="spec-item">
                            <label>采样率</label>
                            <span class="status-good">{{ device.sampleRate }}kHz</span>
                          </div>
                          <div class="spec-item">
                            <label>连接稳定性</label>
                            <span class="status-good">{{ device.stability }}%</span>
                          </div>
                        </div>
                      </div>
                      <div class="device-card-footer">
                        <div class="connection-controls">
                          <button class="btn btn-secondary" @click="openEditModal(device.id); $event.stopPropagation();">
                            <i class="fas fa-edit btn-icon"></i>
                            编辑
                          </button>
                          <button class="btn btn-danger" @click="deleteDevice(device.id); $event.stopPropagation();">
                            <i class="fas fa-trash btn-icon"></i>
                            删除
                          </button>
                          <button
                            class="btn gradient-btn"
                            :class="device.status === 'testing' ? 'btn-danger' : 'btn-success'"
                            @click="device.status === 'testing' ? stopTest(device.id) : testDevice(device.id); $event.stopPropagation();"
                          >
                            <i :class="device.status === 'testing' ? 'fas fa-stop btn-icon' : 'fas fa-play btn-icon'"
                            ></i>
                            {{ device.status === 'testing' ? '停止测试' : '测试' }}
                          </button>
                          <button
                            class="btn btn-info"
                            @click="healthCheckDevice(device.id); $event.stopPropagation();"
                          >
                            <i class="fas fa-heartbeat btn-icon"></i>
                            健康检查
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #empty>
                  <div class="no-devices">
                    <i class="fas fa-info-circle"></i>
                    <p>无可用设备</p>
                  </div>
                </template>
              </InfiniteScrollList>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 测试API管理内容区域 -->
    <div id="apiDeviceContent" v-show="activeTab === 'api'">
      <div class="device-three-column-layout">
        <!-- 中间API设备区 -->
        <div class="middle-content">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">
                <i class="fas fa-exchange-alt"></i>
                测试API列表
              </h3>
              <div class="card-actions">
                <div class="filter-bar">
                  <div class="search-box">
                    <i class="fas fa-search search-icon"></i>
                    <input 
                      type="text" 
                      class="search-input" 
                      placeholder="搜索测试API名称或URL..." 
                      v-model="searchQuery"
                      @input="searchDevices"
                    >
                  </div>
                  <BadgeFilter
                    :options="DEVICE_STATUS_OPTIONS"
                    :model-value="statusFilter"
                    all-label="所有状态"
                    title="状态"
                    @update:model-value="setStatusFilter"
                  />
                </div>
                <!-- 算法筛选（徽章单选） -->
                <div class="algorithm-filter-row">
                  <AlgorithmFilter :options="algorithmTypeOptions" v-model="algorithmTypeFilter" title="算法类型" />
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- API设备卡片网格 - 滚动加载分页 -->
              <InfiniteScrollList
                :items="allFilteredAPIDevices"
                :page-size="apiPageSize"
              >
                <template #default="{ items }">
                  <div class="devices-grid">
                    <div
                      v-for="device in items"
                      :key="device.id"
                      class="device-card fade-in"
                      @click="toggleDeviceSelection(device.id)"
                      :class="{ 'highlighted': selectedDevices.includes(device.id) }"
                    >
                      <div class="device-card-header">
                        <div class="device-select">
                          <input type="checkbox" class="device-checkbox" :value="device.id" v-model="selectedDevices" @click.stop>
                        </div>
                        <div class="device-status">
                          <span class="status-badge" :class="device.status">
                            <i :class="device.status === 'testing' ? 'fas fa-play-circle testing-indicator' : 'fas fa-circle online-indicator'"></i>
                            {{ deviceStatusText[device.status] }}
                          </span>
                        </div>
                      </div>
                      <div class="device-card-content">
                        <div class="device-info">
                          <h3 class="device-name">{{ device.name }}</h3>
                          <p class="device-model">{{ device.url }}</p>
                          <div class="device-description" v-if="device.description" style="margin-top: 8px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;">
                            {{ device.description }}
                          </div>
                          <div class="device-meta">
                            <span class="meta-item" v-if="device.algorithmType || device.algorithm_type">
                              <i class="fas fa-microchip"></i>
                              {{ getAlgorithmTypeName(device.algorithmType || device.algorithm_type) }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-tags"></i>
                              {{ device.category }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-exchange-alt"></i>
                              {{ device.method }}
                            </span>
                            <span class="meta-item">
                              <i class="fas fa-clock"></i>
                              {{ device.responseTime }}ms
                            </span>
                          </div>
                        </div>
                        <div class="device-specs">
                          <div class="spec-item">
                            <label>API版本</label>
                            <span>{{ device.version }}</span>
                          </div>
                          <div class="spec-item">
                            <label>最后测试时间</label>
                            <span>{{ device.lastTested }}</span>
                          </div>
                          <div class="spec-item">
                            <label>成功率</label>
                            <span class="status-good">{{ device.successRate }}%</span>
                          </div>
                          <div class="spec-item">
                            <label>认证类型</label>
                            <span>{{ device.authType }}</span>
                          </div>
                        </div>
                      </div>
                      <div class="device-card-footer">
                        <div class="connection-controls">
                          <button class="btn btn-secondary" @click="openEditModal(device.id); $event.stopPropagation();">
                            <i class="fas fa-edit btn-icon"></i>
                            编辑
                          </button>
                          <button class="btn btn-danger" @click="deleteDevice(device.id); $event.stopPropagation();">
                            <i class="fas fa-trash btn-icon"></i>
                            删除
                          </button>
                          <button
                            class="btn btn-info"
                            @click="healthCheckDevice(device.id); $event.stopPropagation();"
                          >
                            <i class="fas fa-heartbeat btn-icon"></i>
                            健康检查
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #empty>
                  <div class="no-devices">
                    <i class="fas fa-info-circle"></i>
                    <p>无可用设备</p>
                  </div>
                </template>
              </InfiniteScrollList>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>




</template>

<script setup>
// 只导入主样式文件，所有组件样式已包含在main.css中
import '../assets/styles/main.css';
import { useDevice } from './DeviceLogic/Device';
import InfiniteScrollList from '../components/common/InfiniteScrollList.vue';
import AlgorithmTag from '../components/algorithm/AlgorithmTag.vue';
import AlgorithmFilter from '../components/algorithm/AlgorithmFilter.vue';
import BadgeFilter from '../components/common/BadgeFilter.vue';

// 使用组合式函数获取所有状态和函数
const {
  // 基本状态
  tabs,
  activeTab,
  dropdowns,
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
  allFilteredPlaybackDevices,
  allFilteredTestDevices,
  allFilteredAPIDevices,
  switchDeviceType,
  toggleDropdown,
  handleAddDevice,
  searchDevices,
  filterDevices,
  showDeviceDetails,
  getDelayClass,
  toggleDeviceSelection,
  resetAllStates,
  
  // 数据获取
  fetchAllDevices,
  
  // 编辑设备相关
  openEditModal,
  
  // 设备操作相关
  deleteDevice,
  testDevice,
  stopTest,
  healthCheckDevice,
  
  // 扫描设备相关
  scanDevices,
  
  // 批量操作相关
  batchEnableDevices,
  batchDisableDevices,
  batchDeleteDevices,
  batchHealthCheck,
  
  // 导入导出相关
  importDevices,
  exportDevices,

  // 分页大小
  playbackPageSize,
  testPageSize,
  apiPageSize
} = useDevice();

// ===== 徽章筛选选项（原下拉框硬编码迁移为常量）=====
const DEVICE_STATUS_OPTIONS = [
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
  { value: 'testing', label: '测试中' },
];

const PLAYBACK_TYPE_OPTIONS = [
  { value: '干声', label: '干声' },
  { value: '噪声', label: '噪声' },
];

function setStatusFilter(value) {
  statusFilter.value = String(value);
}

function setPlaybackTypeFilter(value) {
  playbackTypeFilter.value = String(value);
}

import { onMounted } from 'vue';

onMounted(async () => {
  // 页面加载时获取所有设备数据
  await fetchAllDevices();
});
</script>

<style scoped>
/* 筛选栏：原 device.css 为定宽下拉框设计，徽章筛选需占满可用宽度并允许换行 */
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

/* 算法徽章筛选行：与其它徽章组自然衔接，不再用虚线分隔 */
.algorithm-filter-row {
  width: 100%;
  padding-top: 0;
  margin-top: 0;
  border-top: none;
}

.no-devices {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  color: #64748b;
  background-color: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  width: 100%;
  margin: 0 auto;
}

.no-devices i {
  font-size: 32px;
  margin-bottom: 16px;
  color: #94a3b8;
}

.no-devices p {
  font-size: 16px;
  margin: 0;
}

.device-algorithms {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 0;
}

.algo-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: 500;
}
</style>