<template>
  <div class="filter-component-container">
    <div class="filter-header" v-if="showHeader">
      <h3 class="filter-title">{{ title }}</h3>
      <div class="filter-actions">
        <button class="btn btn-secondary" @click="resetFilters">
          <i class="fas fa-times"></i> 重置筛选
        </button>
        <button class="btn btn-primary" @click="applyFilters">
          <i class="fas fa-check"></i> 应用筛选
        </button>
      </div>
    </div>
    
    <div class="filter-content">
      <!-- 条件筛选 -->
      <div class="filter-group" v-for="group in filterGroups" :key="group.key">
        <h4 class="filter-group-title">{{ group.label }}</h4>
        
        <!-- 文本输入筛选 -->
        <div class="filter-item" v-if="group.type === 'text'">
          <input 
            type="text" 
            :placeholder="group.placeholder || '请输入...'"
            v-model="filterValues[group.key]"
            @input="handleFilterChange"
            class="filter-input"
          />
        </div>
        
        <!-- 下拉选择筛选 -->
        <div class="filter-item" v-else-if="group.type === 'select'">
          <select 
            v-model="filterValues[group.key]"
            @change="handleFilterChange"
            class="filter-select"
          >
            <option value="">全部</option>
            <option 
              v-for="option in group.options" 
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </div>
        
        <!-- 单选按钮组筛选 -->
        <div class="filter-item" v-else-if="group.type === 'radio'">
          <div class="radio-group">
            <label 
              v-for="option in group.options" 
              :key="option.value"
              class="radio-label"
            >
              <input 
                type="radio" 
                :name="group.key"
                :value="option.value"
                v-model="filterValues[group.key]"
                @change="handleFilterChange"
              >
              <span class="radio-text">{{ option.label }}</span>
            </label>
          </div>
        </div>
        
        <!-- 多选框组筛选 -->
        <div class="filter-item" v-else-if="group.type === 'checkbox'">
          <div class="checkbox-group">
            <label 
              v-for="option in group.options" 
              :key="option.value"
              class="checkbox-label"
            >
              <input 
                type="checkbox" 
                :value="option.value"
                v-model="filterValues[group.key]"
                @change="handleFilterChange"
              >
              <span class="checkbox-text">{{ option.label }}</span>
            </label>
          </div>
        </div>
        
        <!-- 日期范围筛选 -->
        <div class="filter-item" v-else-if="group.type === 'dateRange'">
          <div class="date-range-container">
            <div class="date-input-group">
              <label :for="group.key + '-start-date'">开始日期:</label>
              <input 
                type="date" 
                :id="group.key + '-start-date'"
                v-model="filterValues[group.key].start"
                @change="handleFilterChange"
                class="filter-date-input"
              />
            </div>
            <span class="date-separator">至</span>
            <div class="date-input-group">
              <label :for="group.key + '-end-date'">结束日期:</label>
              <input 
                type="date" 
                :id="group.key + '-end-date'"
                v-model="filterValues[group.key].end"
                @change="handleFilterChange"
                class="filter-date-input"
              />
            </div>
          </div>
        </div>
        
        <!-- 滑块筛选 -->
        <div class="filter-item" v-else-if="group.type === 'range'">
          <div class="range-container">
            <div class="range-inputs">
              <div class="range-input-group">
                <label for="min-range">最小值:</label>
                <input 
                  type="number" 
                  id="min-range"
                  :min="group.min"
                  :max="group.max"
                  :step="group.step || 1"
                  v-model="filterValues[group.key].min"
                  @input="handleFilterChange"
                  class="filter-number-input"
                />
              </div>
              <span class="range-separator">-</span>
              <div class="range-input-group">
                <label for="max-range">最大值:</label>
                <input 
                  type="number" 
                  id="max-range"
                  :min="group.min"
                  :max="group.max"
                  :step="group.step || 1"
                  v-model="filterValues[group.key].max"
                  @input="handleFilterChange"
                  class="filter-number-input"
                />
              </div>
            </div>
            <div class="range-slider-container">
              <input 
                type="range" 
                :min="group.min"
                :max="group.max"
                :step="group.step || 1"
                v-model="filterValues[group.key].min"
                @input="handleFilterChange"
                class="range-slider"
              />
              <input 
                type="range" 
                :min="group.min"
                :max="group.max"
                :step="group.step || 1"
                v-model="filterValues[group.key].max"
                @input="handleFilterChange"
                class="range-slider"
              />
            </div>
          </div>
        </div>
        
        <!-- 标签云筛选 -->
        <div class="filter-item" v-else-if="group.type === 'tagCloud'">
          <div class="tag-cloud-container">
            <span 
              v-for="tag in group.options" 
              :key="tag.value"
              class="tag-item"
              :class="{ 'tag-selected': filterValues[group.key].includes(tag.value) }"
              @click="toggleTag(group.key, tag.value)"
            >
              <span class="tag-name">{{ tag.label }}</span>
              <span class="tag-count">({{ tag.count }})</span>
            </span>
          </div>
        </div>
      </div>
    </div>
    
    <div class="filter-footer" v-if="showFooter">
      <div class="active-filters" v-if="activeFilterCount > 0">
        <h4 class="active-filters-title">已选条件 ({{ activeFilterCount }})</h4>
        <div class="active-filters-list">
          <span 
            v-for="(value, key) in getActiveFilters()" 
            :key="key"
            class="active-filter-item"
          >
            <span class="filter-label">{{ getFilterLabel(key) }}:</span>
            <span class="filter-value">{{ getFilterDisplayValue(key, value) }}</span>
            <button class="filter-remove-btn" @click="removeFilter(key)">
              <i class="fas fa-times"></i>
            </button>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'FilterComponent',
  props: {
    title: {
      type: String, default: '筛选条件'
    },
    filterGroups: {
      type: Array, required: true, default: () => []
    },
    showHeader: {
      type: Boolean, default: true
    },
    showFooter: {
      type: Boolean, default: true
    }
  },
  emits: ['filterChange', 'apply', 'reset'],
  data() {
    // 初始化筛选值
    const initialFilterValues = {};
    this.filterGroups.forEach(group => {
      if (group.type === 'checkbox' || group.type === 'tagCloud') {
        initialFilterValues[group.key] = [];
      } else if (group.type === 'dateRange' || group.type === 'range') {
        initialFilterValues[group.key] = {
          min: group.initialMin || (group.type === 'dateRange' ? '' : group.min), 
          max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
        };
      } else {
        initialFilterValues[group.key] = group.initialValue || '';
      }
    });
    
    return {
      filterValues: initialFilterValues
    };
  },
  computed: {
    // 计算已选筛选条件数量
    activeFilterCount() {
      return Object.keys(this.getActiveFilters()).length;
    }
  },
  methods: {
    // 处理筛选值变化
    handleFilterChange() {
      this.$emit('filterChange', this.filterValues);
    },
    
    // 应用筛选
    applyFilters() {
      this.$emit('apply', this.filterValues);
    },
    
    // 重置筛选
    resetFilters() {
      // 重置筛选值
      this.filterGroups.forEach(group => {
        if (group.type === 'checkbox' || group.type === 'tagCloud') {
          this.filterValues[group.key] = [];
        } else if (group.type === 'dateRange' || group.type === 'range') {
          this.filterValues[group.key] = {
            min: group.initialMin || (group.type === 'dateRange' ? '' : group.min), 
            max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
          };
        } else {
          this.filterValues[group.key] = group.initialValue || '';
        }
      });
      
      this.$emit('reset');
      this.$emit('filterChange', this.filterValues);
    },
    
    // 切换标签选择
    toggleTag(groupKey, tagValue) {
      const index = this.filterValues[groupKey].indexOf(tagValue);
      if (index > -1) {
        this.filterValues[groupKey].splice(index, 1);
      } else {
        this.filterValues[groupKey].push(tagValue);
      }
      this.handleFilterChange();
    },
    
    // 移除单个筛选条件
    removeFilter(key) {
      const group = this.filterGroups.find(g => g.key === key);
      if (group) {
        if (group.type === 'checkbox' || group.type === 'tagCloud') {
          this.filterValues[key] = [];
        } else if (group.type === 'dateRange' || group.type === 'range') {
          this.filterValues[key] = {
            min: group.initialMin || (group.type === 'dateRange' ? '' : group.min), 
            max: group.initialMax || (group.type === 'dateRange' ? '' : group.max)
          };
        } else {
          this.filterValues[key] = group.initialValue || '';
        }
        this.handleFilterChange();
      }
    },
    
    // 获取已选筛选条件
    getActiveFilters() {
      const activeFilters = {};
      Object.entries(this.filterValues).forEach(([key, value]) => {
        if (Array.isArray(value)) {
          if (value.length > 0) {
            activeFilters[key] = value;
          }
        } else if (typeof value === 'object') {
          if (value.min || value.max) {
            activeFilters[key] = value;
          }
        } else if (value) {
          activeFilters[key] = value;
        }
      });
      return activeFilters;
    },
    
    // 获取筛选条件标签
    getFilterLabel(key) {
      const group = this.filterGroups.find(g => g.key === key);
      return group ? group.label : key;
    },
    
    // 获取筛选值显示文本
    getFilterDisplayValue(key, value) {
      const group = this.filterGroups.find(g => g.key === key);
      if (!group) return String(value);
      
      if (Array.isArray(value)) {
        return value
          .map(v => {
            const option = group.options.find(o => o.value === v);
            return option ? option.label : v;
          })
          .join(', ');
      } else if (typeof value === 'object') {
        if (group.type === 'dateRange') {
          return `${value.min || '不限'} - ${value.max || '不限'}`;
        } else if (group.type === 'range') {
          return `${value.min} - ${value.max}`;
        }
      } else {
        const option = group.options.find(o => o.value === value);
        return option ? option.label : value;
      }
      
      return String(value);
    }
  }
};
</script>

<style scoped>
.filter-component-container {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 24px;
  margin-bottom: 24px;
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}

.filter-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin: 0;
}

.filter-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-content {
  margin-bottom: 24px;
}

.filter-group {
  margin-bottom: 24px;
}

.filter-group-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
}

.filter-item {
  margin-bottom: 16px;
}

.filter-input, .filter-select, .filter-number-input, .filter-date-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.3s ease;
  box-sizing: border-box;
}

select.filter-select {
  appearance: none;
  background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='none' view_box='0 0 12 12'%3E%3Cpath fill='%236B7280' d='M6 9.2L1.4 4.6 2.5 3.5 6 7.01 9.5 3.5 10.6 4.6z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}

.filter-input:focus, .filter-select:focus, .filter-number-input:focus, .filter-date-input:focus {
  outline: none;
  border-color: #1677FF;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.radio-group, .checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.radio-label, .checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 14px;
  color: #666;
}

.radio-label input[type="radio"], .checkbox-label input[type="checkbox"] {
  margin-right: 8px;
  cursor: pointer;
}

.radio-text, .checkbox-text {
  cursor: pointer;
  user-select: none;
}

.date-range-container, .range-inputs {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.date-input-group, .range-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-input-group label, .range-input-group label {
  font-size: 14px;
  color: #666;
  min-width: 60px;
}

.date-separator, .range-separator {
  color: #999;
  font-size: 16px;
  font-weight: 500;
}

.range-slider-container {
  margin-top: 16px;
  padding: 0 12px;
}

.range-slider {
  width: 100%;
  margin-bottom: 8px;
}

.tag-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #f5f5f5;
  color: #666;
  border-radius: 16px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.tag-item:hover {
  background: #e6f7ff;
  color: #1677FF;
  border-color: #1677FF;
}

.tag-selected {
  background: #1677FF;
  color: white;
}

.tag-count {
  font-size: 12px;
  opacity: 0.8;
}

.filter-footer {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #e2e8f0;
}

.active-filters {
  margin-top: 16px;
}

.active-filters-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
}

.active-filters-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.active-filter-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #e6f7ff;
  color: #1677FF;
  border-radius: 16px;
  font-size: 14px;
}

.filter-label {
  font-weight: 600;
}

.filter-value {
  color: #1890ff;
}

.filter-remove-btn {
  background: transparent;
  border: none;
  color: #1677FF;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  margin-left: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.filter-remove-btn:hover {
  background: #1677FF;
  color: white;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
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
</style>