<template>
  <div class="test-execution-component">
    <h3 class="step-title">测试执行中</h3>

    <!-- INT-203：实时链路降级提示（WS 断开，HTTP 轮询兜底中） -->
    <div v-if="connectionFallback" class="conn-fallback-alert" role="alert"
      style="display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 16px; background-color: var(--warning-light); border: 1px solid var(--warning-color); border-radius: var(--radius-md); color: var(--warning-color); font-size: 14px;">
      <i class="fas fa-plug-circle-exclamation"></i>
      <span>实时连接已断开，进度已切换为 HTTP 轮询刷新（日志暂不可用），正在自动重连...</span>
    </div>

    <!-- 任务信息和进度概览 -->
    <div class="test-progress-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px;">
      <!-- 任务信息卡片 -->
      <div class="task-info-panel">
        <div class="task-basic-info" style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border);">
          <h4 style="margin: 0 0 12px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--foreground); display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-tasks" style="color: var(--primary);"></i>
            {{ testType }}测试任务
          </h4>
          <div class="task-meta" style="display: flex; gap: 20px; flex-wrap: wrap; align-items: center;">
            <div class="meta-item flex items-center gap-2">
              <i class="fas fa-clock" style="color: var(--muted-foreground); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--muted-foreground);">{{ taskInfo.testDate || new Date().toLocaleDateString() }}</span>
            </div>
            <div class="meta-item flex items-center gap-2">
              <i class="fas fa-user" style="color: var(--muted-foreground); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--muted-foreground);">{{ taskInfo.creator || '系统管理员' }}</span>
            </div>
            <!-- INT-301：任务详情头双状态徽章（执行/评估完全分离；taskStatus 兼容旧调用缺省回退） -->
            <div v-if="taskStatus" class="meta-item flex items-center gap-2">
              <span class="task-status exec-status-badge" :class="executionStatus || taskStatus" title="执行状态">
                <i class="fas task-indicator" :class="getExecutionBadgeIcon(executionStatus || taskStatus)"></i>
                {{ getExecutionStatusText(executionStatus || taskStatus) }}
              </span>
              <span v-if="evaluationStatus" class="task-status eval-status-badge" :class="evaluationStatus" title="评估状态">
                <i class="fas task-indicator" :class="getEvaluationBadgeIcon(evaluationStatus)"></i>
                {{ getEvaluationStatusText(evaluationStatus) }}
              </span>
            </div>
          </div>
        </div>
        
        <!-- 任务详细信息 -->
        <div class="task-details" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px;">
          <div v-if="taskInfo.taskName" class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-tag" style="font-size: 14px;"></i>
              任务名称
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.taskName }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-calendar-check" style="font-size: 14px;"></i>
              预计完成时间
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.expectedCompleteTime || '--' }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-hourglass-half" style="font-size: 14px;"></i>
              预计总时长
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.expectedTotalTime || '--' }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-clock" style="font-size: 14px;"></i>
              已用时长
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.usedTime || '0分钟' }}</div>
          </div>
          <div v-if="taskInfo.apiCount" class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-exchange-alt" style="font-size: 14px;"></i>
              测试API数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.apiCount }}</div>
          </div>
          <div v-if="taskInfo.deviceCount" class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-device" style="font-size: 14px;"></i>
              测试设备数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.deviceCount }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-list-check" style="font-size: 14px;"></i>
              测试用例数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.totalTestCases || 0 }}</div>
          </div>
          <div v-if="taskInfo.concurrentTasks" class="task-detail-item" style="background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted-foreground);">
              <i class="fas fa-bolt" style="font-size: 14px;"></i>
              并发数
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--foreground);">{{ taskInfo.concurrentTasks }}</div>
          </div>
        </div>
      </div>

      <!-- 进度概览卡片 -->
      <div class="progress-overview">
        <div class="progress-item" style="margin-bottom: 20px;">
          <div class="progress-label" style="font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--foreground); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-chart-line" style="color: var(--primary);"></i>
            总进度
          </div>
          <div class="progress-bar-large" style="width: 100%; height: 12px; background-color: var(--secondary); border-radius: var(--radius-full); overflow: hidden; margin-bottom: 8px;">
            <div class="progress-fill" :style="{
              width: progressInfo.totalProgress + '%',
              height: '100%',
              background: 'linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%)',
              borderBorderRadius: 'var(--radius-full)',
              transition: 'width 0.3s ease'
            }"></div>
          </div>
          <div class="progress-percentage" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--primary); text-align: center;">{{ progressInfo.totalProgress }}%</div>
          <div v-if="taskInfo.usedTime && taskInfo.expectedTotalTime" class="progress-time-info" style="text-align: center; font-size: 14px; color: var(--muted-foreground); margin-top: 8px;">
            已用时间{{ taskInfo.usedTime }} / 预计时间{{ taskInfo.expectedTotalTime }}
          </div>
        </div>
        <div class="progress-stats" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; margin-top: 20px;">
          <div class="stat-item" style="background-color: var(--success-light); padding: 16px; border-radius: var(--radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--success);">{{ progressInfo.completed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--foreground);">已完成</div>
          </div>
          <div class="stat-item" style="background-color: var(--warning-light); padding: 16px; border-radius: var(--radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--warning-color);">{{ progressInfo.inProgress }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--foreground);">进行中</div>
          </div>
          <div class="stat-item" style="background-color: var(--secondary-light); padding: 16px; border-radius: var(--radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--secondary);">{{ progressInfo.pending }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--foreground);">待执行</div>
          </div>
          <div class="stat-item" style="background-color: var(--danger-light); padding: 16px; border-radius: var(--radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--destructive);">{{ progressInfo.executionFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--foreground);">执行失败</div>
          </div>
          <div class="stat-item" style="background-color: var(--secondary-light); padding: 16px; border-radius: var(--radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--info);">{{ progressInfo.evaluationFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--foreground);">评估失败</div>
          </div>
        </div>
      </div>
    </div>

    <!-- API资源管理（仅API测试时显示） -->
    <div v-if="testType !== 'E2E' && apiResources && apiResources.length > 0" class="api-resources-section" style="margin-top: 24px; background-color: var(--background); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border);">
      <h4 style="margin: 0 0 16px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--foreground); display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-server" style="color: var(--primary);"></i>
        API资源管理
      </h4>
      <div class="api-resources-list" style="display: flex; flex-direction: column; gap: 12px;">
        <div v-for="api in apiResources" :key="api.id" class="api-resource-item" style="padding: 16px; background-color: var(--muted); border-radius: var(--radius-md); display: flex; justify-content: space-between; align-items: center;">
          <div class="resource-name" style="font-weight: 500; color: var(--foreground);">{{ api.name }}</div>
          <div class="resource-stats" style="display: flex; gap: 20px; align-items: center;">
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--muted-foreground);">当前并发:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--foreground);">{{ api.currentConcurrent || 0 }}/{{ api.maxConcurrent || 10 }}</span>
            </div>
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--muted-foreground);">队列长度:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--foreground);">{{ api.queueLength || 0 }}</span>
            </div>
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--muted-foreground);">平均响应时间:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--foreground);">{{ api.avgResponseTime || 0 }}ms</span>
            </div>
          </div>
          <div class="resource-progress" style="width: 100px;">
            <div class="progress-bar" style="width: 100%; height: 8px; background-color: var(--secondary); border-radius: var(--radius-full); overflow: hidden;">
              <div class="progress-fill" :style="{
                width: (api.currentConcurrent / (api.maxConcurrent || 10)) * 100 + '%',
                height: '100%',
                background: 'linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%)',
                borderBorderRadius: 'var(--radius-full)'
              }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 关联信息卡片 -->
    <div class="task-association-section" style="margin-top: 24px; background-color: var(--background); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border);">
      <div class="association-tabs" style="display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border);">
        <button class="tab-btn" :class="{ active: activeTab === 'cases' }" @click="$emit('update:active-tab', 'cases')" style="padding: 12px 24px; border: none; background: none; font-size: 16px; font-weight: 500; color: var(--muted-foreground); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.3s ease;">
          关联用例
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'devices' }" @click="$emit('update:active-tab', 'devices')" style="padding: 12px 24px; border: none; background: none; font-size: 16px; font-weight: 500; color: var(--muted-foreground); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.3s ease;">
          关联{{ testType === 'API' ? 'API' : '设备' }}
        </button>
      </div>
      <div class="association-content">
        <!-- 关联用例列表 -->
        <div class="associated-cases" v-show="activeTab === 'cases'" style="display: flex; flex-direction: column; gap: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
            <h5 style="margin: 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--foreground); display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-list-check" style="color: var(--primary);"></i>
              关联用例
            </h5>
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
              <!-- 视图切换 -->
              <div class="case-view-switcher" style="display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden;">
                <button class="case-view-btn" :class="{ active: caseViewMode === 'flat' }" @click="caseViewMode = 'flat'" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--muted-foreground); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-list"></i> 平铺
                </button>
                <button class="case-view-btn" :class="{ active: caseViewMode === ViewMode.TAG }" @click="caseViewMode = ViewMode.TAG" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--muted-foreground); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-tags"></i> 标签
                </button>
                <button class="case-view-btn" :class="{ active: caseViewMode === ViewMode.GROUP }" @click="caseViewMode = ViewMode.GROUP" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--muted-foreground); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-folder"></i> 分组
                </button>
              </div>
              <!-- INT-405 状态筛选：执行/评估两维独立（与双徽章同源取值，筛选值即徽章值；
                   原单值合成筛选的 9 混合项随该合成口径一并废弃。
                   「已删除」项去除：后端 TaskCaseStatus 无 deleted 值，INT-305 移除用例
                   已从进度/详情 payload 剔除，该行不可能出现，属死选项） -->
              <div class="filter-select" style="display: flex; align-items: center; gap: 6px;">
                <label style="font-size: 13px; color: var(--muted-foreground); white-space: nowrap;">执行:</label>
                <select v-model="caseFilterExecution" class="form-input" style="height: 32px; padding: 0 8px; font-size: 13px; min-width: 100px;">
                  <option value="all">全部执行</option>
                  <option v-for="opt in CASE_EXECUTION_FILTER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div class="filter-select" style="display: flex; align-items: center; gap: 6px;">
                <label style="font-size: 13px; color: var(--muted-foreground); white-space: nowrap;">评估:</label>
                <select v-model="caseFilterEvaluation" class="form-input" style="height: 32px; padding: 0 8px; font-size: 13px; min-width: 100px;">
                  <option value="all">全部评估</option>
                  <option v-for="opt in CASE_EVALUATION_FILTER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <!-- INT-796 §3.1/§3.5：查看复核历史入口 + 已复核计数（task:read） -->
              <button
                v-if="reviewCount > 0 || historyOpen"
                type="button"
                class="review-history-link"
                title="查看任务复核历史（多次复核追加不覆盖）"
                @click="historyOpen = true"
              >
                <i class="fas fa-clock-rotate-left"></i>
                查看复核历史<span v-if="reviewCount > 0">（已复核 {{ reviewCount }} 条）</span>
              </button>
            </div>
          </div>

          <!-- 平铺视图：保留虚拟滚动 -->
          <div v-if="caseViewMode === 'flat'" class="associated-items-list-container"
               ref="caseScrollContainer"
               @scroll="handleCaseScroll"
               style="max-height: 400px; overflow-y: auto; position: relative;">
            <div :style="{ height: caseTotalHeight + 'px', position: 'relative' }">
              <div :style="{ transform: `translateY(${caseOffset}px)` }">
                <div v-if="filteredAssociatedCases.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--muted-foreground);">
                  <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
                  暂无关联用例
                </div>
                <div v-for="testCase in visibleCases" :key="testCase.id" class="progress-item-small" :class="testCase.status" style="padding: 12px; border-radius: var(--radius-control); background-color: var(--muted); display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; min-height: 52px; box-sizing: border-box; cursor: pointer;" @click="handleTestCaseClick(testCase)">
                  <!-- INT-796 §3.1：批量复核勾选（终态任务 + task.result.review；点击不冒泡） -->
                  <label
                    v-if="canReview && isTerminal"
                    class="review-select"
                    style="display: inline-flex; align-items: center; margin-right: 4px; cursor: pointer;"
                    @click.stop
                  >
                    <input
                      type="checkbox"
                      class="review-select-checkbox"
                      :checked="selectedCaseIds.has(String(testCase.id))"
                      @change="toggleCaseSelect(String(testCase.id))"
                    />
                  </label>
                  <div class="progress-info" style="flex: 1; overflow: hidden;">
                    <div class="progress-name" style="font-weight: 500; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ testCase.name }}</div>
                    <div class="progress-time" style="font-size: 12px; color: var(--muted-foreground);">
                      <span v-if="testCase.duration">{{ testCase.duration }}s</span>
                    </div>
                    <div v-if="testCase.roundProgress" class="round-progress" style="display: flex; align-items: center; gap: 6px; margin-top: 2px;">
                      <span style="font-size: 11px; color: var(--muted-foreground); white-space: nowrap;">
                        第 {{ testCase.roundProgress.current }}/{{ testCase.roundProgress.total }} 轮
                      </span>
                      <div style="flex: 1; height: 3px; background: var(--border); border-radius: var(--radius-2); overflow: hidden; min-width: 40px;">
                        <div style="height: 100%; background: var(--primary); border-radius: var(--radius-2); transition: width 0.3s ease;"
                             :style="{ width: (testCase.roundProgress.current / testCase.roundProgress.total * 100) + '%' }">
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="progress-actions flex items-center gap-2">
                    <div class="progress-status flex items-center gap-2">
                      <!-- INT-405：用例级执行/评估双徽章独立展示（替代原单值合成状态；图标/文案口径同 INT-301 taskStatusBadge 单一源） -->
                      <span class="task-status exec-status-badge" :class="getCaseExecutionBadgeStatus(testCase)" :title="'执行状态'">
                        <i class="fas task-indicator" :class="getExecutionBadgeIcon(getCaseExecutionBadgeStatus(testCase))"></i>
                        {{ getExecutionStatusText(getCaseExecutionBadgeStatus(testCase)) }}
                      </span>
                      <span v-if="testCase.evaluationStatus" class="task-status eval-status-badge" :class="testCase.evaluationStatus" :title="'评估状态'">
                        <i class="fas task-indicator" :class="getCaseEvaluationBadgeIcon(testCase.evaluationStatus)"></i>
                        {{ getCaseEvaluationStatusText(testCase.evaluationStatus) }}
                      </span>
                      <!-- INT-340：人工复核标记（该用例存在复核结果） -->
                      <span v-if="testCase.reviewed" class="reviewed-badge" title="存在人工复核结果">
                        <i class="fas fa-clipboard-check"></i> 已复核
                      </span>
                    </div>
                    <!-- INT-796 §3.1：人工复核/AI复核 入口（终态任务 + 权限门控；点击不冒泡） -->
                    <button
                      v-if="canReview && isTerminal"
                      class="review-row-btn"
                      :disabled="reviewLoading"
                      :title="'人工复核该用例结果'"
                      @click.stop="openCaseReview(testCase)"
                    >
                      <i class="fas fa-clipboard-check"></i> 人工复核
                    </button>
                    <button
                      v-if="canAiReview && isTerminal"
                      class="review-row-btn review-row-btn--ai"
                      :disabled="reviewLoading"
                      :title="'AI 复核该用例结果（建议层，不直接修改统计）'"
                      @click.stop="openAiReview(testCase)"
                    >
                      <i class="fas fa-sparkles"></i> AI 复核
                    </button>
                    <!-- INT-305：移除用例（执行详情模态窗四阶段全允许；点击不冒泡触发用例详情） -->
                    <button v-if="canRemoveCase"
                            class="case-remove-btn"
                            :title="'移除用例'"
                            style="border: none; background: transparent; cursor: pointer; padding: 4px 6px; color: var(--muted-foreground); transition: color 0.2s;"
                            @click.stop="handleRemoveCaseClick(testCase)">
                      <i class="fas fa-trash-alt"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 标签视图 / 分组视图 -->
          <div v-else class="associated-items-list-container" style="max-height: 400px; overflow-y: auto; position: relative;">
            <div v-if="filteredAssociatedCases.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--muted-foreground);">
              <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
              暂无关联用例
            </div>
            <div v-for="(cases, key) in (caseViewMode === ViewMode.TAG ? groupedCasesByTag : groupedCasesByGroupName)" :key="key" class="case-group-card" style="background-color: var(--muted); border-radius: var(--radius-md); margin-bottom: 8px; border: 1px solid var(--border);">
              <div class="case-group-header" @click="toggleCaseGroup(key)" style="padding: 10px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <i class="fas fa-chevron-down" :class="{ expanded: expandedCaseGroups[key] }" style="font-size: 12px; transition: transform 0.2s; transform: rotate(-90deg);"></i>
                <i v-if="caseViewMode === ViewMode.TAG" class="fas fa-tag" style="color: var(--primary); font-size: 13px;"></i>
                <i v-else class="fas fa-folder" style="color: var(--primary); font-size: 13px;"></i>
                <span style="font-weight: 500; color: var(--foreground);">{{ key }}</span>
                <span style="background-color: var(--primary); color: var(--color-white); font-size: 12px; padding: 2px 8px; border-radius: var(--radius-pill); min-width: 20px; text-align: center;">{{ cases.length }}</span>
              </div>
              <div v-if="expandedCaseGroups[key]" class="case-group-content" style="padding: 0 12px 12px 12px; display: flex; flex-direction: column; gap: 2px;">
                <div v-for="testCase in cases" :key="testCase.id" class="progress-item-small" :class="testCase.status" style="padding: 10px; border-radius: var(--radius-control); background-color: var(--background); display: flex; justify-content: space-between; align-items: center; min-height: 48px; box-sizing: border-box; cursor: pointer;" @click="handleTestCaseClick(testCase)">
                  <!-- INT-796 §3.1：批量复核勾选（标签/分组视图同款） -->
                  <label
                    v-if="canReview && isTerminal"
                    class="review-select"
                    style="display: inline-flex; align-items: center; margin-right: 4px; cursor: pointer;"
                    @click.stop
                  >
                    <input
                      type="checkbox"
                      class="review-select-checkbox"
                      :checked="selectedCaseIds.has(String(testCase.id))"
                      @change="toggleCaseSelect(String(testCase.id))"
                    />
                  </label>
                  <div class="progress-info" style="flex: 1; overflow: hidden;">
                    <div class="progress-name" style="font-weight: 500; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ testCase.name }}</div>
                    <div class="progress-time" style="font-size: 12px; color: var(--muted-foreground);">
                      <span v-if="testCase.duration">{{ testCase.duration }}s</span>
                    </div>
                    <div v-if="testCase.roundProgress" class="round-progress" style="display: flex; align-items: center; gap: 6px; margin-top: 2px;">
                      <span style="font-size: 11px; color: var(--muted-foreground); white-space: nowrap;">
                        第 {{ testCase.roundProgress.current }}/{{ testCase.roundProgress.total }} 轮
                      </span>
                      <div style="flex: 1; height: 3px; background: var(--border); border-radius: var(--radius-2); overflow: hidden; min-width: 40px;">
                        <div style="height: 100%; background: var(--primary); border-radius: var(--radius-2); transition: width 0.3s ease;"
                             :style="{ width: (testCase.roundProgress.current / testCase.roundProgress.total * 100) + '%' }">
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="progress-status flex items-center gap-2">
                    <!-- INT-405：用例级执行/评估双徽章独立展示（同平铺视图口径） -->
                    <span class="task-status exec-status-badge" :class="getCaseExecutionBadgeStatus(testCase)" :title="'执行状态'">
                      <i class="fas task-indicator" :class="getExecutionBadgeIcon(getCaseExecutionBadgeStatus(testCase))"></i>
                      {{ getExecutionStatusText(getCaseExecutionBadgeStatus(testCase)) }}
                    </span>
                    <span v-if="testCase.evaluationStatus" class="task-status eval-status-badge" :class="testCase.evaluationStatus" :title="'评估状态'">
                      <i class="fas task-indicator" :class="getCaseEvaluationBadgeIcon(testCase.evaluationStatus)"></i>
                      {{ getCaseEvaluationStatusText(testCase.evaluationStatus) }}
                    </span>
                    <!-- INT-796 §3.1：人工复核/AI复核 入口（标签/分组视图同款） -->
                    <button
                      v-if="canReview && isTerminal"
                      class="review-row-btn"
                      :disabled="reviewLoading"
                      :title="'人工复核该用例结果'"
                      @click.stop="openCaseReview(testCase)"
                    >
                      <i class="fas fa-clipboard-check"></i> 人工复核
                    </button>
                    <button
                      v-if="canAiReview && isTerminal"
                      class="review-row-btn review-row-btn--ai"
                      :disabled="reviewLoading"
                      :title="'AI 复核该用例结果（建议层，不直接修改统计）'"
                      @click.stop="openAiReview(testCase)"
                    >
                      <i class="fas fa-sparkles"></i> AI 复核
                    </button>
                    <!-- INT-305：标签/分组视图同款移除入口 -->
                    <button v-if="canRemoveCase"
                            class="case-remove-btn"
                            :title="'移除用例'"
                            style="border: none; background: transparent; cursor: pointer; padding: 4px 6px; color: var(--muted-foreground); transition: color 0.2s;"
                            @click.stop="handleRemoveCaseClick(testCase)">
                      <i class="fas fa-trash-alt"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 关联设备/API列表 -->
        <div class="associated-devices" v-show="activeTab === 'devices'" style="display: flex; flex-direction: column; gap: 12px;">
          <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--foreground); display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-{{ testType === 'API' ? 'server' : 'mobile-alt' }}" style="color: var(--primary);"></i>
        关联{{ testType === 'API' ? 'API' : '设备' }}
          </h5>
          <div class="associated-items-list" style="display: flex; flex-direction: column; gap: 12px;">
            <div v-if="associatedDevices && associatedDevices.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--muted-foreground);">
              <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
              暂无关联{{ testType === 'API' ? 'API' : '设备' }}
            </div>
            <div v-for="device in associatedDevices" :key="device.id" class="associated-device-item" style="padding: 12px; border-radius: var(--radius-control); background-color: var(--muted); display: flex; justify-content: space-between; align-items: center;">
              <div class="device-info">
                <div class="device-name" style="font-weight: 500; margin-bottom: 4px;">{{ device.name }}</div>
                <div class="device-status" :class="`status-${device.status}`" style="font-size: 12px;">
                  <i class="fas fa-circle" :class="device.status === DeviceStatus.ONLINE ? 'online-indicator' : 'offline-indicator'" style="font-size: 8px; margin-right: 4px;"></i> {{ device.status === DeviceStatus.ONLINE ? '在线' : '离线' }}
                </div>
              </div>
              <div v-if="device.currentConcurrent !== undefined" class="device-stats" style="display: flex; align-items: center; gap: 12px;">
                <span class="stat-item" style="font-size: 14px; color: var(--muted-foreground);">当前并发{{ device.currentConcurrent }}/{{ device.maxConcurrent }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 实时日志区域 -->
    <div v-if="showLogs" class="real-time-logs" style="margin-top: 24px; background-color: var(--background); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <h4 style="margin: 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--foreground); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-file-alt" style="color: var(--primary);"></i>
          实时日志 <span style="font-size: 14px; color: var(--muted-foreground);">({{ logs.length }})</span>
        </h4>
        <button v-if="logs.length > 0" class="btn btn-secondary" @click="scrollToBottom" style="padding: 6px 12px; font-size: 12px;">
          <i class="fas fa-arrow-down"></i> 滚动到底部
        </button>
      </div>
      <div class="logs-container" 
           ref="logScrollContainer"
           @scroll="handleLogScroll"
           style="max-height: 400px; overflow-y: auto; background-color: var(--muted); padding: 16px; border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 14px; position: relative;">
        <div :style="{ height: logTotalHeight + 'px', position: 'relative' }">
          <div :style="{ transform: `translateY(${logOffset}px)` }">
            <div v-if="logs && logs.length === 0" class="no-logs-message" style="color: var(--muted-foreground); text-align: center; padding: 20px;">
              暂无日志
            </div>
            <div v-for="log in visibleLogs" :key="log.id" class="log-item" :class="log.type" style="margin-bottom: 0; display: flex; gap: 12px; height: 28px; align-items: center; white-space: nowrap;">
              <span class="log-time" style="color: var(--muted-foreground); min-width: 150px; font-size: 12px;">{{ formatLogTime(log.time) }}</span>
              <span class="log-content" style="overflow: hidden; text-overflow: ellipsis;">{{ log.content }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>



    <!-- 操作按钮区域 -->
    <div class="step-actions" style="margin-top: 32px; display: flex; gap: 12px; justify-content: flex-end;">
      <!-- INT-302：执行详情模态窗入口——重新执行/重新评估（带范围选择模态窗，事件由 TaskDetailModal 处理） -->
      <button v-if="shouldShowRetryButton" class="btn btn-success" :disabled="isControlling" @click="$emit('retryTask')">
        <i class="fas fa-redo"></i> 重新执行
      </button>
      <!-- INT-401：挑选入口权限可见性（task:cherry_pick，seed_rbac tester 已授；
           与 Tasks 头部全局购物车入口同口径，无权角色不渲染） -->
      <button v-if="shouldShowPickButton && canPickCherry" class="btn btn-info" :disabled="isControlling" @click="$emit('pickResults')">
        <i class="fas fa-shopping-cart"></i> 加入购物车
      </button>
      <button v-if="shouldShowReevaluateButton" class="btn btn-warning" :disabled="isControlling" @click="$emit('reevaluateTask')">
        <i class="fas fa-sync-alt"></i> 重新评估
      </button>
      <button v-if="shouldShowPauseResumeButton" class="btn btn-secondary" :disabled="isControlling" @click="handlePauseResumeClick">
        <i v-if="isPaused" class="fas fa-play"></i>
        <i v-else class="fas fa-pause"></i>
        {{ isPaused ? '继续' : '暂停' }}
      </button>
      <button v-if="shouldShowStopButton" class="btn btn-danger" :disabled="isControlling" @click="$emit('stopTest')">
        <i class="fas fa-stop"></i> 停止测试
      </button>
    </div>

    <!-- INT-796 §3.3：批量复核浮条（勾选多行 → 底部浮条；同一改判字段应用到全部勾选结果，逐条留痕） -->
    <Teleport to="body">
      <div v-if="canReview && isTerminal && selectedCaseIds.size > 0" class="review-batch-bar">
        <button type="button" class="review-batch-clear" title="清除选择" @click="clearCaseSelect">
          <i class="fas fa-xmark"></i>
        </button>
        <span class="review-batch-count">{{ selectedCaseIds.size }}</span>
        <span class="review-batch-text">条用例已选择</span>
        <button type="button" class="review-batch-btn" :disabled="reviewLoading" @click="openBatchReview">
          <i class="fas fa-clipboard-check"></i> 批量复核
        </button>
      </div>
    </Teleport>

    <!-- INT-796：复核历史抽屉（§3.4） -->
    <ReviewHistoryDrawer
      v-if="historyOpen"
      :task-id="props.taskId"
      :task-name="props.taskInfo?.taskName"
      :case-name-map="historyCaseNameMap"
      @close="historyOpen = false"
    />

    <!-- INT-796：AI 复核弹窗（§5.2，建议层；采纳后开人工复核弹窗预填） -->
    <AiReviewDialog
      v-if="aiReviewTarget"
      :task-id="Number(props.taskId)"
      :case-id="aiReviewTarget.caseId"
      :case-name="aiReviewTarget.caseName"
      :results="aiReviewTarget.results"
      :evaluation-status="aiReviewTarget.evaluationStatus"
      @close="aiReviewTarget = null"
      @adopt="adoptAiReviewIntoManual"
    />
  </div>
</template>

<script setup>
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/progress.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { TaskStatus, ExecutionStatus, EvaluationStatus, ViewMode, DeviceStatus, REEXECUTE_ELIGIBLE_STATUSES, PermissionPoint } from '@/domain/enums';
import { useAuthStore } from '../../store/authStore';
import { tasksApi } from '../../infrastructure/api';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import { useNotification } from '../../composables/modal/useNotification';
import AiReviewDialog from '../common/modal/AiReviewDialog.vue';
import ReviewHistoryDrawer from '../common/modal/ReviewHistoryDrawer.vue';
// INT-301 F3：双徽章图标/文案单一定义源 utils/taskStatusBadge.ts；配色单一定义源 TaskCard.css

const props = defineProps({
  testType: {type: String, default: 'API', validator: (value) => ['API', 'E2E', '混合'].includes(value)},
  taskInfo: {type: Object, default: () => ({})},
  progressInfo: {type: Object, default: () => ({
      totalProgress: 0, completed: 0, inProgress: 0, pending: 0, executionFailed: 0, evaluationFailed: 0})
  },
  apiResources: {type: Array, default: () => []},
  associatedCases: {type: Array, default: () => []},
  associatedDevices: {type: Array, default: () => []},
  testProgress: {type: Array, default: () => []},
  logs: {type: Array, default: () => []},
  showLogs: {type: Boolean, default: true},
  activeTab: {type: String, default: 'cases'},
  isPaused: {type: Boolean, default: false},
  isControlling: {type: Boolean, default: false},
  taskStatus: {type: String, default: ''},
  /** INT-301：任务级执行状态（评估推进不落此字段；缺省回退 taskStatus） */
  executionStatus: {type: String, default: ''},
  /** INT-301：任务级评估状态（pending/evaluating/completed/failed/skipped） */
  evaluationStatus: {type: String, default: ''},
  isExecuting: {type: Boolean, default: false},
  connectionFallback: {type: Boolean, default: false},
  /** INT-796：任务详情人工复核/AI复核（§3 入口；终态任务 + task.result.review 门控） */
  taskId: {type: [String, Number], default: ''}
});

const emit = defineEmits([
  'prevStep',
  'pauseTest',
  'resumeTest',
  'stopTest',
  'testCaseClick',
  'update:active-tab',
  'skipTestCase',
  'addTestCase',
  'removeTestCase',
  'loadMoreLogs',
  // INT-302：执行详情模态窗内的重执行/重评估入口（带范围选择模态窗）
  'retryTask',
  'reevaluateTask',
  // INT-339：执行详情模态窗内的挑选加购入口（CherryPickDialog 由 TaskDetailModal 承载）
  'pickResults',
  // INT-305：执行详情模态窗内的移除用例入口（四阶段全允许，确认由 TaskDetailModal 承载）
  'removeCase',
  // INT-796：人工复核提交后刷新任务详情（复核标记/统计按复核后判定重算）
  'refreshReview'
]);

// 已结束的任务状态（finished/success 为后端历史遗留状态值，暂无对应枚举）
const finishedTaskStatuses = [
  TaskStatus.COMPLETED,
  'finished',
  'success',
  TaskStatus.FAILED,
  TaskStatus.STOPPED,
];

const shouldShowPauseResumeButton = computed(() => !finishedTaskStatuses.includes(props.taskStatus));

const shouldShowStopButton = computed(() => !finishedTaskStatuses.includes(props.taskStatus));

// INT-410：重执行入口三态准入（completed/failed/stopped；pending 不允许，需先停止）。
// 与任务列表/卡片同源 REEXECUTE_ELIGIBLE_STATUSES，禁止散落字面量。
const shouldShowRetryButton = computed(() =>
  [...REEXECUTE_ELIGIBLE_STATUSES].includes(props.taskStatus));

// INT-302：重评估入口与任务卡片口径一致（终态任务可见）
const shouldShowReevaluateButton = computed(() => finishedTaskStatuses.includes(props.taskStatus));

// INT-339：挑选加购入口（终态任务可见——§10 默认仅终态任务可挑选）
const shouldShowPickButton = computed(() => finishedTaskStatuses.includes(props.taskStatus));

// INT-401：挑选入口权限可见性（task:cherry_pick；seed_rbac tester 已授，见 INT-429 benchmark
// 同型缺口先例——权限码定义 ≠ 已授，入口必须经 can() 门控）
const { hasPermission: can } = useAuthStore();
const canPickCherry = computed(() => can(PermissionPoint.TASK_CHERRY_PICK));

// ===== INT-796：任务详情人工复核 + AI复核（19 规范 §3：入口/单条批量弹窗/历史抽屉/标记统计） =====
const modalControl = useModalControl();
const notification = useNotification();

/** 终态任务（completed/failed/stopped；人工复核仅终态可改判） */
const isTerminal = computed(() => [...REEXECUTE_ELIGIBLE_STATUSES].includes(props.taskStatus));
/** 人工复核提交权限（task.result.review） */
const canReview = computed(() => can(PermissionPoint.TASK_RESULT_REVIEW));
/** AI 复核发起/查看结论（§6：task.result.review 或 evaluation:execute；AUTH_MODE=off 持 *） */
const canAiReview = computed(() => can(PermissionPoint.TASK_RESULT_REVIEW) || can('evaluation:execute'));

/** 勾选用例（批量复核选择；§3.1 底部批量浮条） */
const selectedCaseIds = ref(new Set());
const reviewLoading = ref(false);
const historyOpen = ref(false);
const reviewCount = ref(0);
const aiReviewTarget = ref(null);

const toggleCaseSelect = (caseId) => {
  const next = new Set(selectedCaseIds.value);
  if (next.has(caseId)) next.delete(caseId); else next.add(caseId);
  selectedCaseIds.value = next;
};
const clearCaseSelect = () => { selectedCaseIds.value = new Set(); };

/** 任务已复核计数（任务头「已复核 {n} 条」徽章；task:read） */
async function loadReviewCount() {
  if (!props.taskId) return;
  try {
    reviewCount.value = await tasksApi.getReviewCount(props.taskId);
  } catch (err) {
    console.error('加载复核计数失败:', err);
  }
}

/** 单条/整用例复核入口（§3.1）：取该用例结果行 → §3.2 复核弹窗（真实 result_ids 逐条留痕） */
async function openCaseReview(testCase) {
  if (!props.taskId) return;
  reviewLoading.value = true;
  try {
    const res = await tasksApi.getCaseResults(props.taskId, testCase.id);
    if (!res.results || res.results.length === 0) {
      notification.warning('该用例无执行结果，无法复核');
      return;
    }
    const results = res.results.map((r) => ({
      resultId: Number(r.id),
      executionStatus: r.executionStatus,
      evaluationStatus: undefined,
      deviceName: r.deviceName,
      apiName: r.apiName,
      reviewed: r.reviewed,
      reviewHistory: r.reviewHistory,
    }));
    const payload = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
      title: '人工复核',
      taskId: props.taskId,
      caseName: res.caseName || testCase.name,
      taskName: props.taskInfo?.taskName,
      results,
      reviewHistory: [],
      evaluationStatus: testCase.evaluationStatus || null,
    });
    if (payload) {
      await submitReview(results.map((r) => r.resultId), payload, testCase);
    }
  } catch (err) {
    console.error('加载用例结果失败:', err);
    notification.error(err?.message || '用例结果加载失败');
  } finally {
    reviewLoading.value = false;
  }
}

/** AI 复核入口（§5.2）：取该用例结果行 → AI 复核状态机弹窗 */
async function openAiReview(testCase) {
  if (!props.taskId) return;
  reviewLoading.value = true;
  try {
    const res = await tasksApi.getCaseResults(props.taskId, testCase.id);
    if (!res.results || res.results.length === 0) {
      notification.warning('该用例无执行结果，无法复核');
      return;
    }
    aiReviewTarget.value = {
      caseId: String(testCase.id),
      caseName: res.caseName || testCase.name,
      results: res.results,
      evaluationStatus: testCase.evaluationStatus || null,
    };
  } catch (err) {
    console.error('加载用例结果失败:', err);
    notification.error(err?.message || '用例结果加载失败');
  } finally {
    reviewLoading.value = false;
  }
}

/** 批量复核入口（§3.3）：勾选多行 → 并行取各用例结果行聚合 → 批量复核弹窗 */
async function openBatchReview() {
  if (!props.taskId || selectedCaseIds.value.size === 0) return;
  reviewLoading.value = true;
  try {
    const entries = await Promise.all(
      [...selectedCaseIds.value].map(async (caseId) => {
        const c = props.associatedCases.find((x) => String(x.id) === caseId);
        const res = await tasksApi.getCaseResults(props.taskId, caseId);
        return { caseName: c?.name || res.caseName || caseId, evaluationStatus: c?.evaluationStatus || null, results: res.results };
      }),
    );
    const caseNameByResultId = {};
    const results = [];
    for (const e of entries) {
      for (const r of e.results) {
        caseNameByResultId[Number(r.id)] = e.caseName;
        results.push({
          resultId: Number(r.id),
          executionStatus: r.executionStatus,
          deviceName: r.deviceName,
          apiName: r.apiName,
          reviewed: r.reviewed,
          reviewHistory: r.reviewHistory,
        });
      }
    }
    if (results.length === 0) {
      notification.warning('所选用例均无执行结果，无法批量复核');
      return;
    }
    const payload = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
      title: '批量复核',
      taskId: props.taskId,
      caseName: '批量复核',
      caseNameByResultId,
      taskName: props.taskInfo?.taskName,
      results,
      reviewHistory: [],
    });
    if (payload) {
      await submitReview(results.map((r) => r.resultId), payload);
      clearCaseSelect();
    }
  } catch (err) {
    console.error('批量复核失败:', err);
    notification.error(err?.message || '批量复核失败，请稍后重试');
  } finally {
    reviewLoading.value = false;
  }
}

/** 提交复核（POST /tasks/results/review；成功 toast 后刷新任务详情/复核计数） */
async function submitReview(resultIds, payload, _testCase) {
  try {
    await tasksApi.reviewResults(resultIds, {
      executionStatus: payload.executionStatus,
      evaluationStatus: payload.evaluationStatus,
      comment: payload.comment,
    });
    notification.success(`复核已提交 ${resultIds.length} 条结果，结果已按复核后判定计入统计`);
    await loadReviewCount();
    emit('refreshReview');
  } catch (err) {
    console.error('人工复核提交失败:', err);
    notification.error(err?.message || '复核提交失败，请稍后重试');
  }
}

/** AI 采纳 → 打开 §3.2 复核弹窗预填（AI 判定的评估状态 + 备注=AI 理由） */
async function adoptAiReviewIntoManual(preset) {
  if (!aiReviewTarget.value) return;
  const results = aiReviewTarget.value.results.map((r) => ({
    resultId: Number(r.id),
    executionStatus: r.executionStatus,
    deviceName: r.deviceName,
    apiName: r.apiName,
    reviewed: r.reviewed,
    reviewHistory: r.reviewHistory,
  }));
  const payload = await modalControl.open(MODAL_TYPES.RESULT_REVIEW, {
    title: '人工复核',
    taskId: props.taskId,
    caseName: aiReviewTarget.value.caseName,
    taskName: props.taskInfo?.taskName,
    results,
    reviewHistory: [],
    evaluationStatus: aiReviewTarget.value.evaluationStatus,
    preset,
  });
  if (payload) {
    await submitReview(results.map((r) => r.resultId), payload);
    aiReviewTarget.value = null;
  }
}

/** 用例名映射（历史抽屉 testCaseId → 名称；从关联用例构建） */
const historyCaseNameMap = computed(() => {
  const map = {};
  for (const c of props.associatedCases || []) {
    if (c.id !== undefined && c.id !== null) map[String(c.id)] = c.name;
  }
  return map;
});

// ===== INT-305：移除用例（执行详情模态窗四阶段全允许） =====

/** 移除入口始终可见（四阶段全允许：待执行/执行中/已完成/评估完成） */
const canRemoveCase = computed(() => true);

const handleRemoveCaseClick = (testCase) => {
  emit('removeCase', { caseId: testCase.id, name: testCase.name });
};

// ===== INT-301：详情头双状态徽章（F3 收敛：图标/文案单一定义源 utils/taskStatusBadge.ts） =====
// INT-405：用例行同源于该模块（getCase* 系列按用例执行/评估两维取值）
import {
  getExecutionBadgeIcon,
  getExecutionStatusText,
  getEvaluationBadgeIcon,
  getEvaluationStatusText,
  getCaseExecutionBadgeStatus,
  getCaseEvaluationBadgeIcon,
  getCaseEvaluationStatusText,
} from '../../utils/taskStatusBadge';

const formatLogTime = (timeStr) => {
  try {
    const date = new Date(timeStr);
    if (!isNaN(date.getTime())) {
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      const seconds = String(date.getSeconds()).padStart(2, '0');
      const ms = String(date.getMilliseconds()).padStart(3, '0');
      return `${month}-${day} ${hours}:${minutes}:${seconds}.${ms}`;
    }
  } catch (e) {
    console.error('Failed to format log time:', e);
  }
  return timeStr;
};

const handlePauseResumeClick = () => {
  if (props.isPaused) {
    emit('resumeTest');
  } else {
    emit('pauseTest');
  }
};

const handleTestCaseClick = (testCase) => {
  console.log('[TestExecutionComponent] handleTestCaseClick:', testCase)
  console.log('[TestExecutionComponent] testCase.id:', testCase.id)
  emit('testCaseClick', testCase.id);
};

const caseItemHeight = 54;
const caseVisibleCount = 10;
const caseStartIndex = ref(0);
const caseScrollContainer = ref(null);

// 视图模式：'flat' 平铺 | 'tag' 标签视图 | 'group' 用例分组视图
const caseViewMode = ref('flat');
// INT-405：状态筛选按执行/评估两维独立（取值即徽章口径，见 statusOptions 单一源）
const caseFilterExecution = ref('all');
const caseFilterEvaluation = ref('all');
// 分组展开状态
const expandedCaseGroups = ref({});

const toggleCaseGroup = (key) => {
  expandedCaseGroups.value = {
    ...expandedCaseGroups.value,
    [key]: !expandedCaseGroups.value[key]
  };
};

// 将 tags 归一为字符串数组
const normalizeCaseTags = (tags) => {
  if (!tags) return [];
  if (Array.isArray(tags) && tags.length > 0 && typeof tags[0] === 'string') return tags;
  return (tags || []).map((t) => t?.name || String(t || ''));
};

/**
 * INT-405：用例执行/评估筛选选项（枚举驱动 + 徽章文案口径，对齐 INT-301 F1「展示即筛选」）。
 * - value/matches = 后端 payload 原值（shared ExecutionStatus / EvaluationStatus 词汇）；
 * - label = 行内双徽章文案（utils/taskStatusBadge 同源），保证「命中行的徽章文案 == 所选项」；
 * - 评估侧 pending/queued 徽章文案同为「待评估」（§8.3），合并为一个选项（matches 承载多值）。
 */
const CASE_EXECUTION_FILTER_OPTIONS = [
  { value: ExecutionStatus.PENDING, label: '待执行', matches: [ExecutionStatus.PENDING] },
  { value: ExecutionStatus.QUEUED, label: '排队中', matches: [ExecutionStatus.QUEUED] },
  { value: ExecutionStatus.RUNNING, label: '执行中', matches: [ExecutionStatus.RUNNING] },
  { value: ExecutionStatus.COMPLETED, label: '已完成', matches: [ExecutionStatus.COMPLETED] },
  { value: ExecutionStatus.STOPPED, label: '已停止', matches: [ExecutionStatus.STOPPED] },
  { value: ExecutionStatus.FAILED, label: '执行失败', matches: [ExecutionStatus.FAILED] },
]

const CASE_EVALUATION_FILTER_OPTIONS = [
  { value: EvaluationStatus.PENDING, label: '待评估', matches: [EvaluationStatus.PENDING, EvaluationStatus.QUEUED] },
  { value: EvaluationStatus.RUNNING, label: '评估中', matches: [EvaluationStatus.RUNNING] },
  { value: EvaluationStatus.CALCULATING, label: '计算中', matches: [EvaluationStatus.CALCULATING] },
  { value: EvaluationStatus.COMPLETED, label: '已完成', matches: [EvaluationStatus.COMPLETED] },
  { value: EvaluationStatus.STOPPED, label: '已停止', matches: [EvaluationStatus.STOPPED] },
  { value: EvaluationStatus.FAILED, label: '评估失败', matches: [EvaluationStatus.FAILED] },
]

// 按执行/评估两维筛选后的用例（'all' 维度不参与过滤，两维取交集）
const filteredAssociatedCases = computed(() => {
  const list = props.associatedCases || [];
  const execOpt = CASE_EXECUTION_FILTER_OPTIONS.find(o => o.value === caseFilterExecution.value);
  const evalOpt = CASE_EVALUATION_FILTER_OPTIONS.find(o => o.value === caseFilterEvaluation.value);
  return list.filter((c) =>
    (!execOpt || execOpt.matches.includes(c.executionStatus)) &&
    (!evalOpt || evalOpt.matches.includes(c.evaluationStatus)));
});

// 按标签分组
const groupedCasesByTag = computed(() => {
  const groups = {};
  filteredAssociatedCases.value.forEach((c) => {
    const tags = normalizeCaseTags(c.tags);
    if (tags.length === 0) {
      const key = '未分组';
      if (!groups[key]) groups[key] = [];
      groups[key].push(c);
    } else {
      tags.forEach((t) => {
        if (!groups[t]) groups[t] = [];
        groups[t].push(c);
      });
    }
  });
  return groups;
});

// 按 groupName 分组
const groupedCasesByGroupName = computed(() => {
  const groups = {};
  filteredAssociatedCases.value.forEach((c) => {
    const key = c.groupName || '未分组';
    if (!groups[key]) groups[key] = [];
    groups[key].push(c);
  });
  return groups;
});

const visibleCases = computed(() => {
  const list = filteredAssociatedCases.value;
  const start = Math.max(0, caseStartIndex.value - 5);
  const end = Math.min(list.length, caseStartIndex.value + caseVisibleCount + 5);
  return list.slice(start, end).map((item, index) => ({
    ...item,
    viewIndex: start + index
  }));
});

const caseTotalHeight = computed(() => filteredAssociatedCases.value.length * caseItemHeight);
const caseOffset = computed(() => Math.max(0, caseStartIndex.value - 5) * caseItemHeight);

// 视图或筛选变化时重置滚动位置（INT-405：筛选拆为执行/评估两维）
watch([caseViewMode, caseFilterExecution, caseFilterEvaluation], () => {
  caseStartIndex.value = 0;
  if (caseScrollContainer.value) caseScrollContainer.value.scrollTop = 0;
});

const handleCaseScroll = (e) => {
  const scrollTop = e.target.scrollTop;
  caseStartIndex.value = Math.floor(scrollTop / caseItemHeight);
};

const logItemHeight = 28;
const logVisibleCount = 20;
const logBufferSize = 15;
const logStartIndex = ref(0);
const logScrollContainer = ref(null);
const shouldAutoScroll = ref(true);
const lastLogCount = ref(0);

const visibleLogs = computed(() => {
  const start = Math.max(0, logStartIndex.value - logBufferSize);
  const end = Math.min(props.logs.length, logStartIndex.value + logVisibleCount + logBufferSize);
  return props.logs.slice(start, end).map((item, index) => ({
    ...item,
    viewIndex: start + index
  }));
});

const logTotalHeight = computed(() => props.logs.length * logItemHeight);
const logOffset = computed(() => Math.max(0, logStartIndex.value - logBufferSize) * logItemHeight);

const handleLogScroll = (e) => {
  const { scrollTop, scrollHeight, clientHeight } = e.target;
  logStartIndex.value = Math.floor(scrollTop / logItemHeight);
  
  const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
  shouldAutoScroll.value = isAtBottom;
  
  // 当滚动到距离顶部还有100px时，触发加载更多（加载历史日志）
  const nearTop = scrollTop < 100;
  if (nearTop && props.logs.length > 0) {
    emit('loadMoreLogs');
  }
};

watch(() => props.logs.length, (newCount, oldCount) => {
  if (newCount > oldCount && logScrollContainer.value) {
    if (shouldAutoScroll.value) {
      // 用户在底部，自动滚动到最新日志
      nextTick(() => {
        if (logScrollContainer.value) {
          logScrollContainer.value.scrollTop = logScrollContainer.value.scrollHeight;
        }
      });
    } else {
      // 用户不在底部（向上滚动查看历史日志）
      // 保存当前滚动位置，DOM更新后补偿新增内容的高度以保持视图稳定
      const savedScrollTop = logScrollContainer.value.scrollTop;
      const addedCount = newCount - oldCount;
      const addedHeight = addedCount * logItemHeight;
      
      nextTick(() => {
        if (logScrollContainer.value) {
          logScrollContainer.value.scrollTop = savedScrollTop + addedHeight;
        }
      });
    }
  }
  lastLogCount.value = newCount;
});

onMounted(() => {
  if (logScrollContainer.value) {
    logScrollContainer.value.scrollTop = logScrollContainer.value.scrollHeight;
  }
  // INT-796：任务头「已复核 {n} 条」计数（task:read）
  void loadReviewCount();
});

const scrollToBottom = () => {
  shouldAutoScroll.value = true;
  nextTick(() => {
    if (logScrollContainer.value) {
      logScrollContainer.value.scrollTop = logScrollContainer.value.scrollHeight;
    }
  });
};
</script>

<style scoped>

/* ===== INT-301：详情头双状态徽章（F3 收敛：配色/取值口径单一定义源
   components/task/TaskCard.css —— 本处仅保留模态窗布局所需的尺寸基座，
   取值配色与 TaskCard 同类名同值，避免两处漂移） ===== */
.exec-status-badge,
.eval-status-badge{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-lg);
  font-size: 12px;
  font-weight: 500;
  border: none;
}

/* INT-340：人工复核标记（用例存在复核结果） */
.reviewed-badge{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--radius-10);
  font-size: 11px;
  font-weight: 500;
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent);
}

/* INT-796 §3：任务详情人工复核/AI复核 交互（入口/批量浮条/历史 link） */
.review-history-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s;
}
.review-history-link:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.review-select {
  flex-shrink: 0;
}
.review-select-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary);
}
.review-row-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.review-row-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.review-row-btn--ai {
  color: var(--secondary);
}
.review-row-btn--ai:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.review-row-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.review-batch-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-lg);
}
.review-batch-clear {
  border: none;
  background: none;
  color: var(--muted-foreground);
  cursor: pointer;
  font-size: 14px;
  padding: 2px 4px;
}
.review-batch-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  padding: 0 6px;
  border-radius: var(--radius-control);
  background: var(--primary);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
}
.review-batch-text {
  font-size: 13px;
  color: var(--foreground);
}
.review-batch-btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--background);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
}
.review-batch-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.review-batch-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 取值配色与 TaskCard.css 同源同值（int-301 F2/F3 统一 tokens 口径）。
   INT-405：用例评估域比任务评估域多 queued/running/calculating/stopped 四值
   （shared EvaluationStatus），按语义并入既有色族——
   进行中（evaluating/running/calculating）=indigo；待评估（pending/queued）=amber；
   中断（stopped/skipped）=gray。 */
.eval-status-badge.evaluating,
.eval-status-badge.running,
.eval-status-badge.calculating,
.exec-status-badge.running,
.exec-status-badge.in-progress{
  background-color: var(--color-indigo-100);
  color: var(--color-indigo-600);
}

.eval-status-badge.completed,
.exec-status-badge.completed{
  background-color: var(--color-emerald-100);
  color: var(--color-emerald-600);
}

.eval-status-badge.failed,
.exec-status-badge.failed{
  background-color: var(--color-red-100);
  color: var(--color-red-600);
}

.eval-status-badge.skipped,
.eval-status-badge.stopped,
.exec-status-badge.stopped,
.exec-status-badge.skipped{
  background-color: var(--color-gray-100);
  color: var(--color-gray-500);
}

.eval-status-badge.pending,
.eval-status-badge.queued,
.exec-status-badge.pending,
.exec-status-badge.paused{
  background-color: var(--color-amber-100);
  color: var(--color-amber-600);
}

.exec-status-badge.queued{
  background-color: var(--color-sky-100);
  color: var(--color-sky-700);
}

.exec-status-badge.merged{
  background-color: var(--color-indigo-100);
  color: var(--color-indigo-600);
}

.association-content{
    padding: 24px;
    background-color: var(--background);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border);
    margin: 20px 0;
}

.association-content h5{
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--foreground);
}

.associated-items-list{
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.associated-items-list .progress-item-small{
    cursor: pointer;
    padding: 12px;
    border-radius: var(--radius-control);
    background-color: var(--muted);
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.3s ease;
}

.associated-items-list .progress-item-small:hover{
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}

.associated-items-list .progress-name{
    font-weight: 500;
    margin-bottom: 4px;
}

.associated-items-list .progress-time{
    font-size: 12px;
    color: var(--muted-foreground);
}

.associated-items-list .progress-status{
    display: flex;
    align-items: center;
    gap: 8px;
}


















/* 组件样式已内联在模板中 */

/* 视图切换按钮激活态 */
.case-view-btn.active{
  background: var(--primary, var(--secondary));
  color: var(--background);
}

.case-view-btn:hover:not(.active){
  background: var(--gray-light, var(--muted));
}

/* 分组展开图标旋转 */
.case-group-header .fa-chevron-down.expanded{
  transform: rotate(0deg);
}
</style>

<!-- INT-768 CSS-1 拆搬：API 卡片域样式由工作台/测试执行组件按需加载 -->
<style src="../../assets/styles/api-test/api-card.css"></style>
