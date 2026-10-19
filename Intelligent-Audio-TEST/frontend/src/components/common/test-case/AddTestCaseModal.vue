<template>
  <teleport to="body">
    <div class="modal-backdrop" @click="closeModal" v-if="visible">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>中途新增测试用例</h3>
          <button class="close-btn" @click="closeModal">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="search-filter-bar">
            <div class="search-box">
              <i class="fas fa-search search-icon"></i>
              <input type="text" class="search-input" placeholder="搜索测试用例..." v-model="searchQuery" @input="handleSearch">
            </div>
            <div class="filter-select">
              <select class="form-input" v-model="selectedTag" @change="handleFilter">
                <option value="all">所有标签</option>
                <option v-for="tag in availableTags" :key="tag" :value="tag">{{ tag }}</option>
              </select>
            </div>
          </div>
          
          <div class="test-case-list-container">
            <div v-if="filteredTestCases.length === 0" class="no-items-message">
              <i class="fas fa-info-circle"></i>
              <p>暂无匹配的测试用例</p>
            </div>
            <div v-else class="test-case-grid">
              <TestCaseCard
                v-for="testCase in filteredTestCases"
                :key="testCase.id"
                :test-case="testCase"
                :is-selected="selectedTestCases.includes(testCase.id)"
                :show-checkbox="true"
                :show-config="false"
                @toggle-selection="toggleTestCaseSelection"
                :actions="[]"
              />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeModal">取消</button>
          <button class="btn btn-primary" @click="addSelectedCases" :disabled="selectedTestCases.length === 0">
            <i class="fas fa-plus"></i> 新增选中用例 ({{ selectedTestCases.length }})
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { ref, computed, watch } from 'vue';
import TestCaseCard from './TestCaseCard.vue';

const props = defineProps({
  visible: { type: Boolean, default: false },
  testCases: { type: Array, default: () => [] }
});

const emit = defineEmits(['close', 'add-test-cases']);

const searchQuery = ref('');
const selectedTag = ref('all');
const selectedTestCases = ref([]);

const filteredTestCases = computed(() => {
  let result = [...props.testCases];
  
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    result = result.filter(testCase => 
      testCase.name.toLowerCase().includes(query) || 
      (testCase.description && testCase.description.toLowerCase().includes(query))
    );
  }
  
  if (selectedTag.value !== 'all') {
    result = result.filter(testCase => 
      testCase.tags && testCase.tags.includes(selectedTag.value)
    );
  }
  
  return result;
});

const availableTags = computed(() => {
  const tags = new Set();
  props.testCases.forEach(testCase => {
    if (testCase.tags) {
      testCase.tags.forEach(tag => tags.add(tag));
    }
  });
  return Array.from(tags);
});

const closeModal = () => {
  resetModal();
  emit('close');
};

const resetModal = () => {
  searchQuery.value = '';
  selectedTag.value = 'all';
  selectedTestCases.value = [];
};

const toggleTestCaseSelection = (testCaseId) => {
  const index = selectedTestCases.value.indexOf(testCaseId);
  if (index > -1) {
    selectedTestCases.value.splice(index, 1);
  } else {
    selectedTestCases.value.push(testCaseId);
  }
};

const addSelectedCases = () => {
  emit('add-test-cases', selectedTestCases.value);
  closeModal();
};

const handleSearch = () => {
};

const handleFilter = () => {
};

watch(() => props.visible, (newValue) => {
  if (newValue) {
    resetModal();
  }
});
</script>

<style scoped>

.close-btn{
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: var(--color-slate-500);
    padding: 0;
    line-height: 1;
}

.close-btn:hover{
    color: var(--color-slate-700);
}






.search-filter-bar{
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-icon{
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary);
  font-size: 16px;
}

.search-input{
  width: 100%;
  padding: 10px 12px 10px 40px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-control);
  font-size: 14px;
  transition: all 0.3s ease;
}

.search-input:focus{
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 10%, transparent);
}

.filter-select{
  min-width: 150px;
}

.form-input{
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-control);
  font-size: 14px;
  transition: all 0.3s ease;
}

.form-input:focus{
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 10%, transparent);
}

.test-case-list-container{
  margin-top: 20px;
}

.no-items-message{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.no-items-message i{
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.no-items-message p{
  margin: 0;
  font-size: 16px;
}

.test-case-grid{
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 768px){
  .search-filter-bar {
    flex-direction: column;
  }
  
  .search-box,
  .filter-select {
    width: 100%;
    min-width: auto;
  }
}
</style>