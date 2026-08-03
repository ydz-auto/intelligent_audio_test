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
                  <div class="filter-select">
                    <select class="form-input" v-model="statusFilter" @change="filterDevices" id="statusFilter">
                      <option value="all">所有状态</option>
                      <option value="online">在线</option>
                      <option value="offline">离线</option>
                      <option value="testing">测试中</option>
                    </select>
                  </div>
                  <div class="filter-select">
                    <select class="form-input" v-model="playbackTypeFilter" @change="filterDevices" id="playbackTypeFilter">
                      <option value="all">所有类型</option>
                      <option value="干声">干声</option>
                      <option value="噪声">噪声</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- 设备卡片网格 -->
              <div class="devices-grid">
                <!-- 无设备时显示 -->
                <div v-if="filteredPlaybackDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                
                <!-- 设备卡片 -->
                <div 
                  v-else
                  v-for="device in filteredPlaybackDevices" 
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
              
              <!-- 分页控件 -->
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
                  <div class="filter-select">
                    <select class="form-input" v-model="statusFilter" @change="filterDevices" id="testStatusFilter">
                      <option value="all">所有状态</option>
                      <option value="online">在线</option>
                      <option value="offline">离线</option>
                      <option value="testing">测试中</option>
                    </select>
                  </div>
                  <div class="filter-select">
                    <select class="form-input" v-model="algorithmFilter" @change="filterDevices" id="algorithmFilter">
                      <option value="all">支持算法: 全部</option>
                      <option v-for="algo in algorithmTypeOptions" :key="algo.value" :value="algo.value">
                        {{ algo.label }}
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- 测试设备卡片网格 -->
              <div class="devices-grid">
                <!-- 无设备时显示 -->
                <div v-if="filteredTestDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                
                <!-- 测试设备卡片 -->
                <div 
                  v-else
                  v-for="device in filteredTestDevices" 
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
              
              <!-- 分页控件 -->
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
                  <div class="filter-select">
                    <select class="form-input" v-model="statusFilter" @change="filterDevices" id="apiStatusFilter">
                      <option value="all">所有状态</option>
                      <option value="online">在线</option>
                      <option value="offline">离线</option>
                      <option value="testing">测试中</option>
                    </select>
                  </div>
                  <div class="filter-select">
                    <select class="form-input" v-model="algorithmTypeFilter" @change="filterDevices" id="apiAlgorithmTypeFilter">
                      <option value="all">所有算法类型</option>
                      <option v-for="algo in algorithmTypeOptions" :key="algo.value" :value="algo.value">
                        {{ algo.label }}
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div class="card-body">
              <!-- API设备卡片网格 -->
              <div class="devices-grid">
                <!-- 无设备时显示 -->
                <div v-if="filteredAPIDevices.length === 0" class="no-devices">
                  <i class="fas fa-info-circle"></i>
                  <p>无可用设备</p>
                </div>
                
                <!-- API设备卡片 -->
                <div 
                  v-else
                  v-for="device in filteredAPIDevices" 
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
              
              <!-- 分页控件 -->
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
  </div>




</template>

<script setup>
// 只导入主样式文件，所有组件样式已包含在main.css中
import '../../assets/styles/main.css';
import { useDevice } from './Device';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import AlgorithmTag from '../../components/algorithm/AlgorithmTag.vue';

// 使用组合式函数获取所有状态和函数（onMounted 已在 useDevice 内部处理）
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

  // 播放设备分页
  playbackCurrentPage,
  playbackPageSize,
  playbackTotalItems,
  playbackTotalPages,
  handlePlaybackPageChange,
  handlePlaybackPageSizeChange,
  handlePlaybackPrevPage,
  handlePlaybackNextPage,

  // 测试设备分页
  testCurrentPage,
  testPageSize,
  testTotalItems,
  testTotalPages,
  handleTestPageChange,
  handleTestPageSizeChange,
  handleTestPrevPage,
  handleTestNextPage,

  // API设备分页
  apiCurrentPage,
  apiPageSize,
  apiTotalItems,
  apiTotalPages,
  handleAPIPageChange,
  handleAPIPageSizeChange,
  handleAPIPrevPage,
  handleAPINextPage
} = useDevice();
</script>

<style scoped>
@import './Device.css';
</style>