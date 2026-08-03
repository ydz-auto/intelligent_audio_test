<template>
  <div class="algorithm-config-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-cogs"></i>
          算法配置管理
        </h2>
        <p class="page-description">管理测试算法定义、参数和映射关系</p>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="btn btn-primary" @click="handleCreate">
            <i class="fas fa-plus btn-icon"></i>
            新建算法
          </button>
        </div>
      </div>
    </div>

    <div class="page-content">
      <div class="card">
        <div class="card-header">
          <div class="tabs-nav">
            <button 
              v-for="tab in tabs" 
              :key="tab.key"
              class="tab-btn"
              :class="{ active: activeTab === tab.key }"
              @click="handleTabChange(tab.key)"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>
        <div class="card-body">
          <div v-if="activeTab === 'list'" class="tab-content">
            <div class="filter-bar">
              <div class="search-box">
                <i class="fas fa-search search-icon"></i>
                <input 
                  type="text" 
                  class="search-input" 
                  placeholder="搜索算法类型或名称"
                  v-model="searchKeyword"
                  @input="handleSearch"
                >
              </div>
              <div class="filter-select">
                <select class="form-input" v-model="groupFilter" @change="handleFilter">
                  <option value="">全部分组</option>
                  <option v-for="group in groups" :key="group.id" :value="group.id">
                    {{ group.name }}
                  </option>
                </select>
              </div>
              <div class="filter-select">
                <select class="form-input" v-model="statusFilter" @change="handleFilter">
                  <option value="">全部状态</option>
                  <option value="online">上线</option>
                  <option value="offline">下线</option>
                </select>
              </div>
            </div>

            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="core-col">算法类型</th>
                    <th class="core-col">名称</th>
                    <th class="secondary-col">分组</th>
                    <th class="secondary-col">状态</th>
                    <th class="secondary-col">参数数</th>
                    <th class="core-col action-col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="loading">
                    <td colspan="7" class="empty-row">
                      <i class="fas fa-spinner fa-spin"></i> 加载中...
                    </td>
                  </tr>
                  <tr v-else-if="filteredAlgorithms.length === 0">
                    <td colspan="7" class="empty-row">暂无数据</td>
                  </tr>
                  <tr v-else v-for="record in paginatedAlgorithms" :key="record.type">
                    <td class="core-col">{{ record.type }}</td>
                    <td class="core-col">{{ record.name }}</td>
                    <td class="secondary-col">
                      <span class="status-tag" v-if="record.group_name">{{ record.group_name }}</span>
                      <span v-else class="text-muted">-</span>
                    </td>
                    <td class="secondary-col">
                      <span class="status-badge" :class="record.status === 'online' ? 'active' : 'inactive'">
                        {{ record.status === 'online' ? '上线' : '下线' }}
                      </span>
                    </td>
                    <td class="secondary-col">{{ record.params?.length || 0 }}</td>
                    <td class="core-col action-col">
                      <div class="table-actions">
                        <button class="btn btn-text btn-sm" @click="handleEdit(record)">
                          <i class="fas fa-edit btn-icon"></i>编辑
                        </button>
                        <button class="btn btn-text btn-sm" @click="handleClone(record)">
                          <i class="fas fa-copy btn-icon"></i>复制
                        </button>
                        <button class="btn btn-text btn-sm btn-danger" @click="confirmDelete(record)">
                          <i class="fas fa-trash btn-icon"></i>删除
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="card-footer" v-if="filteredAlgorithms.length > pageSize">
              <PaginationComponent
                :current-page="currentPage"
                :page-size="pageSize"
                :total-items="filteredAlgorithms.length"
                @prev-page="handlePrevPage"
                @next-page="handleNextPage"
                @go-to-page="handleGoToPage"
                @page-size-change="handlePageSizeChange"
              />
            </div>
          </div>

          <div v-else-if="activeTab === 'detail'" class="tab-content">
            <div v-if="currentAlgorithm" class="algorithm-detail">
              <div class="detail-header">
                <button class="btn btn-text" @click="handleTabChange('list')">
                  <i class="fas fa-arrow-left btn-icon"></i>返回列表
                </button>
                <h3 class="detail-title">{{ currentAlgorithm.name }}</h3>
              </div>

              <div class="detail-section">
                <div class="section-title">基本信息</div>
                <div class="info-grid">
                  <div class="info-item">
                    <span class="info-label">算法类型</span>
                    <span class="info-value">{{ currentAlgorithm.type }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">显示名称</span>
                    <span class="info-value">{{ currentAlgorithm.name }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">分组</span>
                    <span class="info-value">
                      <span class="status-tag" v-if="currentAlgorithm.group_name">{{ currentAlgorithm.group_name }}</span>
                      <span v-else class="text-muted">-</span>
                    </span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">状态</span>
                    <span class="info-value">
                      <span class="status-badge" :class="currentAlgorithm.status === 'online' ? 'active' : 'inactive'">
                        {{ currentAlgorithm.status === 'online' ? '上线' : '下线' }}
                      </span>
                    </span>
                  </div>
                  <div class="info-item full-width">
                    <span class="info-label">描述</span>
                    <span class="info-value">{{ currentAlgorithm.description || '-' }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">排序</span>
                    <span class="info-value">{{ currentAlgorithm.display_order }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">参数数量</span>
                    <span class="info-value">{{ currentAlgorithm.params?.length || 0 }}</span>
                  </div>
                </div>
              </div>

              <div class="detail-section">
                <div class="section-title">参数定义</div>
                <div class="table-container">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th>参数代码</th>
                        <th>参数名称</th>
                        <th>类型</th>
                        <th>必填</th>
                        <th>组件</th>
                        <th>分组</th>
                        <th>默认值</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="!currentAlgorithm.params?.length">
                        <td colspan="7" class="empty-row">暂无参数</td>
                      </tr>
                      <tr v-else v-for="param in currentAlgorithm.params" :key="param.id">
                        <td>{{ param.param_code }}</td>
                        <td>{{ param.param_name }}</td>
                        <td><span class="status-tag">{{ param.param_type }}</span></td>
                        <td>
                          <span class="status-badge" :class="param.required ? 'active' : 'inactive'">
                            {{ param.required ? '是' : '否' }}
                          </span>
                        </td>
                        <td><span class="status-tag" style="background-color: var(--secondary-light); color: var(--secondary-color);">{{ param.component }}</span></td>
                        <td>{{ getGroupName(param.ui_group) }}</td>
                        <td>{{ param.default_value || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="detail-section">
                <div class="section-title">参数映射</div>
                <div class="mapping-tabs">
                  <button 
                    v-for="mappingTab in mappingTabs" 
                    :key="mappingTab.key"
                    class="tab-btn"
                    :class="{ active: activeMappingTab === mappingTab.key }"
                    @click="activeMappingTab = mappingTab.key"
                  >
                    {{ mappingTab.label }}
                  </button>
                </div>
                <div class="table-container">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th>源参数</th>
                        <th>目标参数</th>
                        <th>转换类型</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="!currentAlgorithm.mappings?.[activeMappingTab]?.length">
                        <td colspan="3" class="empty-row">暂无映射</td>
                      </tr>
                      <tr v-else v-for="(mapping, index) in currentAlgorithm.mappings[activeMappingTab]" :key="index">
                        <td>{{ mapping.source_param }}</td>
                        <td>{{ mapping.target_key }}</td>
                        <td>{{ mapping.transform_type }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <i class="fas fa-info-circle"></i>
              <p>请从列表中选择一个算法查看详情</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AlgorithmConfigModal
      v-model:visible="modalVisible"
      :mode="modalMode"
      :edit-data="currentAlgorithm"
      @select="handleSelect"
      @success="loadAlgorithms"
    />
  </div>
</template>

<script setup lang="ts">
import AlgorithmConfigModal from '../../components/algorithm/AlgorithmConfigModal.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import { useAlgorithmConfigPage } from './AlgorithmConfigPage'

const {
  tabs,
  mappingTabs,
  activeTab,
  activeMappingTab,
  loading,
  groups,
  currentAlgorithm,
  searchKeyword,
  groupFilter,
  statusFilter,
  modalVisible,
  modalMode,
  currentPage,
  pageSize,
  filteredAlgorithms,
  paginatedAlgorithms,
  getGroupName,
  loadAlgorithms,
  handleCreate,
  handleEdit,
  handleClone,
  confirmDelete,
  handleSelect,
  handleSearch,
  handleFilter,
  handleTabChange,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange
} = useAlgorithmConfigPage()
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
@import './AlgorithmConfigPage.css';
</style>
