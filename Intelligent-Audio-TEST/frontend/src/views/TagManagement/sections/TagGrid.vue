<template>
  <div class="tag-main-content">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">
          <i class="fas fa-tag"></i>
          {{ currentCategoryName }}
          <span class="tag-total-count">共 {{ tagTotal }} 个标签</span>
        </h3>
        <div class="card-actions">
          <div class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input
              type="text"
              v-model="searchKeyword"
              placeholder="搜索标签..."
              class="search-input"
              @input="handleSearchInput"
            />
          </div>
        </div>
      </div>
      <div
        class="card-body tag-scroll-container"
        ref="scrollContainer"
        @scroll="handleTagScroll"
      >
        <div v-if="tags.length === 0 && !tagLoading" class="empty-state">
          <i class="fas fa-inbox"></i>
          <p>{{ searchKeyword ? '没有找到匹配的标签' : '暂无标签' }}</p>
          <button v-if="!searchKeyword" class="btn btn-primary" @click="emit('open-tag-modal')">
            <i class="fas fa-plus btn-icon"></i>
            创建第一个标签
          </button>
        </div>

        <div v-else class="tag-grid">
          <div
            v-for="tag in tags"
            :key="tag.id"
            class="tag-card"
          >
            <div class="tag-color-bar" :style="{ backgroundColor: tag.color || '#6366f1' }"></div>
            <div class="tag-card-content">
              <div class="tag-header">
                <span class="tag-name">{{ tag.name }}</span>
                <div class="tag-actions">
                  <button class="btn btn-text btn-primary" @click="emit('open-tag-modal', tag)" title="编辑">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="btn btn-text btn-danger" @click="emit('confirm-delete-tag', tag)" title="删除">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>
              <p v-if="tag.description" class="tag-description">{{ tag.description }}</p>
              <div class="tag-meta">
                <span v-if="tag.categoryName" class="tag-category">
                  <i class="fas fa-folder"></i> {{ tag.categoryName }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="tagLoading" class="loading-more">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>

          <div v-if="!tagHasMore && tags.length > 0 && !tagLoading" class="no-more-data">
            <span>已加载全部 {{ tagTotal }} 个标签</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { TagItem } from '@/utils/api'

const props = defineProps<{
  tags: TagItem[]
  tagTotal: number
  tagLoading: boolean
  tagHasMore: boolean
  currentCategoryName: string
}>()

const emit = defineEmits<{
  (e: 'open-tag-modal', tag?: TagItem): void
  (e: 'confirm-delete-tag', tag: TagItem): void
  (e: 'search-tags', keyword: string): void
  (e: 'tag-scroll'): void
}>()

const searchKeyword = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

function handleSearchInput() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    emit('search-tags', searchKeyword.value)
  }, 300)
}

function handleTagScroll(event: Event) {
  const container = event.target as HTMLElement
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 100 && props.tagHasMore && !props.tagLoading) {
    emit('tag-scroll')
  }
}
</script>
