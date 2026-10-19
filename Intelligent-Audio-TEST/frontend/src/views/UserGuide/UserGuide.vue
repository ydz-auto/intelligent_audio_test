<template>
  <div class="user-guide-page">
    <div class="guide-container">
      <!-- 左目录 -->
      <aside class="guide-sidebar">
        <!-- 手册切换 -->
        <nav class="guide-manual-switch" aria-label="用户手册">
          <router-link to="/user-guide" class="manual-item" :class="{ active: isUsageManual }">
            <i class="fas fa-book manual-icon"></i>
            <span class="manual-text">使用手册</span>
          </router-link>
          <router-link to="/user-guide-api" class="manual-item" :class="{ active: !isUsageManual }">
            <i class="fas fa-code manual-icon"></i>
            <span class="manual-text">API 手册</span>
          </router-link>
        </nav>

        <div class="guide-toc">
          <h2 class="toc-title">目录</h2>
          <ul class="toc-list">
            <li v-for="section in guideDoc.sections" :key="section.id">
              <a
                :href="`#${section.id}`"
                class="toc-link"
                :class="{ active: activeId === section.id }"
                @click.prevent="jumpTo(section.id)"
              >{{ section.title }}</a>
            </li>
          </ul>
        </div>
      </aside>

      <!-- 右正文 -->
      <article class="guide-article">
        <h1 class="guide-h1">{{ guideDoc.title }}</h1>
        <p class="guide-subtitle">{{ guideDoc.subtitle }}</p>

        <section
          v-for="(section, idx) in guideDoc.sections"
          :key="section.id"
          :id="section.id"
          class="guide-section"
          :ref="(el) => setSectionRef(section.id, el)"
        >
          <h2 class="guide-h2">{{ section.title }}</h2>
          <template v-for="(block, i) in section.blocks" :key="i">
            <p v-if="block.kind === 'paragraph'" class="guide-paragraph">{{ block.text }}</p>
            <ul v-else-if="block.kind === 'list'" class="guide-list">
              <li v-for="(item, j) in block.items" :key="j">{{ item }}</li>
            </ul>
            <div v-else-if="block.kind === 'code'" class="guide-code-block card">
              <div class="code-block-header">
                <span class="code-language">{{ block.language }}</span>
                <button type="button" class="copy-btn" @click="copyCode(block.code, `${section.id}-${i}`)">
                  <i class="fas fa-copy"></i> {{ copiedIdx === `${section.id}-${i}` ? '已复制' : '复制代码' }}
                </button>
              </div>
              <pre class="code-pre"><code>{{ block.code }}</code></pre>
            </div>
            <div v-else-if="block.kind === 'table'" class="guide-table-scroll">
              <table class="guide-table">
                <thead>
                  <tr>
                    <th v-for="(h, k) in block.headers" :key="k">{{ h }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, r) in block.rows" :key="r">
                    <td v-for="(cell, c) in row" :key="c">{{ cell }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </section>

        <div class="guide-back-links">
          <router-link to="/user-guide">返回文档目录</router-link>
          <span class="guide-sep">·</span>
          <router-link to="/about">关于本平台</router-link>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { API_GUIDE, USER_GUIDE, type GuideDocument } from './guideContent'
import { useNotification } from '../../composables/modal/useNotification'

/**
 * 站内文档页（INT-745 A06）：左目录 + 右内容（原 Vue card + 排版 token）。
 * 手册切换跨路由（/user-guide ↔ /user-guide-api），滚回页顶。
 */
const route = useRoute()
const notification = useNotification()

const isUsageManual = computed(() => route.path === '/user-guide')
const guideDoc = computed<GuideDocument>(() => (isUsageManual.value ? USER_GUIDE : API_GUIDE))

const activeId = ref('')
const copiedIdx = ref('')
const sectionRefs = new Map<string, HTMLElement>()

function setSectionRef(id: string, el: unknown) {
  if (el instanceof HTMLElement) sectionRefs.set(id, el)
}

function jumpTo(id: string) {
  activeId.value = id
  const el = sectionRefs.get(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function copyCode(code: string, key: string) {
  navigator.clipboard?.writeText(code).then(() => {
    copiedIdx.value = key
    setTimeout(() => { copiedIdx.value = '' }, 1500)
  }).catch(() => {
    notification.error('复制失败，请手动复制')
  })
}

/** 公共页滚动容器（PublicLayout 自管滚动，INT-745 P1 修复：window 不滚动） */
function getScrollContainer(): HTMLElement | null {
  return document.querySelector('.public-layout')
}

function onScroll() {
  const sections = guideDoc.value.sections
  const container = getScrollContainer()
  let current = ''
  for (const section of sections) {
    const el = sectionRefs.get(section.id)
    if (el && el.getBoundingClientRect().top <= 120) current = section.id
  }
  // 触底强制高亮最后一节
  if (container && container.clientHeight + container.scrollTop >= container.scrollHeight - 4) {
    current = sections[sections.length - 1]?.id ?? ''
  }
  activeId.value = current
}

onMounted(() => {
  // 初始高亮第一目录项 + 监听滚动（容器为 .public-layout，非 window）
  activeId.value = guideDoc.value.sections[0]?.id ?? ''
  const container = getScrollContainer()
  container?.addEventListener('scroll', onScroll, { passive: true })
  container?.scrollTo(0, 0)
})

onBeforeUnmount(() => {
  getScrollContainer()?.removeEventListener('scroll', onScroll)
})
</script>

<style scoped>
.user-guide-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}
.guide-container {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 32px;
  align-items: start;
}
.guide-sidebar {
  position: sticky;
  top: 76px;
  max-height: calc(100vh - 90px);
  overflow-y: auto;
}
.guide-manual-switch {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
  margin-bottom: 12px;
}
.manual-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--muted-foreground);
  text-decoration: none;
}
.manual-item:hover {
  background: var(--muted);
  color: var(--foreground);
}
.manual-item.active {
  background: var(--accent);
  color: var(--primary);
  font-weight: 500;
}
.manual-icon {
  width: 16px;
  text-align: center;
}
.toc-title {
  margin: 0 0 8px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
}
.toc-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.toc-link {
  display: block;
  padding: 6px 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted-foreground);
  text-decoration: none;
  border-left: 2px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.toc-link:hover {
  background: var(--muted);
  color: var(--foreground);
}
.toc-link.active {
  border-left-color: var(--primary);
  background: var(--accent);
  color: var(--primary);
  font-weight: 500;
}
/* 正文 */
.guide-article {
  min-width: 0;
}
.guide-h1 {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  color: var(--foreground);
}
.guide-subtitle {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--muted-foreground);
}
.guide-section {
  scroll-margin-top: 80px;
}
.guide-h2 {
  margin: 32px 0 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 19px;
  font-weight: 600;
  color: var(--foreground);
}
.guide-section:first-of-type .guide-h2 {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}
.guide-paragraph {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--foreground);
}
.guide-list {
  margin: 0 0 12px;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--foreground);
}
/* 代码块：原 card 深色块 */
.guide-code-block {
  margin: 12px 0;
  border-radius: var(--radius-md);
  overflow: hidden;
}
.code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--muted);
  border-bottom: 1px solid var(--border);
}
.code-language {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
}
.copy-btn {
  border: none;
  background: none;
  font-size: 12px;
  color: var(--muted-foreground);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}
.copy-btn:hover {
  color: var(--primary);
  background: var(--accent);
}
.code-pre {
  margin: 0;
  padding: 16px;
  background: var(--code-bg);
  color: var(--code-text);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  /* 圆角由 .guide-code-block（overflow:hidden + border-radius: var(--radius-md)）裁切，不在此重复定义 */
}
/* 表格 */
.guide-table-scroll {
  margin: 12px 0;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.guide-table {
  width: 100%;
  min-width: 480px;
  border-collapse: collapse;
  font-size: 13px;
}
.guide-table th {
  background: var(--muted);
  font-weight: 600;
  text-align: left;
  padding: 10px 14px;
  white-space: nowrap;
  color: var(--foreground);
}
.guide-table td {
  padding: 10px 14px;
  border-top: 1px solid var(--border);
  color: var(--foreground);
  line-height: 1.6;
}
/* 底部回链 */
.guide-back-links {
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 13px;
  color: var(--muted-foreground);
}
.guide-back-links a {
  color: var(--primary);
  text-decoration: none;
}
.guide-back-links a:hover {
  text-decoration: underline;
}
.guide-sep {
  margin: 0 6px;
}
@media (max-width: 860px) {
  .guide-container {
    grid-template-columns: 1fr;
  }
  .guide-sidebar {
    position: static;
    max-height: none;
  }
}
</style>
