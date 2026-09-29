<template>
  <div class="tasks-view">
    <!-- 页面标题 -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tasks"></i>
          测试任务记录
        </h2>
        <p class="page-description">管理和跟踪所有测试任务的进度和状态</p>
      </div>
    </section>
    
    <!-- 内容区域：三栏布局 -->
    <div class="tasks-content-wrapper">
      <!-- 统计卡片和图表的三栏布局 -->
      <div class="stats-charts-row" v-if="!showComparisonReport">
        <!-- 统计卡片 -->
        <div class="stats-panel">
          <h3>统计信息</h3>
          
          <!-- 任务数量统计 -->
            <div class="stats-cards">
              <div class="stat-card">
                <div class="stat-value">{{ totalTasks }}</div>
                <div class="stat-label">总任务数</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ pendingTasks }}</div>
                <div class="stat-label">待处理</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ queuedTasks }}</div>
                <div class="stat-label">排队中</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ inProgressTasks }}</div>
                <div class="stat-label">进行中</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ completedTasks }}</div>
                <div class="stat-label">已完成</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ failedTasks }}</div>
                <div class="stat-label">执行失败</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ deletedTasks }}</div>
                <div class="stat-label">已删除</div>
              </div>
            </div>
          
          <!-- 任务标签云 -->
          <div class="tags-section">
            <h4>任务标签</h4>
            <div class="tags-cloud" id="tags-cloud">
              <span v-for="tag in currentTags" :key="tag" class="tag-item" @click="toggleTag(tag)">
                {{ tag }}
              </span>
            </div>
            <!-- 标签分页控件 -->
            <div class="tags-pagination" id="tags-pagination">
              <button class="tag-page-btn" :disabled="tagCurrentPage === 1" @click="tagCurrentPage--">
                <i class="fas fa-chevron-left"></i>
              </button>
              <span class="tag-page-info" id="tag-page-info">第 {{ tagCurrentPage }} 页，共 {{ totalTagPages }} 页</span>
              <button class="tag-page-btn" :disabled="tagCurrentPage === totalTagPages" @click="tagCurrentPage++">
                <i class="fas fa-chevron-right"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- 任务统计图表区域 -->
        <section class="stats-charts-container">
          <!-- 任务类型分布 -->
          <div class="chart-card">
            <h3>任务类型分布</h3>
            <div class="chart-container">
              <canvas ref="taskTypeChartRef"></canvas>
            </div>
          </div>
          
          <!-- 任务完成趋势 -->
          <div class="chart-card">
            <div class="chart-header">
              <h3>任务完成趋势</h3>
              <div class="time-granularity-selector">
                <button class="time-btn" :class="{ active: isActive('day') }" @click="changeTimeGranularity('day')">日</button>
                <button class="time-btn" :class="{ active: isActive('week') }" @click="changeTimeGranularity('week')">周</button>
                <button class="time-btn" :class="{ active: isActive('month') }" @click="changeTimeGranularity('month')">月</button>
                <button class="time-btn" :class="{ active: isActive('year') }" @click="changeTimeGranularity('year')">年</button>
              </div>
            </div>
            <div class="chart-container">
              <canvas ref="taskTrendChartRef"></canvas>
            </div>
          </div>
          
          <!-- 任务状态分布 -->
          <div class="chart-card">
            <h3>任务状态分布</h3>
            <div class="chart-container">
              <canvas ref="taskStatusChartRef"></canvas>
            </div>
          </div>
        </section>
      </div>

      <!-- 筛选和排序栏（日常 / 已发布 / 合并 三大视图统一） -->
      <section class="filter-sort-section" v-if="!showComparisonReport">
        <div class="filter-row">
          <input type="text" class="search-input" placeholder="搜索任务名称、标签..." v-model="currentFilter.search" @input="applyCurrentFilter">

          <BadgeFilter
            v-if="activeTab !== 'merged'"
            :options="TYPE_OPTIONS"
            :model-value="currentFilter.type"
            all-label="全部类型"
            title="任务类型"
            @update:model-value="handleTypeFilterChange"
          />

          <BadgeFilter
            :options="currentStatusOptions"
            :model-value="currentFilter.status"
            all-label="全部状态"
            title="任务状态"
            @update:model-value="handleStatusFilterChange"
          />
        </div>

        <div class="filter-row">
          <BadgeFilter
            :options="TIME_RANGE_OPTIONS"
            :model-value="currentFilter.timeRange"
            all-label="全部时间"
            title="时间范围"
            @update:model-value="handleTimeRangeFilterChange"
          />

          <!-- 自定义时间范围 -->
          <div class="filter-item custom-time-range" v-if="currentFilter.timeRange === 'custom'">
            <div>
              <label for="start-date">开始:</label>
              <input type="date" id="task-start-date" class="date-input" v-model="currentFilter.customRange.start" @change="applyCurrentFilter">
            </div>
            <span>至</span>
            <div>
              <label for="end-date">结束:</label>
              <input type="date" id="task-end-date" class="date-input" v-model="currentFilter.customRange.end" @change="applyCurrentFilter">
            </div>
          </div>
          
          <div class="sort-options">
            <span>排序：</span>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === sortFieldKey }" @click="toggleViewSort(sortFieldKey)">
              创建时间 <i class="fas" :class="currentFilter.sort.field === sortFieldKey ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === 'status' }" @click="toggleViewSort('status')">
              状态 <i class="fas" :class="currentFilter.sort.field === 'status' ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === 'title' || currentFilter.sort.field === 'name' }" @click="toggleViewSort(activeTab === 'published' ? 'name' : 'title')">
              名称 <i class="fas" :class="(currentFilter.sort.field === 'title' || currentFilter.sort.field === 'name') ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
          </div>
        </div>
        
        <!-- 算法筛选（徽章单选，日常/已发布/合并三视图统一） -->
        <div class="filter-row">
          <AlgorithmFilter
            :options="algorithmOptions"
            :model-value="currentFilter.algorithmType"
            title="算法筛选"
            @update:model-value="handleAlgorithmFilterChange"
          />
        </div>
      </section>
      
      <!-- 任务列表 -->
      <section class="tasks-container" v-if="!showComparisonReport">
        <!-- 日常任务 / 已发布任务 Tab -->
        <div class="task-tabs">
          <button class="task-tab" :class="{ active: activeTab === 'daily' }" @click="switchTab('daily')">
            <i class="fas fa-tasks"></i> 日常任务
          </button>
          <button
            v-if="can(PermissionPoint.PUBLISHED_TASK_READ)"
            class="task-tab"
            :class="{ active: activeTab === 'published' }"
            @click="switchTab('published')"
          >
            <i class="fas fa-bookmark"></i> 已发布任务
            <span v-if="published.total > 0" class="task-tab-count">{{ published.total }}</span>
          </button>
          <button class="task-tab" :class="{ active: activeTab === 'merged' }" @click="switchTab('merged')">
            <i class="fas fa-object-group"></i> 合并任务
            <span v-if="merged.total > 0" class="task-tab-count">{{ merged.total }}</span>
          </button>
        </div>

        <template v-if="activeTab === 'daily'">
        <!-- 批量操作栏 -->
        <div class="batch-actions" v-if="selectedTasks.size > 0">
          <button class="btn-danger" @click="batchDelete">
            <i class="fas fa-trash"></i> 批量删除
          </button>
          <button v-if="can(PermissionPoint.TASK_PUBLISH)" class="btn-primary" @click="batchPublish" :disabled="published.actionLoading">
            <i class="fas fa-bookmark"></i> 发布
          </button>
          <button class="btn-primary" @click="batchCompare" :disabled="selectedTasks.size < 2">
            <i class="fas fa-exchange-alt"></i> 任务对比
          </button>
          <button class="btn-primary" @click="handleBatchMerge" :disabled="!canMerge" :title="mergeButtonTitle">
            <i class="fas fa-object-ungroup"></i> 合并任务
          </button>
          <button class="btn-primary" @click="batchRestore" :style="{ display: filters.status === 'deleted' ? 'inline-block' : 'none' }">
            <i class="fas fa-undo"></i> 批量恢复
          </button>
          <button class="btn-secondary" @click="cancelSelect">
            <i class="fas fa-times"></i> 取消选择
          </button>
        </div>
        
        <!-- 任务列表头部 -->
        <div class="task-list-header">
          <h3 class="task-list-title">任务列表</h3>
          <div class="task-actions">
            <button class="btn btn-primary" @click="createNewTask">
              <i class="fas fa-plus"></i> 创建新任务
            </button>
            <label class="btn btn-secondary select-all-btn">
              <input 
                type="checkbox" 
                class="select-all-checkbox"
                :checked="isAllSelected"
                @change="toggleSelectAll"
                @click.stop
              >
              <span>全选</span>
            </label>
          </div>
        </div>
        
        <!-- 任务列表容器 -->
        <div id="tasks-container">
          <TaskListWithPagination 
            :tasks="filteredTasks.map(task => ({
              id: task.id,
              name: task.name,
              title: task.name,
              description: task.description,
              type: task.type,
              status: task.status,
              createdAt: formatDate(task.createdAt),
              tags: task.tags,
              deviceCount: task.deviceCount,
              caseCount: task.caseCount,
              completedCases: task.completedCases,
              totalCases: task.totalCases,
              algorithmType: task.algorithmType,
              algorithmParams: task.algorithmParams
            }))"
            :is-selected="(task: any) => selectedTasks.has(task.id)"
            :show-checkbox="true"
            :show-config="false"
            :current-page="currentPage"
            :page-size="pageSize"
            :total-items="totalTasks"
            :total-pages="totalPages"
            :actions="taskActions"
            :search-query="searchTerm"
            @toggle-selection="toggleTaskSelection"
            @action="handleDailyAction"
            @name-updated="handleNameUpdated"
            @page-change="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </div>
        </template>

        <!-- 已发布任务面板 -->
        <template v-else-if="activeTab === 'published'">
          <div class="published-task-header">
            <h3 class="task-list-title">已发布任务</h3>
          </div>

          <div class="published-task-list">
            <div v-for="pt in published.items" :key="pt.id" class="published-card-wrap">
              <!-- 任务主体：复用日常任务卡片（标题/状态徽章/按钮位置/尺寸完全一致） -->
              <TaskCard
                :task="mapPublishedTask(pt)"
                :actions="publishedCardActions"
                :show-checkbox="false"
                :show-config="false"
                @action="handlePublishedCardAction"
                @name-updated="handlePublishedNameUpdated"
              />

              <!-- 版本历史（展开，发布任务专属功能） -->
              <div v-if="expandedPublishedId === pt.id" class="published-task-versions">
                <div class="published-task-versions-title">
                  <i class="fas fa-history"></i> 版本历史（共 {{ publishedDetail?.versions?.length ?? 0 }} 个版本）
                </div>
                <div v-for="v in publishedDetail?.versions || []" :key="v.id" class="published-task-version-row">
                  <span class="published-task-version-badge">v{{ v.version }}</span>
                  <span class="published-task-status" :class="v.status">{{ publishedStatusText(v.status) }}</span>
                  <span class="published-task-version-time">{{ formatDate(v.publishedAt) }}</span>
                  <span class="published-task-version-source" v-if="v.sourceTaskId">来源任务 #{{ v.sourceTaskId }}</span>
                </div>

                <!-- 来源任务（发布来源的日常任务及其已有执行数据） -->
                <div v-if="publishedSourceTaskId" class="published-task-exec-history">
                  <div class="published-task-versions-title">
                    <i class="fas fa-file-import"></i> 来源任务（发布时取自该日常任务）
                  </div>
                  <div class="published-task-version-row">
                    <span class="published-task-exec-name" :title="publishedDetail.sourceTaskName || ''">{{ publishedDetail.sourceTaskName }}</span>
                    <span class="published-task-status" :class="publishedDetail.sourceTaskStatus">{{ getStatusText(publishedDetail.sourceTaskStatus || '') }}</span>
                    <span class="published-task-version-time" v-if="publishedDetail.sourceTaskTotalCases != null">用例 {{ publishedDetail.sourceTaskCompletedCases ?? 0 }}/{{ publishedDetail.sourceTaskTotalCases }}</span>
                    <span class="published-task-version-time">{{ formatDate(publishedDetail.publishedAt) }}</span>
                    <button class="btn btn-secondary btn-sm" @click="handleDailyAction({ action: { id: 'view-details' }, task: { id: publishedSourceTaskId } })">
                      <i class="fas fa-eye"></i> 详情
                    </button>
                    <button class="btn btn-primary btn-sm" @click="handleDailyAction({ action: { id: 'view-report' }, task: { id: publishedSourceTaskId, name: publishedDetail.sourceTaskName } })">
                      <i class="fas fa-file-alt"></i> 报告
                    </button>
                  </div>
                </div>

                <!-- 冻结报告（发布时冻结的报告/执行数据/评估数据/用例日志，不可变） -->
                <div v-if="publishedDetail?.reportSnapshot" class="published-task-exec-history">
                  <div class="published-task-versions-title">
                    <i class="fas fa-file-archive"></i> 冻结报告（发布时快照 · 不可变）
                  </div>
                  <div class="published-task-version-row">
                    <span class="published-task-exec-name" :title="publishedDetail.reportSnapshot.name">{{ publishedDetail.reportSnapshot.name }}</span>
                    <span class="published-task-version-time">用例 {{ publishedDetail.reportSnapshot.summary.completedCases }}/{{ publishedDetail.reportSnapshot.summary.totalCases }}</span>
                    <span class="published-task-version-time">通过率 {{ formatPassRate(publishedDetail.reportSnapshot.summary.passRate) }}</span>
                    <button class="btn btn-primary btn-sm" @click="reportSnapshotOpen = true">
                      <i class="fas fa-eye"></i> 查看冻结报告
                    </button>
                  </div>
                </div>
                <div v-else class="published-task-exec-history">
                  <div class="published-task-versions-title">
                    <i class="fas fa-file-archive"></i> 冻结报告
                  </div>
                  <div class="published-task-version-row">
                    <span class="published-task-version-time">该版本发布时未冻结执行数据（无报告）</span>
                  </div>
                </div>

                <!-- 执行记录（冻结快照 → 执行生成的日常任务） -->
                <div v-if="(publishedDetail?.executionHistory || []).length > 0" class="published-task-exec-history">
                  <div class="published-task-versions-title">
                    <i class="fas fa-play-circle"></i> 执行记录（按冻结快照执行生成的日常任务）
                  </div>
                  <div v-for="exec in publishedDetail.executionHistory" :key="exec.taskId" class="published-task-version-row">
                    <span class="published-task-version-badge">v{{ exec.version }}</span>
                    <span class="published-task-exec-name" :title="exec.taskName">{{ exec.taskName }}</span>
                    <span class="published-task-status" :class="exec.status">{{ getStatusText(exec.status) }}</span>
                    <span class="published-task-version-time">用例 {{ exec.completedCases }}/{{ exec.totalCases }}</span>
                    <span class="published-task-version-time">{{ formatDate(exec.createdAt) }}</span>
                    <button class="btn btn-secondary btn-sm" @click="handleDailyAction({ action: { id: 'view-details' }, task: { id: exec.taskId } })">
                      <i class="fas fa-eye"></i> 详情
                    </button>
                    <button class="btn btn-primary btn-sm" @click="handleDailyAction({ action: { id: 'view-report' }, task: { id: exec.taskId, name: exec.taskName } })">
                      <i class="fas fa-file-alt"></i> 报告
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="empty-state" v-if="!published.loading && published.items.length === 0">
              <i class="fas fa-bookmark"></i>
              <p>暂无已发布任务</p>
              <p class="empty-state-hint">从日常任务列表发布，沉淀可复用、可追踪的任务资产</p>
            </div>
          </div>

          <PaginationComponent
            v-if="published.total > 0"
            :current-page="published.page"
            :page-size="published.perPage"
            :total-items="published.total"
            :total-pages="published.pages"
            @prev-page="handlePublishedPage(-1)"
            @next-page="handlePublishedPage(1)"
            @go-to-page="handlePublishedGoTo"
            @page-size-change="handlePublishedPageSize"
          />
        </template>

        <!-- 合并任务面板 -->
        <template v-else-if="activeTab === 'merged'">
          <div class="published-task-header">
            <h3 class="task-list-title">合并任务</h3>
          </div>

          <div class="published-task-list" v-if="!merged.loading">
            <div v-for="mt in merged.items" :key="mt.id" class="published-card-wrap">
              <!-- 任务主体：复用日常任务卡片（标题/状态徽章/按钮位置/尺寸完全一致） -->
              <TaskCard
                :task="mapMergedTask(mt)"
                :actions="taskActions"
                :show-checkbox="false"
                :show-config="false"
                @action="handleDailyAction"
                @name-updated="handleMergedNameUpdated"
              />

              <!-- 源任务列表（默认收起，点击标题展开，支持查看/执行/评估/报告等全部操作） -->
              <div class="merged-source-list" v-if="(mt.sourceTasks?.length ?? 0) > 0">
                <div class="merged-source-list-title" @click="toggleMergedSources(mt.id)">
                  <i class="fas fa-object-ungroup"></i> 源任务列表（{{ mt.sourceTasks.length }} 个）
                  <i class="fas merged-source-toggle" :class="expandedMergedSources.has(mt.id) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
                </div>
                <template v-if="expandedMergedSources.has(mt.id)">
                  <div v-for="src in mt.sourceTasks" :key="src.id" class="merged-source-row">
                    <div class="merged-source-row-info">
                      <span class="merged-source-row-name" :title="src.name">{{ src.name }}</span>
                      <span class="merged-source-status" :class="src.status">{{ getStatusText(src.status) }}</span>
                      <span class="merged-source-row-cases"><i class="fas fa-list-alt"></i>用例 {{ src.completedCases ?? 0 }}/{{ src.totalCases ?? 0 }}</span>
                      <span v-if="src.createdAt" class="merged-source-row-time"><i class="fas fa-calendar-alt"></i>{{ formatDate(src.createdAt) }}</span>
                    </div>
                    <div class="merged-source-row-actions">
                      <template v-for="act in taskActions" :key="act.id">
                        <button
                          v-if="!act.show || act.show(src)"
                          class="btn btn-sm"
                          :class="`btn-${act.type}`"
                          :disabled="typeof act.disabled === 'function' ? act.disabled(src) : act.disabled"
                          :title="act.title || act.label"
                          @click="handleDailyAction({ action: { id: act.id }, task: src })"
                        >
                          <i v-if="act.icon" :class="`fas ${act.icon}`"></i>
                          {{ act.label }}
                        </button>
                      </template>
                    </div>
                  </div>
                </template>
              </div>
              <div class="merged-source-list empty-source-hint" v-else>
                <div class="merged-source-row">
                  <span class="merged-source-row-cases">该合并任务暂无来源任务记录</span>
                </div>
              </div>
            </div>

            <div class="empty-state" v-if="merged.items.length === 0">
              <i class="fas fa-object-group"></i>
              <p>暂无合并任务</p>
              <p class="empty-state-hint">在任务列表勾选多个已完成任务，点击「合并任务」创建</p>
            </div>
          </div>

          <div class="loading-state" v-else>
            <div class="loading-spinner"></div>
            <p>正在加载合并任务...</p>
          </div>

          <PaginationComponent
            v-if="merged.total > 0"
            :current-page="merged.page"
            :page-size="merged.perPage"
            :total-items="merged.total"
            :total-pages="merged.pages"
            @prev-page="handleMergedPage(-1)"
            @next-page="handleMergedPage(1)"
            @go-to-page="handleMergedGoTo"
            @page-size-change="handleMergedPageSize"
          />
        </template>
      </section>
      
      <!-- 任务对比报告区域 -->
      <section class="comparison-report-container" id="task-comparison-report-container" v-if="showComparisonReport">
        <div class="comparison-header">
          <h3 class="comparison-title">任务对比报告</h3>
          <p class="comparison-subtitle">对比分析所选任务的执行情况和结果，帮助您识别系统性能瓶颈和质量问题，为后续优化提供依据。</p>
        </div>
        
        <!-- 报告保存区域 -->
        <div class="report-save-section analysis-conclusion-card">
          <!-- 图标区域 -->
          <div class="analysis-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M10 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          
          <!-- 内容区域 -->
          <div class="analysis-content">
            <!-- 标题和操作按钮 -->
            <div class="analysis-header">
              <h4 class="analysis-title">{{ reportName || '任务对比报告' }}</h4>
              <div class="analysis-status">
                <span class="status-dot"></span>
                {{ reportServiceData?.status === 'draft' ? '草稿' : '已发布' }}
              </div>
            </div>
            
            <!-- 非编辑模式下显示静态文本 -->
            <div v-if="!isEditingReport" class="analysis-text">
              <div>
                {{ reportServiceData?.description || '请输入报告描述' }}
              </div>
            </div>
            
            <!-- 编辑模式下显示输入框 -->
            <div v-else class="analysis-edit">
              <div class="edit-field">
                <label for="report-name">报告名称</label>
                <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportName">
              </div>
              <div class="edit-field">
                <label for="report-description">报告描述</label>
                <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="reportServiceData!.description"></textarea>
              </div>
            </div>
            
            <!-- 操作按钮 -->
            <div class="analysis-actions">
              <button v-if="!isEditingReport" class="btn btn-primary" @click="toggleEditReport">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn btn-primary" @click="saveComparisonReport">
                  <i class="fas fa-save"></i> 保存
                </button>
                <button class="btn btn-secondary" @click="cancelEditReport">
                  <i class="fas fa-times"></i> 取消
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <!-- 统一的设备和API选择器 -->
        <div class="comparison-selectors">
          <h4 class="selector-title">
            <i class="fas fa-list"></i> 选择要对比的设备和API
          </h4>
          <div class="selector-content">
            <div id="unified-selector">
              <div v-for="device in reportDevices" :key="device.id"
                   class="device-select-item" :class="{ 'selected': device.selected, 'api-item': device.type === 'API' }"
                   @click="toggleDeviceSelection(device.id)">
                <!-- 设备/API图标 -->
                <div class="device-icon-wrapper">
                  <i :class="device.type === '设备' ? 'fas fa-headphones' : 'fas fa-exchange-alt'"></i>
                </div>
                <!-- 名称和类型 -->
                <div class="device-info">
                  <span class="device-name">{{ device.name }}</span>
                  <span class="device-type-tag">{{ device.type }}</span>
                </div>
                <!-- 选择状态标识 -->
                <div class="selection-indicator">
                  <i class="fas fa-check-circle"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 分析结论 -->
        <div class="analysis-conclusion-card">
          <div class="analysis-icon">
            <i class="fas fa-chart-line"></i>
          </div>
          <div class="analysis-content">
            <div class="analysis-header">
              <h4 class="analysis-title">分析结论</h4>
              <div class="analysis-status" :class="reportServiceData.status">
                <span class="status-dot"></span>
                {{ reportServiceData.status === 'draft' ? '草稿' : '已发布' }}
              </div>
            </div>
            <div v-if="!isEditingConclusion" class="analysis-text" id="task-analysis-conclusion" v-html="reportConclusion"></div>
            <div v-else class="analysis-edit">
              <textarea 
                id="task-analysis-conclusion-edit" 
                class="analysis-textarea" 
                v-model="reportConclusion" 
                placeholder="请输入分析结论...">
              </textarea>
            </div>
            <div class="analysis-actions">
              <button v-if="!isEditingConclusion" class="btn btn-primary" @click="toggleEditConclusion">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn btn-primary" id="task-save-conclusion-btn" @click="saveConclusion">
                  <i class="fas fa-save"></i> 保存
                </button>
                <button class="btn btn-secondary" id="task-cancel-edit-btn" @click="cancelEditConclusion">
                  <i class="fas fa-times"></i> 取消
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <!-- 设备/API信息对比 -->
        <div class="comparison-section">
          <ComparisonTableComponent 
            title="设备/API信息对比"
            :columns="deviceApiColumns"
            :data="deviceApiComparisonData"
            :default-collapsed="true"
            :show-search="false"
          />
        </div>
        
        <!-- 用例执行数量对比 -->
        <div class="comparison-section">
          <ComparisonTableComponent 
            title="用例执行数量对比"
            :columns="caseExecutionColumns"
            :data="caseExecutionData"
            :default-collapsed="true"
            :show-search="false"
          />
        </div>
        

        
        <!-- 按用例分组对比 -->
        <div class="comparison-section">
          <caseCategoryComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
        
        <!-- 按用例标签对比 -->
        <div class="comparison-section">
          <caseTagComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
        
        <!-- 具体用例对比 -->
        <div class="comparison-section">
          <specificCaseComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
      </section>
    </div>

    <!-- 任务类型选择弹窗 -->
    <TaskTypeModal 
      v-if="isTaskTypeModalVisible"
      modalId="task-type-modal"
      @close="isTaskTypeModalVisible = false"
      @confirm="handleCreateTask"
    />

    <!-- 发布已发布任务弹窗 -->
    <PublishTaskModal
      v-if="isPublishModalVisible"
      :tasks="tasks"
      :submitting="published.actionLoading"
      :preset-source-task-id="publishPresetTaskId"
      @close="handleClosePublishModal"
      @confirm="handlePublishConfirm"
    />

    <!-- 冻结报告查看弹窗 -->
    <ReportSnapshotModal
      v-if="reportSnapshotOpen && publishedDetail?.reportSnapshot"
      :snapshot="publishedDetail.reportSnapshot"
      @close="reportSnapshotOpen = false"
    />
  </div>

  <!-- 操作按钮区域 -->
  <teleport to="#global-fixed-elements">
    <div id="floating-report-actions" v-if="showComparisonReport" style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; justify-content: center; gap: 16px; z-index: 9999; padding: 16px 24px; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); backdrop-filter: blur(10px); border: 1px solid rgba(226, 232, 240, 0.8);">
      <button class="btn btn-primary" id="keep-report-btn" @click="saveComparisonReport">
        <i class="fas fa-save"></i> 保存
      </button>
      <button class="btn btn-success" id="publish-report-btn" @click="publishComparisonReport">
        <i class="fas fa-paper-plane"></i> 发布
      </button>
      <button class="btn btn-secondary" id="close-comparison-report" @click="closeComparisonReport">
        <i class="fas fa-times"></i> 关闭对比报告
      </button>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed, reactive } from 'vue';
import { useTasks } from './TasksLogic/tasks';
import TaskListWithPagination from '../components/TaskListWithPagination.vue';
import TaskCard from '../components/TaskCard.vue';
import AlgorithmFilter from '../components/algorithm/AlgorithmFilter.vue';
import BadgeFilter from '../components/common/BadgeFilter.vue';
import PaginationComponent from '../components/common/PaginationComponent.vue';
import ComparisonTableComponent from '../components/report/ComparisonTableComponent.vue';
import CaseCategoryComparisonComponent from '../components/report/CaseCategoryComparisonComponent.vue';
import CaseTagComparisonComponent from '../components/report/CaseTagComparisonComponent.vue';
import SpecificCaseComparisonComponent from '../components/report/SpecificCaseComparisonComponent.vue';
import TaskTypeModal from './TasksLogic/TaskTypeModal.vue';
import PublishTaskModal from '../components/published-task/PublishTaskModal.vue';
import ReportSnapshotModal from '../components/published-task/ReportSnapshotModal.vue';
import { usePublishedTasks } from '../composables/usePublishedTasks';
import { useMergedTasks } from '../composables/useMergedTasks';
import { usePermissions } from '../composables/usePermissions';
import { useModalControl, MODAL_TYPES } from '../composables/useModal';
import { useNotification } from '../composables/useNotification';
import { PermissionPoint, PublishedTaskStatusText } from '../domain/enums';
import type { PublishedTaskItem } from '../domain/model/publishedTask';

const notification = useNotification();
const modalControl = useModalControl();
const { can } = usePermissions();

// 日常任务 / 已发布任务 / 合并任务 Tab
const activeTab = ref<'daily' | 'published' | 'merged'>('daily');
const published = usePublishedTasks();
const merged = useMergedTasks();
const isPublishModalVisible = ref(false);
const expandedPublishedId = ref<number | null>(null);
const publishedDetail = ref<any>(null);
const reportSnapshotOpen = ref(false);
// 卡片「发布」入口预选的源任务（弹窗打开时带入）
const publishPresetTaskId = ref<number | null>(null);

// 可发布状态（对齐后端 PUBLISHABLE_STATUSES）
const PUBLISHABLE_STATUSES = ['completed', 'failed', 'stopped', 'pending'];

/** 任务操作定义（日常任务卡片与合并任务来源行共用，保证行为一致） */
const taskActions: any[] = [
  { id: 'view-details', label: '查看详情', icon: 'fa-eye', type: 'secondary' },
  { id: 'view-report', label: '查看报告', icon: 'fa-file-alt', type: 'primary' },
  { id: 'publish', label: '发布', icon: 'fa-bookmark', type: 'primary', show: (task: any) => PUBLISHABLE_STATUSES.includes(task.status) && can(PermissionPoint.TASK_PUBLISH), disabled: (task: any) => isControlling.value.has(task.id) || published.actionLoading },
  { id: 'regenerate-report', label: '重新生成报告', icon: 'fa-sync', type: 'warning', show: (task: any) => ['completed', 'failed', 'stopped', 'paused', 'skipped', 'merged'].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'resume', label: '继续', icon: 'fa-play', type: 'secondary', show: (task: any) => ['paused', 'stopped'].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'retry', label: '重新执行', icon: 'fa-redo', type: 'success', show: (task: any) => ['pending', 'failed', 'completed', 'stopped', 'merged'].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'reevaluate', label: '重新评估', icon: 'fa-sync-alt', type: 'info', show: (task: any) => ['completed', 'failed', 'stopped', 'paused', 'skipped', 'merged'].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'delete', label: '删除', icon: 'fa-trash', type: 'danger', disabled: (task: any) => isControlling.value.has(task.id) },
];

const {
  tasks,
  filteredTasks, selectedTasks, sortConfig,
  currentPage, pageSize, totalPages,
  searchTerm, filters, customDateRange, tagCurrentPage, tagPageSize,
  showComparisonReport, isEditingConclusion,
  totalTagPages, currentTags, totalTasks, pendingTasks, queuedTasks,
  inProgressTasks, completedTasks, failedTasks, deletedTasks,
  isAllSelected, formatDate, applyFilters, handleSearch, toggleSort,
  toggleTag, toggleTaskSelection, toggleSelectAll, cancelSelect, createNewTask, handleCreateTask,
  handleTaskAction, updateTaskName, batchDelete, getStatusText,
  batchCompare, batchMerge, batchRestore, closeComparisonReport, saveComparisonReport,
  publishComparisonReport, saveConclusion, toggleEditConclusion, reevaluateTask,
  cancelEditConclusion, toggleEditReport, cancelEditReport,
  deviceApiColumns, caseExecutionColumns,
  toggleDeviceSelection, fetchTasks,
  reportService,
  isEditingReport,
  reportConclusion,
  handlePageChange,
  handlePageSizeChange,
  reportServiceData,
  reportName,
  reportDevices,
  deviceApiComparisonData,
  caseExecutionData,
  isTaskTypeModalVisible,
  currentTask,
  isControlling,
  changeTimeGranularity,
  isActive,
  createTaskTypeChart, createTaskTrendChart, createTaskStatusChart,
  updateCharts,
  // 图表refs
  taskTypeChartRef,
  taskTrendChartRef,
  taskStatusChartRef,
  // 日志相关
  taskLogs, filteredTaskLogs, taskLogSearchTerm, taskLogLevelFilter, taskLogFilter,
  refreshTaskLogs, filterTaskLogs,
  // 算法选项
  algorithmOptions,
  loadAlgorithmOptions
} = useTasks();

// ========== 三大视图统一筛选排序（日常 / 已发布 / 合并）==========

/** 日常视图状态选项（对齐原硬编码） */
const DAILY_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待执行' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'evaluating', label: '评估中' },
  { value: 'reevaluate_queued', label: '重新评估排队中' },
  { value: 'reevaluating', label: '重新评估中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '执行失败' },
  { value: 'deleted', label: '已删除' },
  { value: 'merged', label: '已合并' },
];

/** 合并视图状态选项 */
const MERGED_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'completed', label: '已完成' },
  { value: 'merged', label: '已合并' },
];

/** 任务类型选项（日常 / 发布视图） */
const TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'e2e', label: '端到端测试' },
  { value: 'api', label: 'API测试' },
];

/** 时间范围选项（三视图共用） */
const TIME_RANGE_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
];

/** 各视图筛选状态适配为统一结构（search/type/algorithmType/status/timeRange/customRange/sort），
 *  使顶部筛选排序栏在三大视图间可复用同一套控件 */
const dailyFilterState = reactive({
  get search() { return searchTerm.value; },
  set search(v: string) { searchTerm.value = v; },
  get type() { return filters.value.type; },
  set type(v: string) { filters.value.type = v; },
  get algorithmType() { return filters.value.algorithmType; },
  set algorithmType(v: string) { filters.value.algorithmType = v; },
  get status() { return filters.value.status; },
  set status(v: string) { filters.value.status = v; },
  get timeRange() { return filters.value.timeRange; },
  set timeRange(v: string) { filters.value.timeRange = v; },
  get customRange() { return customDateRange.value; },
  set customRange(v: { start: string; end: string }) { customDateRange.value = v; },
  get sort() { return sortConfig.value; },
  set sort(v: { field: string; order: string }) { sortConfig.value = v; },
});

const publishedFilterState = reactive({
  get search() { return published.filters.keyword; },
  set search(v: string) { published.filters.keyword = v; },
  get type() { return published.filters.type; },
  set type(v: string) { published.filters.type = v; },
  get algorithmType() { return published.filters.algorithmType; },
  set algorithmType(v: string) { published.filters.algorithmType = v; },
  get status() { return published.filters.status; },
  set status(v: string) { published.filters.status = v; },
  get timeRange() { return published.filters.timeRange; },
  set timeRange(v: string) { published.filters.timeRange = v; },
  get customRange() { return published.filters.customRange; },
  set customRange(v: { start: string; end: string }) { published.filters.customRange = v; },
  get sort() { return published.filters.sort; },
  set sort(v: { field: string; order: 'asc' | 'desc' }) { published.filters.sort = v; },
});

const mergedFilterState = reactive({
  get search() { return merged.filters.search; },
  set search(v: string) { merged.filters.search = v; },
  type: 'merged',
  get algorithmType() { return merged.filters.algorithmType; },
  set algorithmType(v: string) { merged.filters.algorithmType = v; },
  get status() { return merged.filters.status; },
  set status(v: string) { merged.filters.status = v; },
  get timeRange() { return merged.filters.timeRange; },
  set timeRange(v: string) { merged.filters.timeRange = v; },
  get customRange() { return merged.filters.customRange; },
  set customRange(v: { start: string; end: string }) { merged.filters.customRange = v; },
  get sort() { return merged.filters.sort; },
  set sort(v: { field: string; order: 'asc' | 'desc' }) { merged.filters.sort = v; },
});

/** 当前视图的筛选状态（筛选排序栏统一绑定） */
const currentFilter = computed(() => {
  if (activeTab.value === 'published') return publishedFilterState;
  if (activeTab.value === 'merged') return mergedFilterState;
  return dailyFilterState;
});

/** 当前视图的状态选项 */
const currentStatusOptions = computed(() => {
  if (activeTab.value === 'published') return published.statusOptions;
  if (activeTab.value === 'merged') return MERGED_STATUS_OPTIONS;
  return DAILY_STATUS_OPTIONS;
});

/** 当前视图的创建时间排序字段（发布任务用 publishedAt） */
const sortFieldKey = computed(() => (activeTab.value === 'published' ? 'publishedAt' : 'createdAt'));

/** 筛选变更：按当前视图触发对应列表拉取 */
function applyCurrentFilter() {
  if (activeTab.value === 'published') {
    published.page = 1;
    published.fetchList();
  } else if (activeTab.value === 'merged') {
    merged.apply();
  } else {
    applyFilters();
  }
}

/** 算法徽章筛选变更（单选，仅日常视图） */
function handleAlgorithmFilterChange(value: string) {
  currentFilter.value.algorithmType = value;
  applyCurrentFilter();
}

/** 排序变更：按当前视图触发对应排序 */
function toggleViewSort(field: string) {
  if (activeTab.value === 'published') {
    published.toggleSort(field);
  } else if (activeTab.value === 'merged') {
    merged.toggleSort(field);
  } else {
    toggleSort(field);
  }
}

// 监听图表容器ref变化，初始化图表
watch([taskTypeChartRef, taskTrendChartRef, taskStatusChartRef], () => {
  if (taskTypeChartRef.value && taskTrendChartRef.value && taskStatusChartRef.value) {
    updateCharts();
  }
}, { deep: true });

onMounted(async () => {
  await Promise.all([fetchTasks(), loadAlgorithmOptions()]);
  applyFilters();
  // 初始化时获取日志
  await refreshTaskLogs();
  
  // 初始化图表
  setTimeout(() => {
    if (taskTypeChartRef.value) {
      createTaskTypeChart(taskTypeChartRef.value);
    }
    if (taskTrendChartRef.value) {
      createTaskTrendChart(taskTrendChartRef.value);
    }
    if (taskStatusChartRef.value) {
      createTaskStatusChart(taskStatusChartRef.value);
    }
  }, 100);
});

const handleNameUpdated = ({ taskId, newName }: { taskId: string | number; newName: string }) => {
  console.log('[DEBUG] handleUpdateTaskName called:', { taskId, newName });
  updateTaskName(taskId, newName);
};

const MERGEABLE_STATUSES = ['completed', 'merged'];

const canMerge = computed(() => {
  if (selectedTasks.value.size < 2) return false;
  const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
  return selectedTasksArray.every(t => MERGEABLE_STATUSES.includes(t.status));
});

const mergeButtonTitle = computed(() => {
  if (selectedTasks.value.size < 2) {
    return '请至少选择两个任务进行合并';
  }
  const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
  const incompleteTasks = selectedTasksArray.filter(t => !MERGEABLE_STATUSES.includes(t.status));
  if (incompleteTasks.length > 0) {
    const names = incompleteTasks.map(t => t.name).join(', ');
    return `以下任务未完成，无法合并: ${names}`;
  }
  return '点击将选中的已完成任务合并为一个新任务';
});

// ---------- 已发布任务（Tab 化展示，权限点驱动显隐） ----------

function switchTab(tab: 'daily' | 'published' | 'merged') {
  activeTab.value = tab;
  if (tab === 'published') {
    published.fetchList();
  } else if (tab === 'merged') {
    merged.fetchList();
  }
}

function publishedStatusText(status: string): string {
  return PublishedTaskStatusText[status as keyof typeof PublishedTaskStatusText] || status;
}

function getTaskTypeText(type: string): string {
  const map: Record<string, string> = { api: 'API 测试', e2e: 'E2E 测试' };
  return map[type] || type;
}

/** 日常任务列表 action 分发：拦截「发布」走发布弹窗，其余透传原逻辑 */
function handleDailyAction(event: any) {
  if (event?.action?.id === 'publish') {
    openPublishForTask(event.task);
    return;
  }
  handleTaskAction(event);
}

/** 从卡片打开发布弹窗并预选源任务 */
function openPublishForTask(task: any) {
  publishPresetTaskId.value = task?.id ?? null;
  isPublishModalVisible.value = true;
}

/** 关闭发布弹窗（重置预选，避免下次打开残留） */
function handleClosePublishModal() {
  publishPresetTaskId.value = null;
  isPublishModalVisible.value = false;
}

/** 勾选批量发布：名称沿用源任务名，不可发布状态自动跳过 */
async function batchPublish() {
  const selected = tasks.value.filter((t: any) => selectedTasks.value.has(t.id));
  if (selected.length === 0) return;
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '批量发布',
    content: `将为选中的 ${selected.length} 个任务发布（名称沿用源任务名，不可发布状态自动跳过）。是否继续？`,
    confirmText: '发布',
    cancelText: '取消',
  });
  if (!confirmed) return;

  let successCount = 0;
  const failedNames: string[] = [];
  for (const task of selected) {
    try {
      await published.publish(task.id, task.name || task.title || `任务${task.id}`, task.description);
      successCount += 1;
    } catch (error: any) {
      failedNames.push(task.name || `#${task.id}`);
    }
  }
  if (successCount > 0) {
    notification.success(`批量发布完成：成功 ${successCount} 个${failedNames.length ? `，失败 ${failedNames.length} 个` : ''}`);
  } else {
    notification.error('批量发布失败，请确认任务状态是否可发布');
  }
  if (failedNames.length > 0) {
    console.warn('批量发布失败的任务:', failedNames);
  }
}

async function handlePublishConfirm(payload: { sourceTaskId: number; name: string; description?: string; publishReason?: string }) {
  try {
    await published.publish(payload.sourceTaskId, payload.name, payload.description, payload.publishReason);
    handleClosePublishModal();
    notification.success('已发布任务创建成功');
    activeTab.value = 'published';
    await published.fetchList();
  } catch (error: any) {
    notification.error(error?.response?.data?.message || error?.message || '发布失败，请稍后重试');
  }
}

async function handlePublishedExecute(pt: PublishedTaskItem) {
  if (pt.status === 'archived') {
    notification.warning('已归档任务禁止执行，请先创建新版本');
    return;
  }
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '执行此版本',
    content: `将按版本 v${pt.version} 的快照创建新的日常任务「${pt.name}」，创建后到任务列表启动执行。是否继续？`,
    confirmText: '创建任务',
    cancelText: '取消',
  });
  if (!confirmed) return;
  try {
    const result = await published.execute(pt.id);
    if (result?.taskId) {
      notification.success(`日常任务已创建（ID: ${result.taskId}），请到任务列表启动执行`);
      await fetchTasks();
      activeTab.value = 'daily';
    }
  } catch (error: any) {
    notification.error(error?.response?.data?.message || error?.message || '创建日常任务失败');
  }
}

async function handlePublishedArchive(pt: PublishedTaskItem) {
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '归档已发布任务',
    content: `确定归档「${pt.name}」v${pt.version} 吗？归档后不可直接执行。`,
    confirmText: '归档',
    cancelText: '取消',
    danger: true,
  });
  if (!confirmed) return;
  try {
    await published.archive(pt.id);
    notification.success('任务已归档');
  } catch (error: any) {
    notification.error(error?.response?.data?.message || error?.message || '归档失败');
  }
}

async function togglePublishedDetail(pt: PublishedTaskItem) {
  if (expandedPublishedId.value === pt.id) {
    expandedPublishedId.value = null;
    publishedDetail.value = null;
    return;
  }
  expandedPublishedId.value = pt.id;
  publishedDetail.value = await published.fetchDetail(pt.id);
}

/** 来源任务 ID（兼容旧记录 source_task_id 为空时从快照兜底） */
const publishedSourceTaskId = computed(() =>
  publishedDetail.value?.sourceTaskId ?? publishedDetail.value?.snapshotConfig?.sourceTaskId ?? null
);

/** 通过率格式化（支持 0~1 与百分比两种存储） */
function formatPassRate(val: number | null | undefined): string {
  if (val == null) return '0%';
  if (val <= 1) return `${(val * 100).toFixed(1)}%`;
  return `${Number(val).toFixed(1)}%`;
}

function handlePublishedPage(delta: number) {
  const next = published.page + delta;
  if (next < 1 || next > published.pages) return;
  published.setPage(next);
}

function handlePublishedGoTo(p: number) {
  if (p >= 1 && p <= published.pages) {
    published.setPage(p);
  }
}

function handlePublishedPageSize(size: number) {
  published.perPage = size;
  published.page = 1;
  published.fetchList();
}

// ---------- 发布 / 合并视图：复用日常任务卡片（TaskCard）----------

/** 发布任务 → TaskCard 数据结构（发布任务是资产，无执行进度，隐藏完成率） */
function mapPublishedTask(pt: any) {
  return {
    id: pt.id,
    name: pt.name,
    description: pt.description || '',
    type: pt.type,
    status: pt.status,
    createdAt: formatDate(pt.publishedAt || pt.createdAt),
    tags: [],
    versionCount: pt.versionCount ?? 1,
    hideCompletionRate: true,
  };
}

/** 合并任务 → TaskCard 数据结构（来源数并入描述，保留完整执行统计） */
function mapMergedTask(mt: any) {
  return {
    id: mt.id,
    name: mt.name,
    description: mt.description || (mt.sourceTasks?.length ? `合并自 ${mt.sourceTasks.length} 个任务` : ''),
    type: 'merged',
    status: mt.status,
    createdAt: formatDate(mt.createdAt),
    tags: mt.tags || [],
    caseCount: mt.totalCases ?? 0,
    totalCases: mt.totalCases ?? 0,
    completedCases: mt.completedCases ?? 0,
  };
}

/** 发布任务专属操作（保留发布视图特殊功能） */
const publishedCardActions: any[] = [
  {
    id: 'execute-version',
    label: '执行此版本',
    icon: 'fa-play',
    type: 'primary',
    show: (task: any) => task.status !== 'archived' && can(PermissionPoint.PUBLISHED_TASK_EXECUTE),
    disabled: () => published.actionLoading,
  },
  { id: 'versions', label: '版本', icon: 'fa-history', type: 'secondary' },
  {
    id: 'archive',
    label: '归档',
    icon: 'fa-archive',
    type: 'danger',
    show: (task: any) => task.status !== 'archived' && can(PermissionPoint.PUBLISHED_TASK_ARCHIVE),
    disabled: () => published.actionLoading,
  },
];

/** 发布任务卡片 action 分发 */
function handlePublishedCardAction(event: any) {
  const { action, task } = event;
  const pt = published.items.find((p: any) => p.id === task.id);
  if (!pt) return;
  switch (action.id) {
    case 'execute-version':
      handlePublishedExecute(pt);
      break;
    case 'versions':
      togglePublishedDetail(pt);
      break;
    case 'archive':
      handlePublishedArchive(pt);
      break;
  }
}

/** 发布任务重命名（作用于整个版本链） */
async function handlePublishedNameUpdated({ taskId, newName }: { taskId: string | number; newName: string }) {
  try {
    await published.rename(Number(taskId), newName);
    notification.success('任务名称已更新');
  } catch (error: any) {
    notification.error(error?.response?.data?.message || error?.message || '更新任务名称失败');
  }
}

/** 合并任务重命名（复用日常任务重命名接口） */
async function handleMergedNameUpdated({ taskId, newName }: { taskId: string | number; newName: string }) {
  try {
    await updateTaskName(taskId, newName);
    merged.refresh();
  } catch (error: any) {
    notification.error(error?.response?.data?.message || error?.message || '更新任务名称失败');
  }
}

// ---------- 合并任务（Tab 化展示） ----------

/** 源任务列表展开状态（默认收起） */
const expandedMergedSources = ref<Set<number>>(new Set());

function toggleMergedSources(id: number) {
  const next = new Set(expandedMergedSources.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedMergedSources.value = next;
}

function handleMergedPage(delta: number) {
  const next = merged.page + delta;
  if (next < 1 || next > merged.pages) return;
  merged.setPage(next);
}

function handleMergedGoTo(p: number) {
  if (p >= 1 && p <= merged.pages) {
    merged.setPage(p);
  }
}

function handleMergedPageSize(size: number) {
  merged.setPageSize(size);
}

/** 合并成功后同步刷新合并任务列表 */
async function handleBatchMerge() {
  await batchMerge();
  if (activeTab.value === 'merged') {
    merged.refresh();
  }
}
</script>

<style scoped>
/* 只导入主样式文件，所有组件样式已包含在main.css中 */
@import '../assets/styles/main.css';

/* 日常任务 / 已发布任务 Tab */
.task-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 12px;
}

.task-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: 1px solid #e2e8f0;
  border-radius: 8px 8px 0 0;
  background: #f8fafc;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border-bottom: none;
}

.task-tab:hover {
  background: #f1f5f9;
  color: #334155;
}

.task-tab.active {
  background: #fff;
  color: #FF6A00;
  border-color: #FF6A00;
  box-shadow: 0 -2px 0 0 #FF6A00 inset;
  font-weight: 600;
}

.task-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  background: #ff6a00;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

/* 已发布任务面板 */
.published-task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.published-task-list {
  display: flex;
  flex-direction: column;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.published-task-versions {
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px dashed #e2e8f0;
}

.published-task-exec-history {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.published-task-exec-name {
  font-weight: 500;
  color: #334155;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.published-task-versions-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 10px;
}

.published-task-version-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 4px;
  border-bottom: 1px solid #eef2f7;
  font-size: 13px;
}

.published-task-version-row:last-child {
  border-bottom: none;
}

.published-task-version-time {
  color: #94a3b8;
  font-size: 12px;
}

.published-task-version-source {
  color: #94a3b8;
  font-size: 12px;
}

/* 合并任务面板 */
.merged-source-list {
  margin-top: 4px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: 8px;
}

.merged-source-list-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}

.merged-source-list-title:hover {
  color: #ff6a00;
}

.merged-source-toggle {
  margin-left: auto;
  color: #94a3b8;
  font-size: 12px;
  transition: transform 0.2s ease;
}

.merged-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 6px 4px;
  border-bottom: 1px solid #eef2f7;
}

.merged-source-row:last-child {
  border-bottom: none;
}

.merged-source-row-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1;
}

.merged-source-row-name {
  font-weight: 500;
  color: #334155;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merged-source-row-cases {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #64748b;
  font-size: 12px;
}

.merged-source-row-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #94a3b8;
  font-size: 12px;
}

.merged-source-row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.empty-source-hint .merged-source-row {
  justify-content: flex-start;
  color: #94a3b8;
  font-size: 13px;
}

.merged-source-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  background: #e2e8f0;
  color: #64748b;
  flex-shrink: 0;
}

.merged-source-status.merged {
  background: #fff7ed;
  color: #ea580c;
}

.merged-source-status.completed {
  background: #ecfdf5;
  color: #059669;
}

.merged-source-status.failed {
  background: #fee2e2;
  color: #dc2626;
}

/* 图表头部样式 */
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

/* 时间粒度选择器样式 */
.time-granularity-selector {
  display: flex;
  gap: 8px;
}

/* 时间按钮样式 */
.time-btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  outline: none;
}

/* 时间按钮悬停样式 */
.time-btn:hover {
  background: #f1f5f9;
  color: #334155;
  border-color: #cbd5e1;
}

/* 时间按钮激活样式 */
.time-btn.active {
  background: #ff6a00;
  color: white;
  border-color: #ff6a00;
}

.comparison-report-container {
  margin-top: 32px;
}

.comparison-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  align-items: center;
  text-align: center;
}

.comparison-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #2c3e50;
  background: linear-gradient(135deg, #FF6A00 0%, #FF8C40 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.comparison-subtitle {
  margin: 0;
  font-size: 15px;
  color: #7f8c8d;
  line-height: 1.5;
  max-width: 600px;
}

.report-save-section {
  background: linear-gradient(to right, #e6f7ff, #ffffff);
  border: 1px solid #91d5ff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.analysis-icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  background: white;
}

.analysis-content {
  flex: 1;
}

.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.analysis-title {
  margin: 0;
  color: #0050b3;
  font-size: 1.1rem;
  font-weight: 600;
}

.analysis-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
  background-color: #f0f9ff;
  color: #0ea5e9;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #0ea5e9;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(14, 165, 233, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0); }
}

.analysis-text {
  color: #333;
  line-height: 1.6;
  font-size: 0.95rem;
  padding: 0;
  transition: all 0.3s ease;
}

.analysis-edit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.edit-field label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #475569;
}

.edit-field input, .edit-field textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 0.95rem;
  line-height: 1.6;
  transition: all 0.3s ease;
}

.analysis-actions {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
  align-items: center;
}

.comparison-selectors {
  margin-bottom: 24px;
}

.selector-title {
  margin-bottom: 16px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.selector-content {
  background: #ffffff;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

#unified-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.device-select-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  width: 130px;
  height: 150px;
  position: relative;
  overflow: hidden;
}

.device-select-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: #cbd5e1;
}

.device-select-item.selected {
  border-color: #FF6A00;
  background-color: #fffaf0;
}

.device-select-item.api-item.selected {
  border-color: #1677FF;
  background-color: #f0f7ff;
}

.device-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #f8fafc;
  transition: all 0.3s ease;
}

.device-select-item.selected .device-icon-wrapper {
  background: rgba(255, 106, 0, 0.1);
}

.device-select-item.api-item.selected .device-icon-wrapper {
  background: rgba(22, 119, 255, 0.1);
}

.device-icon-wrapper i {
  font-size: 24px;
  color: #64748b;
}

.device-select-item.selected .device-icon-wrapper i {
  color: #FF6A00;
}

.device-select-item.api-item.selected .device-icon-wrapper i {
  color: #1677FF;
}

.device-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.device-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #1e293b;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.device-type-tag {
  font-size: 0.75rem;
  color: #64748b;
  padding: 2px 8px;
  background: #f1f5f9;
  border-radius: 10px;
}

.selection-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transform: scale(0.5);
  transition: all 0.3s ease;
}

.device-select-item.selected .selection-indicator {
  opacity: 1;
  transform: scale(1);
}

.selection-indicator i {
  font-size: 18px;
  color: #FF6A00;
}

.device-select-item.api-item.selected .selection-indicator i {
  color: #1677FF;
}
.analysis-conclusion-card {
  background: linear-gradient(to right, #e6f7ff, #ffffff);
  border: 1px solid #91d5ff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 32px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.selector-hint {
  margin-top: 16px;
  font-size: 14px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-hint i {
  color: #60a5fa;
}

.comparison-section {
  margin-bottom: 24px;
}

/* 日志区域样式 */
.logs-section {
  margin-top: 32px;
}

.logs-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background-color: #f8fafc;
}

.log-item {
  margin-bottom: 12px;
  padding: 16px;
  background: white;
  border-radius: 8px;
  border-left: 4px solid #64748b;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.log-item:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.log-item.debug {
  border-left-color: #64748b;
}

.log-item.info {
  border-left-color: #3b82f6;
}

.log-item.warning {
  border-left-color: #f59e0b;
}

.log-item.error {
  border-left-color: #ef4444;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.log-time {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.log-level {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 12px;
  background-color: #f1f5f9;
}

.log-item.debug .log-level {
  color: #64748b;
  background-color: #f1f5f9;
}

.log-item.info .log-level {
  color: #3b82f6;
  background-color: #dbeafe;
}

.log-item.warning .log-level {
  color: #f59e0b;
  background-color: #fef3c7;
}

.log-item.error .log-level {
  color: #ef4444;
  background-color: #fee2e2;
}

.log-content {
  font-size: 14px;
  color: #334155;
  margin-bottom: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.log-meta {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.log-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.log-meta i {
  font-size: 10px;
}

.empty-logs {
  text-align: center;
  color: #64748b;
  padding: 40px 0;
}

.empty-logs i {
  font-size: 32px;
  margin-bottom: 12px;
  display: block;
  color: #cbd5e1;
}

.logs-filter {
  margin-bottom: 16px;
}

.logs-filter .filter-row {
  margin-top: 12px;
  gap: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.logs-filter .search-input {
  width: 100%;
  max-width: 400px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.3s ease;
}

.logs-filter .search-input:focus {
  outline: none;
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}

.logs-filter .filter-select {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  background-color: white;
  color: #334155;
  cursor: pointer;
  transition: all 0.3s ease;
}

.logs-filter .filter-select:focus {
  outline: none;
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}
</style>
