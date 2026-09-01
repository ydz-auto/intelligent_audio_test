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
import { TaskStatus, ReportStatus } from '@/shared/types/enums';

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
      const statusMap = { 'pending': '排队中', 'in-progress': '执行中', 'completed': '已完成', 'failed': '执行失败', 'draft': '草稿', 'published': '已发布' };
      return statusMap[status] || status;
    },
    getProgressColor(percentage) {
      if (percentage >= 90) return '#52C41A';
      if (percentage >= 70) return '#1677FF';
      if (percentage >= 50) return '#FAAD14';
      return '#F5222D';
    }
  }
};
</script>

<style scoped>
.comparison-table-container {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 24px;
  margin-bottom: 24px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
  cursor: pointer;
  user-select: none;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-content i {
  font-size: 14px;
  color: #999;
  transition: all 0.3s ease;
}

.header-content i:hover {
  color: #1677FF;
}

.table-content {
  overflow: hidden;
  transition: all 0.3s ease;
}

.table-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin: 0;
}

.table-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.comparison-table th {
  background: #fafafa;
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: #333;
  border-bottom: 2px solid #e2e8f0;
  white-space: nowrap;
}

.th-content {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.th-content i {
  color: #999;
  transition: color 0.3s ease;
}

.th-content i:hover {
  color: #1677FF;
}

.comparison-table td {
  padding: 12px 16px;
  border-bottom: 1px solid #e2e8f0;
  color: #666;
  vertical-align: middle;
}

.table-row {
  transition: all 0.3s ease;
}

.table-row:hover {
  background: #f0f5ff;
}

.table-row-highlight {
  background: #e6f7ff;
}

.status-pending {
  background: #fff7e6;
  color: #fa8c16;
}

.status-in-progress {
  background: #e6f7ff;
  color: #1890ff;
}

.status-completed {
  background: #f6ffed;
  color: #52c41a;
}

.status-failed {
  background: #fff1f0;
  color: #ff4d4f;
}

.status-draft {
  background: #f0f0f0;
  color: #666;
}

.status-published {
  background: #f6ffed;
  color: #52c41a;
}

.percentage-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.percentage-value {
  font-weight: 600;
  color: #333;
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--secondary-color);
  border-radius: var(--border-radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--border-radius-full);
  transition: width 0.3s ease;
  position: relative;
  overflow: hidden;
}

.number-cell {
  font-weight: 600;
  color: #333;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: linear-gradient(90deg, #FF6A00, #1677FF);
  color: white;
}

.btn-primary:hover {
  opacity: 0.9;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.btn-secondary {
  background: white;
  color: #666;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover {
  background: #f5f5f5;
  border-color: #1677FF;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
