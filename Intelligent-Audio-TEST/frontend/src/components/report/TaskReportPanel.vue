<template>
  <div class="task-report-panel">
    <div class="report-layout">
      <div class="report-main">
        <div class="report-header">
          <h1 class="report-title">{{ report.title || report.name || '任务报告' }}</h1>
          <div class="report-meta">
            <span class="report-date">{{ formatDate(report.createdAt || report.created_at) }}</span>
            <span class="report-status" :class="report.status">
              {{ report.status === 'draft' ? '草稿' : '已发布' }}
            </span>
          </div>
          <p class="report-description" v-if="report.description">{{ report.description }}</p>
        </div>

        <div class="report-section" id="section-overview">
          <OverviewCardComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-analysis">
          <h2 class="section-title">分析结论</h2>
          <div class="analysis-content">
            <div v-if="!localIsEditing" class="analysis-text" v-html="sanitizedAnalysisContent"></div>
            <div v-else class="analysis-edit">
              <textarea 
                v-model="editableConclusion" 
                placeholder="请输入分析结论..."
                class="analysis-textarea"
              ></textarea>
            </div>
            <div class="analysis-actions">
              <button v-if="!localIsEditing" class="btn-link" @click="startEdit">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn-primary" @click="saveLocalConclusion">保存</button>
                <button class="btn-secondary" @click="cancelLocalConclusion">取消</button>
              </template>
            </div>
          </div>
        </div>

        <div v-for="(table, idx) in tables" :key="idx" class="report-section">
          <ComparisonTableComponent 
            :title="table.title"
            :columns="table.columns"
            :data="table.data"
            :defaultCollapsed="table.defaultCollapsed !== false"
          />
        </div>

        <div class="report-section" id="section-category">
          <CaseCategoryComparisonComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-tag">
          <CaseTagComparisonComponent :reportData="report" />
        </div>

        <div class="report-section" id="section-case">
          <SpecificCaseComparisonComponent :reportData="report" />
        </div>
      </div>

      <div class="report-nav">
        <nav class="nav-menu">
          <a 
            v-for="item in navItems" 
            :key="item.id"
            :href="'#' + item.id"
            :class="['nav-item', { active: activeSection === item.id }]"
            @click.prevent="scrollToSection(item.id)"
          >
            <span class="nav-dot"></span>
            <span class="nav-label">{{ item.label }}</span>
          </a>
        </nav>
        <div class="nav-progress">
          <div class="progress-fill" :style="{ height: progressHeight }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue';
import { sanitizeConclusion } from '../../utils/sanitize';
import ComparisonTableComponent from './ComparisonTableComponent.vue'
import CaseCategoryComparisonComponent from './CaseCategoryComparisonComponent.vue'
import CaseTagComparisonComponent from './CaseTagComparisonComponent.vue'
import SpecificCaseComparisonComponent from './SpecificCaseComparisonComponent.vue'
import OverviewCardComponent from './OverviewCardComponent.vue'

const props = defineProps({
  report: { type: Object, required: true },
  isEditingReport: { type: Boolean, default: false },
  isEditingConclusion: { type: Boolean, default: false },
  analysisContent: { type: String, default: '' },
  tables: { type: Array, default: () => [] }
})

const emit = defineEmits(['toggle-edit', 'save-report', 'cancel-edit', 'toggle-conclusion-edit', 'save-conclusion', 'cancel-conclusion'])

const editableConclusion = ref('')
const localIsEditing = ref(false)
const activeSection = ref('section-overview')
const progressHeight = ref('0%')

const navItems = [
  { id: 'section-overview', label: '概览' },
  { id: 'section-analysis', label: '分析结论' },
  { id: 'section-category', label: '用例分组' },
  { id: 'section-tag', label: '用例标签' },
  { id: 'section-case', label: '具体用例' },
]

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

watch(() => props.analysisContent, (newVal) => {
  editableConclusion.value = newVal
}, { immediate: true })

const sanitizedAnalysisContent = computed(() => {
  return sanitizeConclusion(props.analysisContent);
});

const startEdit = () => {
  editableConclusion.value = props.analysisContent
  localIsEditing.value = true
}

const saveLocalConclusion = () => {
  emit('save-conclusion', editableConclusion.value)
  localIsEditing.value = false
}

const cancelLocalConclusion = () => {
  editableConclusion.value = props.analysisContent
  localIsEditing.value = false
  emit('cancel-conclusion')
}

const scrollToSection = (sectionId) => {
  const element = document.getElementById(sectionId)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setTimeout(() => {
      window.scrollBy({ top: -80, behavior: 'smooth' })
    }, 100)
  }
}

const handleScroll = () => {
  const sections = navItems.map(item => ({
    id: item.id,
    element: document.getElementById(item.id)
  }))
  
  let currentSection = 'section-overview'
  const scrollPosition = window.scrollY + 120
  
  sections.forEach(section => {
    if (section.element) {
      const sectionTop = section.element.offsetTop
      const sectionHeight = section.element.offsetHeight
      if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
        currentSection = section.id
      }
    }
  })
  
  activeSection.value = currentSection
  
  const docHeight = document.documentElement.scrollHeight - window.innerHeight
  const scrollPercent = (window.scrollY / docHeight) * 100
  progressHeight.value = Math.min(100, Math.max(0, scrollPercent)) + '%'
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
  handleScroll()
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.task-report-panel {
  width: 100%;
  min-height: 100vh;
  background: #fafafa;
}

.report-layout {
  display: flex;
  max-width: 1200px;
  margin: 0 auto;
  gap: 32px;
  padding: 32px 24px;
}

.report-main {
  flex: 1;
  min-width: 0;
}

.report-nav {
  width: 160px;
  flex-shrink: 0;
  position: sticky;
  top: 80px;
  height: fit-content;
  align-self: flex-start;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: 8px;
  text-decoration: none;
  color: #64748b;
  font-size: 14px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.nav-item:hover {
  background: #f1f5f9;
  color: #334155;
}

.nav-item.active {
  color: #1677FF;
  font-weight: 500;
}

.nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: all 0.2s ease;
}

.nav-item.active .nav-dot {
  background: #1677FF;
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.2);
}

.nav-label {
  flex: 1;
}

.nav-progress {
  position: absolute;
  left: 22px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: #e2e8f0;
  border-radius: 1px;
}

.progress-fill {
  width: 100%;
  background: #1677FF;
  border-radius: 1px;
  transition: height 0.1s ease;
}

.report-header {
  margin-bottom: 32px;
}

.report-title {
  font-size: 28px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 8px 0;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.report-date {
  font-size: 14px;
  color: #64748b;
}

.report-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.report-status.draft {
  background: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.report-description {
  font-size: 15px;
  color: #64748b;
  line-height: 1.6;
  margin: 0;
}

.report-section {
  margin-bottom: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 16px 0;
}

.analysis-content {
  background: white;
  border-radius: 12px;
  padding: 24px;
}

.analysis-text {
  font-size: 15px;
  color: #475569;
  line-height: 1.8;
  min-height: 80px;
}

.analysis-edit {
  display: flex;
  flex-direction: column;
}

.analysis-textarea {
  width: 100%;
  min-height: 150px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  transition: border-color 0.2s ease;
}

.analysis-textarea:focus {
  outline: none;
  border-color: #1677FF;
}

.analysis-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.btn-link {
  background: none;
  border: none;
  color: #1677FF;
  font-size: 14px;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s ease;
}

.btn-link:hover {
  background: rgba(22, 119, 255, 0.1);
}

.btn-primary {
  background: #1677FF;
  color: white;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover {
  background: #0958D9;
}

.btn-secondary {
  background: #f1f5f9;
  color: #64748b;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-secondary:hover {
  background: #e2e8f0;
}

@media (max-width: 900px) {
  .report-layout {
    flex-direction: column;
    gap: 24px;
  }
  
  .report-nav {
    width: 100%;
    position: relative;
    top: 0;
    order: -1;
  }
  
  .nav-menu {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .nav-item {
    padding: 8px 12px;
  }
  
  .nav-progress {
    display: none;
  }
}
</style>
