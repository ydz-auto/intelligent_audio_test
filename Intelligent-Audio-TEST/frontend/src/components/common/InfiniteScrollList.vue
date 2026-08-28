<template>
  <div class="infinite-scroll-container" ref="containerRef">
    <!-- 空状态 -->
    <div v-if="!loading && visibleItems.length === 0" class="empty-state">
      <slot name="empty">
        <i class="fas fa-info-circle"></i>
        <p>暂无数据</p>
      </slot>
    </div>

    <template v-else>
      <!-- 内容区域：父组件通过默认插槽控制具体渲染 -->
      <slot :items="visibleItems"></slot>

      <!-- 首次加载 -->
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- 加载更多中 -->
      <div v-if="loadingMore" class="loading-more">
        <i class="fas fa-spinner fa-spin"></i>
        <span>加载更多...</span>
      </div>

      <!-- 加载更多提示 -->
      <div v-if="hasMore && !loadingMore && visibleItems.length > 0" ref="triggerRef" class="load-more-trigger">
        <span class="load-more-hint">
          已显示 {{ visibleItems.length }} / {{ items.length }} 条
        </span>
        <button class="btn btn-secondary btn-sm" @click="loadMore">
          <i class="fas fa-chevron-down"></i> 加载更多
        </button>
      </div>

      <!-- 全部加载完成 -->
      <div v-if="!hasMore && visibleItems.length > 0 && items.length > pageSize" class="all-loaded">
        <span>已加载全部 {{ items.length }} 条记录</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  pageSize: { type: Number, default: 10 },
  loading: { type: Boolean, default: false },
  scrollThreshold: { type: Number, default: 200 }
});

const emit = defineEmits(['page-change']);

const containerRef = ref(null);
const triggerRef = ref(null);
const currentPage = ref(1);
const loadingMore = ref(false);
let observer = null;

const pageSize = computed(() => props.pageSize);
const visibleItems = computed(() => {
  const end = currentPage.value * pageSize.value;
  const arr = Array.isArray(props.items) ? props.items : [];
  return arr.slice(0, end);
});

const hasMore = computed(() => {
  return visibleItems.value.length < (Array.isArray(props.items) ? props.items.length : 0);
});

watch(() => props.items, () => {
  currentPage.value = 1;
}, { deep: false });

const loadMore = () => {
  if (loadingMore.value || !hasMore.value) return;
  loadingMore.value = true;
  setTimeout(() => {
    currentPage.value++;
    loadingMore.value = false;
    emit('page-change', currentPage.value);
  }, 200);
};

// 使用 IntersectionObserver 监听触发元素是否进入视口
const setupObserver = () => {
  if (observer) {
    observer.disconnect();
  }
  observer = new IntersectionObserver((entries) => {
    const entry = entries[0];
    if (entry.isIntersecting && hasMore.value && !loadingMore.value) {
      loadMore();
    }
  }, {
    root: null,
    rootMargin: `${props.scrollThreshold}px`,
    threshold: 0
  });

  nextTick(() => {
    if (triggerRef.value) {
      observer.observe(triggerRef.value);
    }
  });
};

watch(hasMore, (val) => {
  if (val) {
    nextTick(setupObserver);
  }
});

watch(() => props.items, () => {
  nextTick(setupObserver);
});

onMounted(() => {
  setupObserver();
});

onUnmounted(() => {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
});

defineExpose({
  resetPage: () => {
    currentPage.value = 1;
  },
  getCurrentPage: () => currentPage.value,
  getPageSize: () => pageSize.value,
  scrollToTop: () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
});
</script>

<style scoped>
.infinite-scroll-container {
  /* 不设置 max-height 和 overflow，让页面自然滚动 */
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  color: #64748b;
  background-color: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  width: 100%;
  margin: 0 auto;
}

.empty-state i {
  font-size: 32px;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 0;
  font-size: 15px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

.spinner {
  border: 4px solid var(--background-tertiary, #e2e8f0);
  border-top: 4px solid var(--primary-color, #3b82f6);
  border-radius: 50%;
  width: 36px;
  height: 36px;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-state p {
  margin: 0;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
}

.load-more-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 12px;
  border-top: 1px dashed var(--border-color, #e2e8f0);
  margin-top: 8px;
}

.load-more-hint {
  color: var(--text-tertiary, #94a3b8);
  font-size: 12px;
}

.all-loaded {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: var(--text-tertiary, #94a3b8);
  font-size: 12px;
  border-top: 1px dashed var(--border-color, #e2e8f0);
  margin-top: 8px;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}
</style>
