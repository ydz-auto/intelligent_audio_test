<template>
  <div class="pagination-container">
    <div class="pagination-info">
      显示第 {{ currentPage }} 页，共 {{ computedTotalPages }} 页，总计 {{ totalItems }} 条记录
    </div>
    <div class="pagination-buttons">
      <button 
        class="pagination-btn" 
        @click="$emit('prev-page')" 
        :disabled="currentPage === 1"
      >
        &lt; 上一页
      </button>
      
      <!-- 页码显示逻辑 -->
      <!-- 显示第一页 -->
      <button 
        class="pagination-btn"
        :class="{ active: currentPage === 1 }"
        @click="$emit('go-to-page', 1)"
      >
        1
      </button>
      
      <!-- 左边省略号 -->
      <span v-if="currentPage > 3" class="pagination-ellipsis">...</span>
      
      <!-- 当前页附近的页码 -->
      <button 
        v-for="page in visiblePages" 
        :key="page"
        class="pagination-btn"
        :class="{ active: currentPage === page }"
        @click="$emit('go-to-page', page)"
      >
        {{ page }}
      </button>
      
      <!-- 右边省略号 -->
      <span v-if="currentPage < computedTotalPages - 2" class="pagination-ellipsis">...</span>
      
      <!-- 显示最后一页 -->
      <button 
        v-if="computedTotalPages > 1"
        class="pagination-btn"
        :class="{ active: currentPage === computedTotalPages }"
        @click="$emit('go-to-page', computedTotalPages)"
      >
        {{ computedTotalPages }}
      </button>
      
      <button 
        class="pagination-btn" 
        @click="$emit('next-page')" 
        :disabled="currentPage === computedTotalPages"
      >
        下一页 &gt;
      </button>
      
      <!-- 跳转到指定页 -->
      <div class="pagination-jump">
        <span>跳转到</span>
        <input 
          type="number" 
          class="pagination-input"
          v-model.number="jumpPage"
          :min="1"
          :max="totalPages"
          @keydown.enter="handleJump"
          placeholder="页码"
        >
        <span>页</span>
        <button class="pagination-btn jump-btn" @click="handleJump">跳转</button>
      </div>
    </div>
    <div class="page-size-select">
      <span>每页显示：</span>
      <select 
        :value="pageSize" 
        @change="$emit('page-size-change', parseInt($event.target.value))"
      >
        <option value="10">10</option>
        <option value="20">20</option>
        <option value="50">50</option>
        <option value="100">100</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';

const props = defineProps({
  currentPage: { type: Number, required: true },
  pageSize: { type: Number, default: 10 },
  totalItems: { type: Number, required: true },
  totalPages: { type: Number, default: null }
});

const jumpPage = ref(props.currentPage);

watch(() => props.currentPage, (newPage) => {
  jumpPage.value = newPage;
});

const computedTotalPages = computed(() => {
  if (props.totalPages !== null) {
    return props.totalPages;
  }
  return Math.ceil(props.totalItems / props.pageSize);
});

const visiblePages = computed(() => {
  const pages = [];
  const current = props.currentPage;
  const total = computedTotalPages.value;
  
  for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
    pages.push(i);
  }
  
  return pages;
});

const emit = defineEmits(['prev-page', 'next-page', 'go-to-page', 'page-size-change']);

const handleJump = () => {
  let page = parseInt(jumpPage.value);
  if (isNaN(page) || page < 1) {
    page = 1;
  } else if (page > computedTotalPages.value) {
    page = computedTotalPages.value;
  }
  emit('go-to-page', page);
};
</script>

<style scoped>
/* 分页组件特定样式 */
.pagination-container {
    /* 公共样式已在 components/common.css 中定义 */
}

.pagination-btn {
    /* 公共样式已在 components/common.css 中定义 */
}

.pagination-btn.active {
    /* 公共样式已在 components/common.css 中定义 */
}
</style>