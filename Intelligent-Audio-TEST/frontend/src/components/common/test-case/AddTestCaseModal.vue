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

<style>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10002;
  animation: fadeIn 0.3s ease;
}

.modal-container {
  background-color: white;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-lg);
  width: 90%;
  max-width: 800px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.3s ease;
}

.modal-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.close-btn:hover {
  background-color: var(--background-secondary);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 20px 24px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 10px 24px;
  border: none;
  border-radius: var(--border-radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background-color: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background-color: var(--background-tertiary);
  border-color: var(--primary-color);
  transform: translateY(-1px);
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .modal-container {
    width: 95%;
    margin: 20px;
    max-height: calc(100vh - 40px);
  }
}
</style>

<style scoped>
.search-filter-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-box {
  flex: 1;
  min-width: 200px;
  position: relative;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary);
  font-size: 16px;
}

.search-input {
  width: 100%;
  padding: 10px 12px 10px 40px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  font-size: 14px;
  transition: all 0.3s ease;
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.1);
}

.filter-select {
  min-width: 150px;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  font-size: 14px;
  transition: all 0.3s ease;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.1);
}

.test-case-list-container {
  margin-top: 20px;
}

.no-items-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.no-items-message i {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.no-items-message p {
  margin: 0;
  font-size: 16px;
}

.test-case-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 768px) {
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