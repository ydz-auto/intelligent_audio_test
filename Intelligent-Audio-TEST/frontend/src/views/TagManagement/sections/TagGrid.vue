<template>
  <div class="tg-tag-main-content">
    <div class="tg-card">
      <div class="tg-card-header">
        <h3 class="tg-card-title">
          <i class="fas fa-tag"></i>
          {{ currentCategoryName }}
          <span class="tg-tag-total-count">共 {{ tagTotal }} 个标签</span>
        </h3>
        <div class="tg-card-actions">
          <div class="tg-search-box">
            <i class="fas fa-search tg-search-icon"></i>
            <input
              type="text"
              v-model="searchKeyword"
              placeholder="搜索标签..."
              class="tg-search-input"
              @input="handleSearchInput"
            />
          </div>
        </div>
      </div>
      <div
        class="tg-card-body tg-tag-scroll-container"
        ref="scrollContainer"
        @scroll="handleTagScroll"
      >
        <div v-if="tags.length === 0 && !tagLoading" class="tg-empty-state">
          <i class="fas fa-inbox"></i>
          <p>{{ searchKeyword ? '没有找到匹配的标签' : '暂无标签' }}</p>
          <button v-if="!searchKeyword" class="tg-btn tg-btn-primary" @click="emit('open-tag-modal')">
            <i class="fas fa-plus tg-btn-icon"></i>
            创建第一个标签
          </button>
        </div>

        <div v-else class="tg-tag-grid">
          <div
            v-for="tag in tags"
            :key="tag.id"
            class="tg-tag-card"
          >
            <div class="tg-tag-color-bar" :style="{ backgroundColor: tag.color || '#6366f1' }"></div>
            <div class="tg-tag-card-content">
              <div class="tg-tag-header">
                <span class="tg-tag-name">{{ tag.name }}</span>
                <div class="tg-tag-actions">
                  <button class="tg-btn tg-btn-text tg-btn-primary" @click="emit('open-tag-modal', tag)" title="编辑">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="tg-btn tg-btn-text tg-btn-danger" @click="emit('confirm-delete-tag', tag)" title="删除">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>
              <p v-if="tag.description" class="tg-tag-description">{{ tag.description }}</p>
              <div class="tg-tag-meta">
                <span v-if="tag.categoryName" class="tg-tag-category">
                  <i class="fas fa-folder"></i> {{ tag.categoryName }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="tagLoading" class="tg-loading-more">
            <i class="fas fa-spinner fa-spin"></i>
            <span>加载中...</span>
          </div>

          <div v-if="!tagHasMore && tags.length > 0 && !tagLoading" class="tg-no-more-data">
            <span>已加载全部 {{ tagTotal }} 个标签</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { TagItem } from '@/domain/model/tag'

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
