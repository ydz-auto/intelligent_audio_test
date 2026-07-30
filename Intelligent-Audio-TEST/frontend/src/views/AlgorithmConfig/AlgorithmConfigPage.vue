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
import { ref, computed, onMounted } from 'vue'
import AlgorithmConfigModal from '../../components/algorithm/AlgorithmConfigModal.vue'
import PaginationComponent from '../../components/common/data/PaginationComponent.vue'
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal'

interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number
  group_name?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  params?: any[]
  mappings?: {
    device: any[]
    api: any[]
    evaluation: any[]
  }
}

interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
}

const modalControl = useModalControl()

const tabs = [
  { key: 'list', label: '算法列表' },
]

const mappingTabs = [
  { key: 'device', label: '设备参数' },
  { key: 'api', label: 'API参数' },
  { key: 'evaluation', label: '评估参数' }
]

const activeTab = ref('list')
const activeMappingTab = ref('device')
const loading = ref(false)
const algorithms = ref<AlgorithmRecord[]>([])
const groups = ref<AlgorithmGroup[]>([])
const currentAlgorithm = ref<AlgorithmRecord | null>(null)
const searchKeyword = ref('')
const groupFilter = ref<number | string>('')
const statusFilter = ref<string>('')

const modalVisible = ref(false)
const modalMode = ref<'list' | 'create' | 'edit'>('list')

const currentPage = ref(1)
const pageSize = ref(10)

const filteredAlgorithms = computed(() => {
  let result = algorithms.value

  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(a =>
      a.type.toLowerCase().includes(keyword) ||
      a.name.toLowerCase().includes(keyword)
    )
  }

  if (groupFilter.value !== '') {
    result = result.filter(a => a.group_id === Number(groupFilter.value))
  }

  if (statusFilter.value !== '') {
    result = result.filter(a => a.status === statusFilter.value)
  }

  return result
})

const paginatedAlgorithms = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAlgorithms.value.slice(start, end)
})

function getGroupName(group: string | undefined): string {
  const names: Record<string, string> = {
    basic: '基本配置',
    model: '模型配置',
    advanced: '高级选项'
  }
  return names[group || ''] || group || '-'
}

async function loadAlgorithms() {
  loading.value = true
  try {
    const response = await fetch('/api/v1/algorithm/definitions')
    const result = await response.json()
    if (result.success) {
      algorithms.value = (result.data.data || []).map(normalizeAlgorithmFields)
    }
  } catch (error) {
    console.error('加载算法列表失败:', error)
  } finally {
    loading.value = false
  }
}

function normalizeAlgorithmFields(algo: any) {
  return {
    ...algo,
    group_id: algo.groupId ?? algo.group_id,
    group_name: algo.groupName ?? algo.group_name,
    display_order: algo.displayOrder ?? algo.display_order,
    device_params: algo.deviceParams ?? algo.device_params ?? [],
    api_params: algo.apiParams ?? algo.api_params ?? [],
    case_params: algo.caseParams ?? algo.case_params ?? [],
    params: algo.params ?? [],
    mappings: algo.mappings ?? { device: [], api: [], evaluation: [] },
    associated_dimensions: algo.associatedDimensions ?? algo.associated_dimensions ?? [],
    reference_params: algo.referenceParams ?? algo.reference_params ?? []
  }
}

async function loadGroups() {
  try {
    const response = await fetch('/api/v1/algorithm/groups')
    const result = await response.json()
    if (result.success) {
      groups.value = result.data?.data || []
    }
  } catch (error) {
    console.error('加载分组列表失败:', error)
  }
}

function handleCreate() {
  modalMode.value = 'create'
  currentAlgorithm.value = null
  modalVisible.value = true
}

function handleEdit(record: AlgorithmRecord) {
  modalMode.value = 'edit'
  currentAlgorithm.value = JSON.parse(JSON.stringify(record))
  loadAlgorithmDetail(record.type).then(() => {
    modalVisible.value = true
  })
}

async function loadAlgorithmDetail(algoType: string) {
  try {
    const response = await fetch(`/api/v1/algorithm/definitions/${algoType}`)
    const result = await response.json()
    if (result.success && result.data) {
      currentAlgorithm.value = normalizeAlgorithmFields(result.data)
    }
  } catch (error) {
    console.error('加载算法详情失败:', error)
  }
}

function handleView(record: AlgorithmRecord) {
  currentAlgorithm.value = record
  activeTab.value = 'detail'
}

async function handleClone(record: AlgorithmRecord) {
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认复制',
    content: `确定要复制算法「${record.name}」吗？`,
    confirmText: '复制',
    cancelText: '取消'
  })
  
  if (!confirmed) return
  
  try {
    const detailResponse = await fetch(`/api/v1/algorithm/definitions/${record.type}`)
    const detailResult = await detailResponse.json()
    let cloneData: any = { ...record }
    if (detailResult.success && detailResult.data) {
      cloneData = normalizeAlgorithmFields(detailResult.data)
    }
    
    const response = await fetch('/api/v1/algorithm/definitions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...cloneData,
        type: `${record.type}_copy`,
        name: `${record.name} (副本)`
      })
    })
    const result = await response.json()
    if (result.success) {
      loadAlgorithms()
    } else {
      console.error('复制失败:', result.message)
    }
  } catch (error) {
    console.error('复制失败:', error)
  }
}

async function confirmDelete(record: AlgorithmRecord) {
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认删除',
    content: `确定要删除算法「${record.name}」吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    danger: true
  })
  
  if (confirmed) {
    await executeDelete(record)
  }
}

async function executeDelete(record: AlgorithmRecord) {
  if (!record) return
  
  try {
    const response = await fetch(`/api/v1/algorithm/definitions/${record.type}`, {
      method: 'DELETE'
    })
    const result = await response.json()
    if (result.success) {
      loadAlgorithms()
      if (activeTab.value === 'detail') {
        activeTab.value = 'list'
      }
    } else {
      console.error('删除失败:', result.message)
    }
  } catch (error) {
    console.error('删除失败:', error)
  }
}

function handleSelect(data: AlgorithmRecord) {
  console.log('Selected algorithm:', data)
}

function handleSearch() {
  currentPage.value = 1
}

function handleFilter() {
  currentPage.value = 1
}

function handleTabChange(tabKey: string) {
  activeTab.value = tabKey
  if (tabKey === 'list') {
    currentAlgorithm.value = null
  }
}

function handlePrevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

function handleNextPage() {
  const totalPages = Math.ceil(filteredAlgorithms.value.length / pageSize.value)
  if (currentPage.value < totalPages) {
    currentPage.value++
  }
}

function handleGoToPage(page: number) {
  currentPage.value = page
}

function handlePageSizeChange(newSize: number) {
  pageSize.value = newSize
  currentPage.value = 1
}

onMounted(() => {
  loadAlgorithms()
  loadGroups()
})
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
.algorithm-config-page {
  padding: var(--spacing-lg);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-bold);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--primary-color);
}

.page-description {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.page-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.tabs-nav {
  display: flex;
  gap: var(--spacing-xs);
}

.tab-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  cursor: pointer;
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
}

.tab-btn:hover {
  background: var(--primary-light);
  color: var(--primary-color);
}

.tab-btn.active {
  background: var(--primary-color);
  color: var(--white-color);
}

.tab-content {
  padding: var(--spacing-md) 0;
}

.filter-bar {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.filter-bar .search-box {
  width: 280px;
}

.filter-bar .filter-select {
  width: 180px;
}

.table-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.algorithm-detail {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.detail-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.info-item.full-width {
  grid-column: span 2;
}

.info-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.info-value {
  font-size: var(--font-size-md);
  color: var(--text-primary);
}

.mapping-tabs {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xxl);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: var(--font-size-xxxl);
  margin-bottom: var(--spacing-md);
  color: var(--text-light);
}

.empty-state p {
  margin: 0;
  font-size: var(--font-size-md);
}

.btn-danger {
  color: var(--danger-color);
}

.btn-danger:hover {
  background: var(--danger-light);
  color: var(--danger-color);
}

.text-muted {
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  
  .info-item.full-width {
    grid-column: span 1;
  }
  
  .filter-bar {
    flex-direction: column;
  }
  
  .filter-bar .search-box,
  .filter-bar .filter-select {
    width: 100%;
  }
}
</style>
