<template>
  <div class="spl-mapping-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-sliders-h"></i>
          声压级映射管理
        </h2>
        <p class="page-description">校准1-100数字增益与实际声压级(SPL)的映射关系</p>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openAddMappingModal">
          <i class="fas fa-plus btn-icon"></i>
          添加增益映射
        </button>
        <button class="btn btn-secondary" @click="importMappingData">
          <i class="fas fa-upload btn-icon"></i>
          导入映射数据
        </button>
      </div>
    </div>

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
            <div class="filter-select">
              <select class="form-input" v-model="calibrationFilter" @change="filterMappings()">
                <option value="all">所有状态</option>
                <option value="calibrated">已校准</option>
                <option value="uncalibrated">未校准</option>
              </select>
            </div>
            <div class="filter-select">
              <select class="form-input" v-model="deviceFilter" @change="filterByDevice()">
                <option value="all">所有设备</option>
                <option v-for="device in playbackDevices" :key="device.id" :value="device.id">
                  {{ device.name }}{{ device.model ? ` (${device.model})` : '' }}
                </option>
              </select>
            </div>
          </div>
        </div>
        <div class="card-body">
          <!-- 映射卡片网格 -->
          <div class="mapping-grid">
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
                  <p><strong>校准时间：</strong>{{ mapping.measurementDate || '未校准' }}</p>
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

    <!-- 全局模态框将在此处自动渲染 -->
  </div>
</template>

<script setup lang="ts">
import { useSplMapping } from './SPLMapping';
import { onMounted, watch } from 'vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';

const {
  searchTerm, 
  calibrationFilter, 
  deviceFilter,
  filteredMappings, 
  paginatedMappings, 
  stats, 
  playbackDevices,
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

onMounted(async () => {
  await Promise.all([
    initData(),
    fetchDevices()
  ]);
  initModalWatchers();
  initCharts();
});
</script>

<style>
@import '../../assets/styles/main.css';
</style>