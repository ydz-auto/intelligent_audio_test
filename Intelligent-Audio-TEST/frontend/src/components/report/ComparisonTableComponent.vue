<template>
  <div class="comparison-table-container">
    <div class="table-header">
      <div
        class="header-content"
        role="button"
        tabindex="0"
        @click="toggleCollapse"
        @keydown.enter.prevent="toggleCollapse"
        @keydown.space.prevent="toggleCollapse"
      >
        <h3 class="table-title">{{ title }}</h3>
        <i class="fas" :class="isCollapsed ? 'fa-chevron-down' : 'fa-chevron-up'"></i>
      </div>
      <div class="table-actions" v-if="showActions" @click.stop>
        <div class="search-box" v-if="showSearch" @click.stop>
          <i class="fas fa-search"></i>
          <input 
            type="text" 
            placeholder="搜索..." 
            v-model="searchQuery"
            @input="handleSearch"
            @click.stop
            debounce="300"
          />
        </div>
        <button class="btn btn-primary" @click.stop="$emit('export')">
          <i class="fas fa-download"></i> 导出
        </button>
      </div>
    </div>
    
    <div class="table-content" v-if="!isCollapsed">
      <div class="table-wrapper">
        <table class="comparison-table">
          <thead>
            <tr>
              <th v-for="(column, index) in columns" :key="index" :class="column.className">
                <div class="th-content">
                  <span>{{ column.label }}</span>
                  <i 
                    v-if="column.sortable" 
                    class="fas" 
                    :class="getSortIconClass(column.key)"
                    @click.stop="handleSort(column.key)"
                  ></i>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="(row, rowIndex) in filteredData" 
              :key="rowIndex"
              class="table-row"
              :class="{ 'table-row-highlight': row.highlight }"
            >
              <td v-for="(column, colIndex) in columns" :key="colIndex" :class="column.className">
                <div class="td-content">
                  <!-- 支持不同类型的内容渲染 -->
                  <template v-if="column.type === 'status'">
                    <span class="status-badge" :class="`status-${row[column.key]}`">{{ getStatusLabel(row[column.key]) }}</span>
                  </template>
                  <template v-else-if="column.type === 'percentage'">
                    <div class="percentage-cell">
                      <span class="percentage-value">{{ row[column.key] }}%</span>
                      <div class="progress-bar" style="background-color: var(--secondary-color);">
                        <div class="progress-fill" :style="{ width: `${row[column.key]}%`, backgroundColor: getProgressColor(row[column.key]) }"></div>
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.type === 'number'">
                    <span class="number-cell">{{ row[column.key] }}</span>
                  </template>
                  <template v-else-if="column.type === 'icon'">
                    <i class="fas" :class="row[column.key]"></i>
                  </template>
                  <template v-else>
                    {{ row[column.key] }}
                  </template>
                </div>
              </td>
            </tr>
            <tr v-if="filteredData.length === 0" class="empty-row">
              <td :colspan="columns.length" class="empty-cell">
                <div class="empty-state">
                  <i class="fas fa-inbox"></i>
                  <p>暂无数据</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 分页控件 -->
      <div class="pagination" v-if="showPagination && totalItems > pageSize">
        <div class="pagination-info">
          第 {{ currentPage }} 页，共 {{ totalPages }} 页，总计 {{ totalItems }} 条数据
        </div>
        <div class="pagination-controls">
          <button 
            class="btn btn-secondary" 
            @click="goToPage(1)"
            :disabled="currentPage === 1"
          >
            <i class="fas fa-angle-double-left"></i> 首页
          </button>
          <button 
            class="btn btn-secondary" 
            @click="goToPage(currentPage - 1)"
            :disabled="currentPage === 1"
          >
            <i class="fas fa-angle-left"></i> 上一页
          </button>
          
          <span 
            v-for="page in visiblePages" 
            :key="page"
            class="pagination-page"
            :class="{ 'active': page === currentPage }"
            @click="goToPage(page)"
          >
            {{ page }}
          </span>
          
          <button 
            class="btn btn-secondary" 
            @click="goToPage(currentPage + 1)"
            :disabled="currentPage === totalPages"
          >
            下一页 <i class="fas fa-angle-right"></i>
          </button>
          <button 
            class="btn btn-secondary" 
            @click="goToPage(totalPages)"
            :disabled="currentPage === totalPages"
          >
            末页 <i class="fas fa-angle-double-right"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { TaskStatus, ReportStatus, ExecutionStatus } from '@/domain/enums';

export default {
  name: 'ComparisonTableComponent',
  props: {
    title: {
      type: String, default: '对比表格'
    },
    columns: {
      type: Array, required: true, default: () => []
    },
    data: {
      type: Array, required: true, default: () => []
    },
    showActions: {
      type: Boolean, default: true
    },
    showSearch: {
      type: Boolean, default: true
    },
    showPagination: {
      type: Boolean, default: true
    },
    pageSize: {
      type: Number, default: 10
    },
    collapsible: {
      type: Boolean, default: true
    },
    defaultCollapsed: {
      type: Boolean, default: false
    }
  },
  emits: ['export', 'sort', 'search'],
  inject: {
    isExporting: { default: false }
  },
  data() {
    return {
      searchQuery: '',
      currentPage: 1,
      sortKey: null,
      sortOrder: 'asc',
      isCollapsed: this.defaultCollapsed
    };
  },
  watch: {
    defaultCollapsed(newVal) {
      this.isCollapsed = newVal;
    },
    isExporting(newVal) {
      if (newVal) this.isCollapsed = false;
    }
  },
  computed: {
    totalItems() {
      return this.data.length;
    },
    totalPages() {
      return Math.ceil(this.totalItems / this.pageSize);
    },
    visiblePages() {
      const pages = [];
      const maxVisiblePages = 5;
      const startPage = Math.max(1, this.currentPage - Math.floor(maxVisiblePages / 2));
      const endPage = Math.min(this.totalPages, startPage + maxVisiblePages - 1);
      
      for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
      }
      
      return pages;
    },
    filteredData() {
      // 确保this.data是数组，如果不是，使用空数组作为默认值
      const dataArray = Array.isArray(this.data) ? this.data : [];
      let result = [...dataArray];
      
      // 搜索过滤
      if (this.searchQuery) {
        const query = this.searchQuery.toLowerCase();
        result = result.filter(row => {
          return this.columns.some(column => {
            const value = row[column.key];
            return String(value).toLowerCase().includes(query);
          });
        });
      }
      
      // 排序
      if (this.sortKey) {
        result.sort((a, b) => {
          const aVal = a[this.sortKey];
          const bVal = b[this.sortKey];
          
          if (aVal < bVal) return this.sortOrder === 'asc' ? -1 : 1;
          if (aVal > bVal) return this.sortOrder === 'asc' ? 1 : -1;
          return 0;
        });
      }
      
      // 分页（导出模式不分页，显示全部数据）
      if (this.showPagination && !this.isExporting) {
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = startIndex + this.pageSize;
        result = result.slice(startIndex, endIndex);
      }
      
      return result;
    }
  },
  methods: {
    toggleCollapse() {
      if (this.collapsible) {
        this.isCollapsed = !this.isCollapsed;
      }
    },
    getSortIconClass(columnKey) {
      if (this.sortKey !== columnKey) {
        return 'fa-sort';
      }
      return this.sortOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
    },
    handleSort(columnKey) {
      if (this.sortKey === columnKey) {
        // 切换排序方向
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        // 设置新的排序字段
        this.sortKey = columnKey;
        this.sortOrder = 'asc';
      }
      this.$emit('sort', { key: this.sortKey, order: this.sortOrder });
    },
    handleSearch() {
      this.currentPage = 1;
      this.$emit('search', this.searchQuery);
    },
    goToPage(page) {
      if (page >= 1 && page <= this.totalPages) {
        this.currentPage = page;
      }
    },
    getStatusLabel(status) {
      const statusMap = { [ExecutionStatus.PENDING]: '排队中', 'in-progress': '执行中', [ExecutionStatus.COMPLETED]: '已完成', [ExecutionStatus.FAILED]: '执行失败', [ReportStatus.DRAFT]: '草稿', [ReportStatus.PUBLISHED]: '已发布' };
      return statusMap[status] || status;
    },
    getProgressColor(percentage) {
      if (percentage >= 90) return 'var(--success)';
      if (percentage >= 70) return 'var(--secondary)';
      if (percentage >= 50) return 'var(--warning)';
      return 'var(--destructive)';
    }
  }
};
</script>

<style scoped>

#useCasePagination .pagination-controls{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}




.comparison-table-container{
  background: var(--color-white);
  border-radius: 12px;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-black) 8%, transparent);
  padding: 24px;
  margin-bottom: 24px;
}

.table-header{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
  cursor: pointer;
  user-select: none;
}

.header-content{
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-content i{
  font-size: 14px;
  color: var(--color-gray-400);
  transition: all 0.3s ease;
}

.header-content i:hover{
  color: var(--secondary);
}

.table-content{
  overflow: hidden;
  transition: all 0.3s ease;
}

.table-title{
  font-size: 18px;
  font-weight: bold;
  color: var(--foreground);
  margin: 0;
}

.table-actions{
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.table-wrapper{
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid var(--color-slate-200);
}

.comparison-table{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.comparison-table th{
  background: var(--color-neutral-50);
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: var(--foreground);
  border-bottom: 2px solid var(--color-slate-200);
  white-space: nowrap;
}

.th-content{
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.th-content i{
  color: var(--color-gray-400);
  transition: color 0.3s ease;
}

.th-content i:hover{
  color: var(--secondary);
}

.comparison-table td{
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-slate-200);
  color: var(--color-gray-500);
  vertical-align: middle;
}

.table-row{
  transition: all 0.3s ease;
}

.table-row:hover{
  background: var(--secondary-light);
}

.table-row-highlight{
  background: var(--secondary-light);
}

.status-pending{
  background: var(--warning-light);
  color: var(--warning);
}

.status-in-progress{
  background: var(--secondary-light);
  color: var(--secondary);
}

.status-completed{
  background: var(--success-light);
  color: var(--success);
}

.status-failed{
  background: var(--destructive-light);
  color: var(--destructive);
}

.status-draft{
  background: var(--gray-light);
  color: var(--color-gray-500);
}

.status-published{
  background: var(--success-light);
  color: var(--success);
}

.percentage-cell{
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.percentage-value{
  font-weight: 600;
  color: var(--foreground);
}

.progress-bar{
  width: 100%;
  height: 6px;
  background: var(--secondary-color);
  border-radius: var(--border-radius-full);
  overflow: hidden;
}

.progress-fill{
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--border-radius-full);
  transition: width 0.3s ease;
  position: relative;
  overflow: hidden;
}

.number-cell{
  font-weight: 600;
  color: var(--foreground);
}

.pagination-controls{
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary{
  background: linear-gradient(90deg, var(--primary), var(--secondary));
  color: white;
}

.btn-primary:hover{
  opacity: 0.9;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 15%, transparent);
}

.btn-secondary{
  background: white;
  color: var(--color-gray-500);
  border: 1px solid var(--border);
}

.btn-secondary:hover{
  background: var(--muted);
  border-color: var(--secondary);
}

.btn:disabled{
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
