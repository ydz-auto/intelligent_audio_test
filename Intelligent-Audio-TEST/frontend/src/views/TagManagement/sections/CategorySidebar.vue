<template>
  <div class="category-sidebar">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">
          <i class="fas fa-folder"></i>
          标签分类
          <span class="total-count">共 {{ categoryTotal }} 个</span>
        </h3>
        <button class="btn btn-text btn-primary" @click="emit('open-category-modal')">
          <i class="fas fa-plus btn-icon"></i>
          新建
        </button>
      </div>
      <div class="card-search">
        <div class="search-box">
          <i class="fas fa-search search-icon"></i>
          <input
            type="text"
            v-model="categorySearchKeyword"
            placeholder="搜索分类..."
            class="search-input"
            @input="handleCategorySearchInput"
          />
        </div>
      </div>
      <div
        class="card-body category-scroll-container"
        ref="scrollContainer"
        @scroll="handleCategoryScroll"
      >
        <div class="category-list">
          <div
            v-for="cat in categories"
            :key="cat.id"
            :class="['category-item', { active: selectedCategoryId === cat.id }]"
            @click="emit('select-category', cat.id)"
          >
            <div class="category-info">
              <span class="category-color" :style="{ backgroundColor: cat.color || '#6366f1' }"></span>
              <span class="category-name">{{ cat.name }}</span>
              <span class="tag-count-badge">{{ cat.tagCount }}</span>
            </div>
            <div class="category-actions" v-if="selectedCategoryId === cat.id">
              <button class="btn btn-text btn-primary" @click.stop="emit('open-category-modal', cat)" title="编辑">
                <i class="fas fa-edit"></i>
              </button>
              <button class="btn btn-text btn-danger" @click.stop="emit('confirm-delete-category', cat)" title="删除">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>

          <div
            :class="['category-item', { active: selectedCategoryId === null }]"
            @click="emit('select-category', null)"
          >
            <div class="category-info">
              <span class="category-color" :style="{ backgroundColor: '#94a3b8' }"></span>
              <span class="category-name">未分类</span>
              <span class="tag-count-badge">{{ uncategorizedCount }}</span>
            </div>
          </div>

          <div v-if="categoryLoading" class="loading-more-categories">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>

          <div v-if="!categoryHasMore && categories.length > 0 && !categoryLoading" class="no-more-categories">
            <span>已加载全部</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { TagCategory } from '@/utils/api'

const props = defineProps<{
  categories: TagCategory[]
  selectedCategoryId: number | null
  categoryTotal: number
  categoryLoading: boolean
  categoryHasMore: boolean
  uncategorizedCount: number
}>()

const emit = defineEmits<{
  (e: 'select-category', id: number | null): void
  (e: 'open-category-modal', cat?: TagCategory): void
  (e: 'confirm-delete-category', cat: TagCategory): void
  (e: 'search-categories', keyword: string): void
  (e: 'category-scroll'): void
}>()

const categorySearchKeyword = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

let categorySearchDebounceTimer: ReturnType<typeof setTimeout> | null = null

function handleCategorySearchInput() {
  if (categorySearchDebounceTimer) {
    clearTimeout(categorySearchDebounceTimer)
  }
  categorySearchDebounceTimer = setTimeout(() => {
    emit('search-categories', categorySearchKeyword.value)
  }, 300)
}

function handleCategoryScroll(event: Event) {
  const container = event.target as HTMLElement
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 50 && props.categoryHasMore && !props.categoryLoading) {
    emit('category-scroll')
  }
}
</script>
