<template>
  <div class="task-report-panel">
    <div class="report-layout">
      <div class="report-main">
        <div class="report-header-section">
          <div class="report-header-content">
            <div class="report-title-area">
              <h1 class="report-main-title">{{ report.title || '任务报告' }}</h1>
              <div class="report-meta">
                <span class="report-date">
                  <i class="fas fa-calendar-alt"></i>
                  {{ formatDate(report.createdAt || report.created_at) }}
                </span>
                <span class="report-status" :class="report.status">
                  <span class="status-dot"></span>
                  {{ report.status === 'draft' ? '草稿' : '已发布' }}
                </span>
              </div>
            </div>
            <div class="report-actions-area">
              <button v-if="!isEditingReport" class="action-btn primary" @click="$emit('toggle-edit')">
                <i class="fas fa-edit"></i>
                <span>编辑</span>
              </button>
              <template v-else>
                <button class="action-btn primary" @click="$emit('save-report')">
                  <i class="fas fa-save"></i>
                  <span>保存</span>
                </button>
                <button class="action-btn secondary" @click="$emit('cancel-edit')">
                  <i class="fas fa-times"></i>
                  <span>取消</span>
                </button>
              </template>
            </div>
          </div>
          
          <div class="report-description-section">
            <div v-if="!isEditingReport" class="description-text">
              {{ report.description || '点击编辑添加报告描述' }}
            </div>
            <div v-else class="description-edit">
              <input type="text" placeholder="报告名称" v-model="report.title" class="edit-input title-input">
              <textarea placeholder="报告描述" rows="3" v-model="report.description" class="edit-input desc-input"></textarea>
            </div>
          </div>
        </div>

        <div class="report-section" id="section-overview" ref="overviewRef">
          <div class="section-header">
            <div class="section-icon overview">
              <i class="fas fa-chart-pie"></i>
            </div>
            <h2 class="section-title">概览</h2>
          </div>
          <div class="section-content">
            <OverviewCardComponent :reportData="report" />
          </div>
        </div>

        <div class="report-section" id="section-analysis" ref="analysisRef">
          <div class="section-header">
            <div class="section-icon analysis">
              <i class="fas fa-lightbulb"></i>
            </div>
            <h2 class="section-title">分析结论</h2>
          </div>
          <div class="section-content">
            <div class="analysis-card">
              <div v-if="!localIsEditing" class="analysis-text" v-html="sanitizedAnalysisContent"></div>
              <div v-else class="analysis-edit">
                <textarea 
                  v-model="editableConclusion" 
                  placeholder="请输入分析结论..."
                  class="analysis-textarea"
                ></textarea>
              </div>
              <div class="analysis-actions">
                <button v-if="!localIsEditing" class="action-btn primary" @click="startEdit">
                  <i class="fas fa-edit"></i>
                  <span>编辑</span>
                </button>
                <template v-else>
                  <button class="action-btn primary" @click="saveLocalConclusion">
                    <i class="fas fa-save"></i>
                    <span>保存</span>
                  </button>
                  <button class="action-btn secondary" @click="cancelLocalConclusion">
                    <i class="fas fa-times"></i>
                    <span>取消</span>
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>

        <div v-for="(table, idx) in tables" :key="idx" class="report-section">
          <div class="section-header">
            <div class="section-icon comparison">
              <i class="fas fa-table"></i>
            </div>
            <h2 class="section-title">{{ table.title }}</h2>
          </div>
          <div class="section-content">
            <ComparisonTableComponent 
              :title="table.title"
              :columns="table.columns"
              :data="table.data"
              :defaultCollapsed="table.defaultCollapsed !== false"
            />
          </div>
        </div>

        <div class="report-section" id="section-category" ref="categoryRef">
          <div class="section-header">
            <div class="section-icon category">
              <i class="fas fa-layer-group"></i>
            </div>
            <h2 class="section-title">按用例分组对比</h2>
          </div>
          <div class="section-content">
            <CaseCategoryComparisonComponent :reportData="report" />
          </div>
        </div>

        <div class="report-section" id="section-tag" ref="tagRef">
          <div class="section-header">
            <div class="section-icon tag">
              <i class="fas fa-tags"></i>
            </div>
            <h2 class="section-title">按用例标签对比</h2>
          </div>
          <div class="section-content">
            <CaseTagComparisonComponent :reportData="report" />
          </div>
        </div>

        <div class="report-section" id="section-case" ref="caseRef">
          <div class="section-header">
            <div class="section-icon case">
              <i class="fas fa-list-check"></i>
            </div>
            <h2 class="section-title">具体用例对比</h2>
          </div>
          <div class="section-content">
            <SpecificCaseComparisonComponent :reportData="report" />
          </div>
        </div>
      </div>

      <div class="report-nav-sidebar">
        <div class="nav-sidebar-inner">
          <div class="nav-title">快速导航</div>
          <nav class="nav-menu">
            <a 
              v-for="item in navItems" 
              :key="item.id"
              :href="'#' + item.id"
              :class="['nav-item', { active: activeSection === item.id }]"
              @click.prevent="scrollToSection(item.id)"
            >
              <div class="nav-icon" :class="item.iconClass">
                <i :class="item.icon"></i>
              </div>
              <span class="nav-label">{{ item.label }}</span>
              <div class="nav-indicator" v-if="activeSection === item.id"></div>
            </a>
          </nav>
          <div class="nav-progress">
            <div class="progress-bar" :style="{ height: progressHeight }"></div>
          </div>
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
  report: {
    type: Object, required: true
  },
  isEditingReport: {
    type: Boolean, default: false
  },
  isEditingConclusion: {
    type: Boolean, default: false
  },
  analysisContent: {
    type: String, default: ''
  },
  tables: {
    type: Array, default: () => []
  }
})

const emit = defineEmits(['toggle-edit', 'save-report', 'cancel-edit', 'toggle-conclusion-edit', 'save-conclusion', 'cancel-conclusion'])

const editableConclusion = ref('')
const localIsEditing = ref(false)
const activeSection = ref('section-overview')
const progressHeight = ref('0%')

const navItems = [
  { id: 'section-overview', label: '概览', icon: 'fas fa-chart-pie', iconClass: 'overview' },
  { id: 'section-analysis', label: '分析结论', icon: 'fas fa-lightbulb', iconClass: 'analysis' },
  { id: 'section-category', label: '用例分组', icon: 'fas fa-layer-group', iconClass: 'category' },
  { id: 'section-tag', label: '用例标签', icon: 'fas fa-tags', iconClass: 'tag' },
  { id: 'section-case', label: '具体用例', icon: 'fas fa-list-check', iconClass: 'case' },
]

const formatDate = (dateStr) => {
  if (!dateStr) return '未知日期'
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
    const offset = 100
    const elementPosition = element.getBoundingClientRect().top
    const offsetPosition = elementPosition + window.pageYOffset - offset
    window.scrollTo({
      top: offsetPosition,
      behavior: 'smooth'
    })
  }
}

const handleScroll = () => {
  const sections = navItems.map(item => ({
    id: item.id,
    element: document.getElementById(item.id)
  }))
  
  let currentSection = 'section-overview'
  const scrollPosition = window.scrollY + 150
  
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
  background: #f8fafc;
}

.report-layout {
  display: flex;
  max-width: 1400px;
  margin: 0 auto;
  gap: 24px;
  padding: 24px;
}

.report-main {
  flex: 1;
  min-width: 0;
}

.report-nav-sidebar {
  width: 200px;
  flex-shrink: 0;
  position: sticky;
  top: 80px;
  height: fit-content;
  align-self: flex-start;
}

.nav-sidebar-inner {
  background: white;
  border-radius: 16px;
  padding: 20px 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;
}

.nav-title {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 16px;
  padding-left: 4px;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  text-decoration: none;
  color: #64748b;
  transition: all 0.2s ease;
  position: relative;
  cursor: pointer;
}

.nav-item:hover {
  background: #f1f5f9;
  color: #334155;
}

.nav-item.active {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #1e40af;
}

.nav-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  background: #f1f5f9;
  color: #64748b;
  transition: all 0.2s ease;
}

.nav-item.active .nav-icon {
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.nav-icon.overview { background: #f0fdf4; color: #22c55e; }
.nav-icon.analysis { background: #fef3c7; color: #f59e0b; }
.nav-icon.category { background: #eff6ff; color: #3b82f6; }
.nav-icon.tag { background: #fdf4ff; color: #a855f7; }
.nav-icon.case { background: #fff1f2; color: #ef4444; }

.nav-item.active .nav-icon.overview { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; }
.nav-item.active .nav-icon.analysis { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; }
.nav-item.active .nav-icon.category { background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: white; }
.nav-item.active .nav-icon.tag { background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); color: white; }
.nav-item.active .nav-icon.case { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; }

.nav-label {
  font-size: 13px;
  font-weight: 500;
  flex: 1;
}

.nav-indicator {
  width: 3px;
  height: 20px;
  background: linear-gradient(180deg, #3b82f6 0%, #1d4ed8 100%);
  border-radius: 2px;
  position: absolute;
  right: 0;
}

.nav-progress {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #e2e8f0;
  border-radius: 0 2px 2px 0;
}

.progress-bar {
  width: 100%;
  background: linear-gradient(180deg, #3b82f6 0%, #1d4ed8 100%);
  border-radius: 0 2px 2px 0;
  transition: height 0.1s ease;
}

.report-header-section {
  background: white;
  border-radius: 20px;
  padding: 32px;
  margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}

.report-header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.report-title-area {
  flex: 1;
}

.report-main-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 12px 0;
  line-height: 1.2;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}

.report-date {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #64748b;
}

.report-date i {
  color: #94a3b8;
}

.report-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  background: #f0fdf4;
  color: #22c55e;
}

.report-status.draft {
  background: #fef3c7;
  color: #f59e0b;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.report-actions-area {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.action-btn.primary {
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.action-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
}

.action-btn.secondary {
  background: #f1f5f9;
  color: #64748b;
}

.action-btn.secondary:hover {
  background: #e2e8f0;
  color: #334155;
}

.report-description-section {
  border-top: 1px solid #e2e8f0;
  padding-top: 20px;
}

.description-text {
  font-size: 15px;
  color: #64748b;
  line-height: 1.6;
}

.description-edit {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  transition: all 0.2s ease;
}

.edit-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.title-input {
  font-size: 18px;
  font-weight: 600;
}

.desc-input {
  resize: vertical;
  min-height: 100px;
}

.report-section {
  background: white;
  border-radius: 20px;
  margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 32px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 1px solid #e2e8f0;
}

.section-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.section-icon.overview {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
}

.section-icon.analysis {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

.section-icon.comparison {
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.section-icon.category {
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.section-icon.tag {
  background: linear-gradient(135deg, #a855f7 0%, #7c3aed 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3);
}

.section-icon.case {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.section-content {
  padding: 24px 32px;
}

.analysis-card {
  background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
  border-radius: 16px;
  padding: 24px;
  border: 1px solid #fde047;
}

.analysis-text {
  font-size: 15px;
  color: #475569;
  line-height: 1.8;
  min-height: 100px;
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
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  transition: all 0.2s ease;
}

.analysis-textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.analysis-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  justify-content: flex-end;
}

@media (max-width: 1024px) {
  .report-layout {
    flex-direction: column;
  }
  
  .report-nav-sidebar {
    width: 100%;
    position: relative;
    top: 0;
    order: -1;
  }
  
  .nav-sidebar-inner {
    padding: 16px;
  }
  
  .nav-menu {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .nav-item {
    padding: 8px 12px;
  }
  
  .nav-label {
    display: none;
  }
  
  .nav-progress {
    display: none;
  }
}

@media (max-width: 640px) {
  .report-layout {
    padding: 16px;
  }
  
  .report-header-section {
    padding: 20px;
  }
  
  .report-main-title {
    font-size: 22px;
  }
  
  .section-header {
    padding: 16px 20px;
  }
  
  .section-content {
    padding: 16px 20px;
  }
}
</style>
