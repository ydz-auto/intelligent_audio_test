<template>
  <div class="test-execution-component">
    <h3 class="step-title">测试执行中</h3>

    <!-- INT-203：实时链路降级提示（WS 断开，HTTP 轮询兜底中） -->
    <div v-if="connectionFallback" class="conn-fallback-alert" role="alert"
      style="display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 16px; background-color: var(--warning-light); border: 1px solid var(--warning-color); border-radius: var(--border-radius-md); color: var(--warning-color); font-size: 14px;">
      <i class="fas fa-plug-circle-exclamation"></i>
      <span>实时连接已断开，进度已切换为 HTTP 轮询刷新（日志暂不可用），正在自动重连...</span>
    </div>

    <!-- 任务信息和进度概览 -->
    <div class="test-progress-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px;">
      <!-- 任务信息卡片 -->
      <div class="task-info-panel">
        <div class="task-basic-info" style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border-color);">
          <h4 style="margin: 0 0 12px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-tasks" style="color: var(--primary-color);"></i>
            {{ testType }}测试任务
          </h4>
          <div class="task-meta" style="display: flex; gap: 20px; flex-wrap: wrap; align-items: center;">
            <div class="meta-item flex items-center gap-2">
              <i class="fas fa-clock" style="color: var(--text-secondary); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--text-secondary);">{{ taskInfo.testDate || new Date().toLocaleDateString() }}</span>
            </div>
            <div class="meta-item flex items-center gap-2">
              <i class="fas fa-user" style="color: var(--text-secondary); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--text-secondary);">{{ taskInfo.creator || '系统管理员' }}</span>
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
          <div v-if="taskInfo.taskName" class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-tag" style="font-size: 14px;"></i>
              任务名称
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.taskName }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-calendar-check" style="font-size: 14px;"></i>
              预计完成时间
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.expectedCompleteTime || '--' }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-hourglass-half" style="font-size: 14px;"></i>
              预计总时长
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.expectedTotalTime || '--' }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-clock" style="font-size: 14px;"></i>
              已用时长
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.usedTime || '0分钟' }}</div>
          </div>
          <div v-if="taskInfo.apiCount" class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-exchange-alt" style="font-size: 14px;"></i>
              测试API数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.apiCount }}</div>
          </div>
          <div v-if="taskInfo.deviceCount" class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-device" style="font-size: 14px;"></i>
              测试设备数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.deviceCount }}</div>
          </div>
          <div class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-list-check" style="font-size: 14px;"></i>
              测试用例数量
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.totalTestCases || 0 }}</div>
          </div>
          <div v-if="taskInfo.concurrentTasks" class="task-detail-item" style="background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); display: flex; flex-direction: column; gap: 8px;">
            <div class="detail-label" style="display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-secondary);">
              <i class="fas fa-bolt" style="font-size: 14px;"></i>
              并发数
            </div>
            <div class="detail-value" style="font-size: 16px; font-weight: var(--font-weight-medium); color: var(--text-primary);">{{ taskInfo.concurrentTasks }}</div>
          </div>
        </div>
      </div>

      <!-- 进度概览卡片 -->
      <div class="progress-overview">
        <div class="progress-item" style="margin-bottom: 20px;">
          <div class="progress-label" style="font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-chart-line" style="color: var(--primary-color);"></i>
            总进度
          </div>
          <div class="progress-bar-large" style="width: 100%; height: 12px; background-color: var(--secondary-color); border-radius: var(--border-radius-full); overflow: hidden; margin-bottom: 8px;">
            <div class="progress-fill" :style="{
              width: progressInfo.totalProgress + '%',
              height: '100%',
              background: 'var(--primary-gradient)',
              borderBorderRadius: 'var(--border-radius-full)',
              transition: 'width 0.3s ease'
            }"></div>
          </div>
          <div class="progress-percentage" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--primary-color); text-align: center;">{{ progressInfo.totalProgress }}%</div>
          <div v-if="taskInfo.usedTime && taskInfo.expectedTotalTime" class="progress-time-info" style="text-align: center; font-size: 14px; color: var(--text-secondary); margin-top: 8px;">
            已用时间{{ taskInfo.usedTime }} / 预计时间{{ taskInfo.expectedTotalTime }}
          </div>
        </div>
        <div class="progress-stats" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; margin-top: 20px;">
          <div class="stat-item" style="background-color: var(--success-light); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--success-color);">{{ progressInfo.completed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">已完成</div>
          </div>
          <div class="stat-item" style="background-color: var(--warning-light); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--warning-color);">{{ progressInfo.inProgress }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">进行中</div>
          </div>
          <div class="stat-item" style="background-color: var(--secondary-light); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--secondary-color);">{{ progressInfo.pending }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">待执行</div>
          </div>
          <div class="stat-item" style="background-color: var(--danger-light); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--danger-color);">{{ progressInfo.executionFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">执行失败</div>
          </div>
          <div class="stat-item" style="background-color: var(--secondary-light); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--info);">{{ progressInfo.evaluationFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">评估失败</div>
          </div>
        </div>
      </div>
    </div>

    <!-- API资源管理（仅API测试时显示） -->
    <div v-if="testType !== 'E2E' && apiResources && apiResources.length > 0" class="api-resources-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border-color);">
      <h4 style="margin: 0 0 16px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-server" style="color: var(--primary-color);"></i>
        API资源管理
      </h4>
      <div class="api-resources-list" style="display: flex; flex-direction: column; gap: 12px;">
        <div v-for="api in apiResources" :key="api.id" class="api-resource-item" style="padding: 16px; background-color: var(--background-secondary); border-radius: var(--border-radius-md); display: flex; justify-content: space-between; align-items: center;">
          <div class="resource-name" style="font-weight: 500; color: var(--text-primary);">{{ api.name }}</div>
          <div class="resource-stats" style="display: flex; gap: 20px; align-items: center;">
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--text-secondary);">当前并发:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--text-primary);">{{ api.currentConcurrent || 0 }}/{{ api.maxConcurrent || 10 }}</span>
            </div>
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--text-secondary);">队列长度:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--text-primary);">{{ api.queueLength || 0 }}</span>
            </div>
            <div class="resource-stat flex items-center gap-2">
              <span class="stat-label" style="font-size: 14px; color: var(--text-secondary);">平均响应时间:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--text-primary);">{{ api.avgResponseTime || 0 }}ms</span>
            </div>
          </div>
          <div class="resource-progress" style="width: 100px;">
            <div class="progress-bar" style="width: 100%; height: 8px; background-color: var(--secondary-color); border-radius: var(--border-radius-full); overflow: hidden;">
              <div class="progress-fill" :style="{
                width: (api.currentConcurrent / (api.maxConcurrent || 10)) * 100 + '%',
                height: '100%',
                background: 'var(--primary-gradient)',
                borderBorderRadius: 'var(--border-radius-full)'
              }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 关联信息卡片 -->
    <div class="task-association-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border-color);">
      <div class="association-tabs" style="display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color);">
        <button class="tab-btn" :class="{ active: activeTab === 'cases' }" @click="$emit('update:active-tab', 'cases')" style="padding: 12px 24px; border: none; background: none; font-size: 16px; font-weight: 500; color: var(--text-secondary); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.3s ease;">
          关联用例
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'devices' }" @click="$emit('update:active-tab', 'devices')" style="padding: 12px 24px; border: none; background: none; font-size: 16px; font-weight: 500; color: var(--text-secondary); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.3s ease;">
          关联{{ testType === 'API' ? 'API' : '设备' }}
        </button>
      </div>
      <div class="association-content">
        <!-- 关联用例列表 -->
        <div class="associated-cases" v-show="activeTab === 'cases'" style="display: flex; flex-direction: column; gap: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
            <h5 style="margin: 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-list-check" style="color: var(--primary-color);"></i>
              关联用例
            </h5>
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
              <!-- 视图切换 -->
              <div class="case-view-switcher" style="display: inline-flex; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden;">
                <button class="case-view-btn" :class="{ active: caseViewMode === 'flat' }" @click="caseViewMode = 'flat'" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-list"></i> 平铺
                </button>
                <button class="case-view-btn" :class="{ active: caseViewMode === ViewMode.TAG }" @click="caseViewMode = ViewMode.TAG" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-tags"></i> 标签
                </button>
                <button class="case-view-btn" :class="{ active: caseViewMode === ViewMode.GROUP }" @click="caseViewMode = ViewMode.GROUP" style="padding: 6px 12px; border: none; background: transparent; font-size: 13px; color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">
                  <i class="fas fa-folder"></i> 分组
                </button>
              </div>
              <!-- INT-405 状态筛选：执行/评估两维独立（与双徽章同源取值，筛选值即徽章值；
                   原单值合成筛选的 9 混合项随该合成口径一并废弃。
                   「已删除」项去除：后端 TaskCaseStatus 无 deleted 值，INT-305 移除用例
                   已从进度/详情 payload 剔除，该行不可能出现，属死选项） -->
              <div class="filter-select" style="display: flex; align-items: center; gap: 6px;">
                <label style="font-size: 13px; color: var(--text-secondary); white-space: nowrap;">执行:</label>
                <select v-model="caseFilterExecution" class="form-input" style="height: 32px; padding: 0 8px; font-size: 13px; min-width: 100px;">
                  <option value="all">全部执行</option>
                  <option v-for="opt in CASE_EXECUTION_FILTER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div class="filter-select" style="display: flex; align-items: center; gap: 6px;">
                <label style="font-size: 13px; color: var(--text-secondary); white-space: nowrap;">评估:</label>
                <select v-model="caseFilterEvaluation" class="form-input" style="height: 32px; padding: 0 8px; font-size: 13px; min-width: 100px;">
                  <option value="all">全部评估</option>
                  <option v-for="opt in CASE_EVALUATION_FILTER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 平铺视图：保留虚拟滚动 -->
          <div v-if="caseViewMode === 'flat'" class="associated-items-list-container"
               ref="caseScrollContainer"
               @scroll="handleCaseScroll"
               style="max-height: 400px; overflow-y: auto; position: relative;">
            <div :style="{ height: caseTotalHeight + 'px', position: 'relative' }">
              <div :style="{ transform: `translateY(${caseOffset}px)` }">
                <div v-if="filteredAssociatedCases.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                  <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
                  暂无关联用例
                </div>
                <div v-for="testCase in visibleCases" :key="testCase.id" class="progress-item-small" :class="testCase.status" style="padding: 12px; border-radius: 8px; background-color: var(--background-secondary); display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; min-height: 52px; box-sizing: border-box; cursor: pointer;" @click="handleTestCaseClick(testCase)">
                  <div class="progress-info" style="flex: 1; overflow: hidden;">
                    <div class="progress-name" style="font-weight: 500; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ testCase.name }}</div>
                    <div class="progress-time" style="font-size: 12px; color: var(--text-secondary);">
                      <span v-if="testCase.duration">{{ testCase.duration }}s</span>
                    </div>
                    <div v-if="testCase.roundProgress" class="round-progress" style="display: flex; align-items: center; gap: 6px; margin-top: 2px;">
                      <span style="font-size: 11px; color: var(--text-secondary); white-space: nowrap;">
                        第 {{ testCase.roundProgress.current }}/{{ testCase.roundProgress.total }} 轮
                      </span>
                      <div style="flex: 1; height: 3px; background: var(--border-color); border-radius: 2px; overflow: hidden; min-width: 40px;">
                        <div style="height: 100%; background: var(--primary-color); border-radius: 2px; transition: width 0.3s ease;"
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
                    <!-- INT-305：移除用例（执行详情模态窗四阶段全允许；点击不冒泡触发用例详情） -->
                    <button v-if="canRemoveCase"
                            class="case-remove-btn"
                            :title="'移除用例'"
                            style="border: none; background: transparent; cursor: pointer; padding: 4px 6px; color: var(--text-secondary); transition: color 0.2s;"
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
            <div v-if="filteredAssociatedCases.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--text-secondary);">
              <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
              暂无关联用例
            </div>
            <div v-for="(cases, key) in (caseViewMode === ViewMode.TAG ? groupedCasesByTag : groupedCasesByGroupName)" :key="key" class="case-group-card" style="background-color: var(--background-secondary); border-radius: var(--border-radius-md); margin-bottom: 8px; border: 1px solid var(--border-color);">
              <div class="case-group-header" @click="toggleCaseGroup(key)" style="padding: 10px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <i class="fas fa-chevron-down" :class="{ expanded: expandedCaseGroups[key] }" style="font-size: 12px; transition: transform 0.2s; transform: rotate(-90deg);"></i>
                <i v-if="caseViewMode === ViewMode.TAG" class="fas fa-tag" style="color: var(--primary-color); font-size: 13px;"></i>
                <i v-else class="fas fa-folder" style="color: var(--primary-color); font-size: 13px;"></i>
                <span style="font-weight: 500; color: var(--text-primary);">{{ key }}</span>
                <span style="background-color: var(--primary-color); color: white; font-size: 12px; padding: 2px 8px; border-radius: 12px; min-width: 20px; text-align: center;">{{ cases.length }}</span>
              </div>
              <div v-if="expandedCaseGroups[key]" class="case-group-content" style="padding: 0 12px 12px 12px; display: flex; flex-direction: column; gap: 2px;">
                <div v-for="testCase in cases" :key="testCase.id" class="progress-item-small" :class="testCase.status" style="padding: 10px; border-radius: 8px; background-color: var(--background-primary); display: flex; justify-content: space-between; align-items: center; min-height: 48px; box-sizing: border-box; cursor: pointer;" @click="handleTestCaseClick(testCase)">
                  <div class="progress-info" style="flex: 1; overflow: hidden;">
                    <div class="progress-name" style="font-weight: 500; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ testCase.name }}</div>
                    <div class="progress-time" style="font-size: 12px; color: var(--text-secondary);">
                      <span v-if="testCase.duration">{{ testCase.duration }}s</span>
                    </div>
                    <div v-if="testCase.roundProgress" class="round-progress" style="display: flex; align-items: center; gap: 6px; margin-top: 2px;">
                      <span style="font-size: 11px; color: var(--text-secondary); white-space: nowrap;">
                        第 {{ testCase.roundProgress.current }}/{{ testCase.roundProgress.total }} 轮
                      </span>
                      <div style="flex: 1; height: 3px; background: var(--border-color); border-radius: 2px; overflow: hidden; min-width: 40px;">
                        <div style="height: 100%; background: var(--primary-color); border-radius: 2px; transition: width 0.3s ease;"
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
                    <!-- INT-305：标签/分组视图同款移除入口 -->
                    <button v-if="canRemoveCase"
                            class="case-remove-btn"
                            :title="'移除用例'"
                            style="border: none; background: transparent; cursor: pointer; padding: 4px 6px; color: var(--text-secondary); transition: color 0.2s;"
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
          <h5 style="margin: 0 0 16px 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-{{ testType === 'API' ? 'server' : 'mobile-alt' }}" style="color: var(--primary-color);"></i>
        关联{{ testType === 'API' ? 'API' : '设备' }}
          </h5>
          <div class="associated-items-list" style="display: flex; flex-direction: column; gap: 12px;">
            <div v-if="associatedDevices && associatedDevices.length === 0" class="no-items-message" style="text-align: center; padding: 40px; color: var(--text-secondary);">
              <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
              暂无关联{{ testType === 'API' ? 'API' : '设备' }}
            </div>
            <div v-for="device in associatedDevices" :key="device.id" class="associated-device-item" style="padding: 12px; border-radius: 8px; background-color: var(--background-secondary); display: flex; justify-content: space-between; align-items: center;">
              <div class="device-info">
                <div class="device-name" style="font-weight: 500; margin-bottom: 4px;">{{ device.name }}</div>
                <div class="device-status" :class="`status-${device.status}`" style="font-size: 12px;">
                  <i class="fas fa-circle" :class="device.status === DeviceStatus.ONLINE ? 'online-indicator' : 'offline-indicator'" style="font-size: 8px; margin-right: 4px;"></i> {{ device.status === DeviceStatus.ONLINE ? '在线' : '离线' }}
                </div>
              </div>
              <div v-if="device.currentConcurrent !== undefined" class="device-stats" style="display: flex; align-items: center; gap: 12px;">
                <span class="stat-item" style="font-size: 14px; color: var(--text-secondary);">当前并发{{ device.currentConcurrent }}/{{ device.maxConcurrent }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 实时日志区域 -->
    <div v-if="showLogs" class="real-time-logs" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border-color);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <h4 style="margin: 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-file-alt" style="color: var(--primary-color);"></i>
          实时日志 <span style="font-size: 14px; color: var(--text-secondary);">({{ logs.length }})</span>
        </h4>
        <button v-if="logs.length > 0" class="btn btn-secondary" @click="scrollToBottom" style="padding: 6px 12px; font-size: 12px;">
          <i class="fas fa-arrow-down"></i> 滚动到底部
        </button>
      </div>
      <div class="logs-container" 
           ref="logScrollContainer"
           @scroll="handleLogScroll"
           style="max-height: 400px; overflow-y: auto; background-color: var(--background-secondary); padding: 16px; border-radius: var(--border-radius-md); font-family: var(--font-mono); font-size: 14px; position: relative;">
        <div :style="{ height: logTotalHeight + 'px', position: 'relative' }">
          <div :style="{ transform: `translateY(${logOffset}px)` }">
            <div v-if="logs && logs.length === 0" class="no-logs-message" style="color: var(--text-secondary); text-align: center; padding: 20px;">
              暂无日志
            </div>
            <div v-for="log in visibleLogs" :key="log.id" class="log-item" :class="log.type" style="margin-bottom: 0; display: flex; gap: 12px; height: 28px; align-items: center; white-space: nowrap;">
              <span class="log-time" style="color: var(--text-secondary); min-width: 150px; font-size: 12px;">{{ formatLogTime(log.time) }}</span>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { TaskStatus, ExecutionStatus, EvaluationStatus, ViewMode, DeviceStatus, REEXECUTE_ELIGIBLE_STATUSES, PermissionPoint } from '@/domain/enums';
import { useAuthStore } from '../../store/authStore';
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
  connectionFallback: {type: Boolean, default: false}
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
  'removeCase'
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

// INT-302：重执行入口与任务卡片口径一致（pending/failed/completed/stopped 可见）
const shouldShowRetryButton = computed(() =>
  [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.STOPPED].includes(props.taskStatus));

// INT-302：重评估入口与任务卡片口径一致（终态任务可见）
const shouldShowReevaluateButton = computed(() => finishedTaskStatuses.includes(props.taskStatus));

// INT-339：挑选加购入口（终态任务可见——§10 默认仅终态任务可挑选）
const shouldShowPickButton = computed(() => finishedTaskStatuses.includes(props.taskStatus));

// INT-401：挑选入口权限可见性（task:cherry_pick；seed_rbac tester 已授，见 INT-429 benchmark
// 同型缺口先例——权限码定义 ≠ 已授，入口必须经 can() 门控）
const { hasPermission: can } = useAuthStore();
const canPickCherry = computed(() => can(PermissionPoint.TASK_CHERRY_PICK));

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
  border-radius: 12px;
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
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
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
    background-color: var(--background-primary);
    border-radius: 12px;
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border-color);
    margin: 20px 0;
}

.association-content h5{
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
}

.associated-items-list{
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.associated-items-list .progress-item-small{
    cursor: pointer;
    padding: 12px;
    border-radius: 8px;
    background-color: var(--background-secondary);
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
    color: var(--text-secondary);
}

.associated-items-list .progress-status{
    display: flex;
    align-items: center;
    gap: 8px;
}


















/* 组件样式已内联在模板中 */

/* 视图切换按钮激活态 */
.case-view-btn.active{
  background: var(--primary-color, var(--secondary));
  color: var(--background);
}

.case-view-btn:hover:not(.active){
  background: var(--background-tertiary, var(--muted));
}

/* 分组展开图标旋转 */
.case-group-header .fa-chevron-down.expanded{
  transform: rotate(0deg);
}
</style>
