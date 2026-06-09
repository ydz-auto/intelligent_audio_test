<template>
  <div class="test-execution-component">
    <h3 class="step-title">测试执行中</h3>
    
    <!-- 任务信息和进度概览 -->
    <div class="test-progress-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 24px;">
      <!-- 任务信息卡片 -->
      <div class="task-info-panel">
        <div class="task-basic-info" style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border-color);">
          <h4 style="margin: 0 0 12px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            <i class="fas fa-tasks" style="color: var(--primary-color);"></i>
            {{ testType }}测试任务
          </h4>
          <div class="task-meta" style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div class="meta-item" style="display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-clock" style="color: var(--text-secondary); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--text-secondary);">{{ taskInfo.testDate || new Date().toLocaleDateString() }}</span>
            </div>
            <div class="meta-item" style="display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-user" style="color: var(--text-secondary); font-size: 14px;"></i>
              <span style="font-size: 14px; color: var(--text-secondary);">{{ taskInfo.creator || '系统管理员' }}</span>
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
          <div class="stat-item" style="background-color: var(--danger-light, rgba(255, 77, 79, 0.12)); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--danger-color, #FF4D4F);">{{ progressInfo.executionFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">执行失败</div>
          </div>
          <div class="stat-item" style="background-color: var(--info-light, rgba(22, 119, 255, 0.12)); padding: 16px; border-radius: var(--border-radius-md); text-align: center; display: flex; flex-direction: column; gap: 8px;">
            <div class="stat-value" style="font-size: 24px; font-weight: var(--font-weight-bold); color: var(--info-color, #1677FF);">{{ progressInfo.evaluationFailed }}</div>
            <div class="stat-label" style="font-size: 14px; color: var(--text-primary);">评估失败</div>
          </div>
        </div>
      </div>
    </div>

    <!-- API资源管理（仅API测试时显示） -->
    <div v-if="testType === 'API' && apiResources && apiResources.length > 0" class="api-resources-section" style="margin-top: 24px; background-color: var(--background-primary); border-radius: var(--border-radius-lg); box-shadow: var(--shadow-sm); padding: 24px; border: 1px solid var(--border-color);">
      <h4 style="margin: 0 0 16px 0; font-size: 18px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-server" style="color: var(--primary-color);"></i>
        API资源管理
      </h4>
      <div class="api-resources-list" style="display: flex; flex-direction: column; gap: 12px;">
        <div v-for="api in apiResources" :key="api.id" class="api-resource-item" style="padding: 16px; background-color: var(--background-secondary); border-radius: var(--border-radius-md); display: flex; justify-content: space-between; align-items: center;">
          <div class="resource-name" style="font-weight: 500; color: var(--text-primary);">{{ api.name }}</div>
          <div class="resource-stats" style="display: flex; gap: 20px; align-items: center;">
            <div class="resource-stat" style="display: flex; align-items: center; gap: 8px;">
              <span class="stat-label" style="font-size: 14px; color: var(--text-secondary);">当前并发:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--text-primary);">{{ api.currentConcurrent || 0 }}/{{ api.maxConcurrent || 10 }}</span>
            </div>
            <div class="resource-stat" style="display: flex; align-items: center; gap: 8px;">
              <span class="stat-label" style="font-size: 14px; color: var(--text-secondary);">队列长度:</span>
              <span class="stat-value" style="font-weight: 500; color: var(--text-primary);">{{ api.queueLength || 0 }}</span>
            </div>
            <div class="resource-stat" style="display: flex; align-items: center; gap: 8px;">
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
          <div style="margin-bottom: 16px;">
            <h5 style="margin: 0; font-size: 16px; font-weight: var(--font-weight-semibold); color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
              <i class="fas fa-list-check" style="color: var(--primary-color);"></i>
              关联用例
            </h5>
          </div>
          <div class="associated-items-list-container" 
               ref="caseScrollContainer"
               @scroll="handleCaseScroll"
               style="max-height: 400px; overflow-y: auto; position: relative;">
            <div :style="{ height: caseTotalHeight + 'px', position: 'relative' }">
              <div :style="{ transform: `translateY(${caseOffset}px)` }">
                <div v-if="associatedCases && associatedCases.length === 0 && (!testProgress || testProgress.length === 0)" class="no-items-message" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                  <i class="fas fa-info-circle" style="font-size: 24px; margin-bottom: 12px; display: block;"></i>
                  暂无关联用例
                </div>
                <div v-for="testCase in visibleCases" :key="testCase.id" class="progress-item-small" :class="testCase.status" style="padding: 12px; border-radius: 8px; background-color: var(--background-secondary); display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; height: 52px; box-sizing: border-box; cursor: pointer;" @click="handleTestCaseClick(testCase)">
                  <div class="progress-info" style="flex: 1; overflow: hidden;">
                    <div class="progress-name" style="font-weight: 500; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ testCase.name }}</div>
                    <div class="progress-time" style="font-size: 12px; color: var(--text-secondary);">
                      {{ 
                        testCase.status === 'completed' ? '已完成' : 
                        testCase.status === 'failed' ? '已失败' : 
                        testCase.status === 'in_progress' ? '执行中' : 
                        testCase.status === 'calculating' ? '计算指标中' : 
                        testCase.status === 'queued' ? '排队中' : '等待中' 
                      }} ({{ testCase.duration || '' }})
                    </div>
                  </div>
                  <div class="progress-actions" style="display: flex; align-items: center; gap: 8px;">
                    <div class="progress-status" style="display: flex; align-items: center; gap: 8px;">
                      <i v-if="testCase.status === 'completed'" class="fas fa-check status-icon" style="color: var(--success-color);"></i>
                      <i v-else-if="testCase.status === 'in_progress'" class="fas fa-spinner fa-spin status-icon" style="color: var(--warning-color);"></i>
                      <i v-else-if="testCase.status === 'calculating'" class="fas fa-calculator status-icon" style="color: var(--info-color, #1677FF);"></i>
                      <i v-else-if="testCase.status === 'queued'" class="fas fa-clock status-icon" style="color: var(--warning-color);"></i>
                      <i v-else-if="testCase.status === 'pending'" class="fas fa-circle pending-dot" style="color: var(--text-disabled);"></i>
                      <i v-else-if="testCase.status === 'skipped'" class="fas fa-forward status-icon" style="color: var(--warning-color);"></i>
                      <i v-else-if="testCase.status === 'deleted'" class="fas fa-trash status-icon" style="color: var(--danger-color, #FF4D4F);"></i>
                      <i v-else-if="testCase.status === 'failed'" class="fas fa-times status-icon" style="color: var(--danger-color, #FF4D4F);"></i>
                      <i v-else-if="testCase.status === 'stopped'" class="fas fa-stop status-icon" style="color: var(--secondary-color);"></i>
                      <i v-else class="fas fa-circle pending-dot" style="color: var(--text-disabled);"></i>
                    </div>
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
                  <i class="fas fa-circle" :class="device.status === 'online' ? 'online-indicator' : 'offline-indicator'" style="font-size: 8px; margin-right: 4px;"></i> {{ device.status === 'online' ? '在线' : '离线' }}
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

const props = defineProps({
  testType: {type: String, required: true, validator: (value) => ['API', 'E2E'].includes(value)},
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
  isExecuting: {type: Boolean, default: false}
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
  'loadMoreLogs'
]);

const shouldShowPauseResumeButton = computed(() => {
  const completedStatuses = ['completed', 'finished', 'success', 'failed', 'stopped'];
  return !completedStatuses.includes(props.taskStatus);
});

const shouldShowStopButton = computed(() => {
  const completedStatuses = ['completed', 'finished', 'success', 'failed', 'stopped'];
  return !completedStatuses.includes(props.taskStatus);
});

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

const visibleCases = computed(() => {
  const start = Math.max(0, caseStartIndex.value - 5);
  const end = Math.min(props.associatedCases.length, caseStartIndex.value + caseVisibleCount + 5);
  return props.associatedCases.slice(start, end).map((item, index) => ({
    ...item,
    viewIndex: start + index
  }));
});

const caseTotalHeight = computed(() => props.associatedCases.length * caseItemHeight);
const caseOffset = computed(() => Math.max(0, caseStartIndex.value - 5) * caseItemHeight);

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
/* 组件样式已内联在模板中 */
</style>
