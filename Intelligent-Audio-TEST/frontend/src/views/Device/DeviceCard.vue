<template>
  <div
    class="device-card fade-in"
    @click="$emit('toggle-select')"
    :class="{ highlighted: selected }"
  >
    <!-- 卡片头部：复选框 + 状态 -->
    <div class="device-card-header">
      <div class="device-select">
        <input
          type="checkbox"
          class="device-checkbox"
          :value="device.id"
          :checked="selected"
          @click.stop="$emit('toggle-select')"
        >
      </div>
      <div class="device-status">
        <span class="status-badge" :class="device.status">
          <i :class="device.status === 'testing' ? 'fas fa-play-circle testing-indicator' : 'fas fa-circle online-indicator'"></i>
          {{ statusText }}
        </span>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="device-card-content">
      <div class="device-info">
        <h3 class="device-name">{{ device.name }}</h3>
        <p class="device-model">{{ subtitle }}</p>
        <div
          class="device-description"
          v-if="device.description"
          style="margin-top: 8px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4;"
        >
          {{ device.description }}
        </div>
        <div
          class="device-algorithms"
          v-if="device.supportedAlgorithms && device.supportedAlgorithms.length > 0"
        >
          <span class="algo-label">支持算法:</span>
          <AlgorithmTag :algorithms="device.supportedAlgorithms" :max-display="3" />
        </div>
        <!-- meta slots：不同设备类型有不同的 meta 项 -->
        <slot name="meta" :device="device" />
      </div>

      <!-- specs slots：不同设备类型有不同的 spec 项 -->
      <div class="device-specs">
        <slot name="specs" :device="device" />
      </div>
    </div>

    <!-- 卡片底部：操作按钮 -->
    <div class="device-card-footer">
      <div class="connection-controls">
        <button class="btn btn-secondary" @click.stop="$emit('edit')">
          <i class="fas fa-edit btn-icon"></i>
          编辑
        </button>
        <button class="btn btn-danger" @click.stop="$emit('delete')">
          <i class="fas fa-trash btn-icon"></i>
          删除
        </button>
        <!-- 测试按钮：API 设备不显示（通过 showTest 控制） -->
        <button
          v-if="showTest"
          class="btn gradient-btn"
          :class="device.status === 'testing' ? 'btn-danger' : 'btn-success'"
          :disabled="device.status === 'offline'"
          @click.stop="$emit('test')"
        >
          <i :class="device.status === 'testing' ? 'fas fa-stop btn-icon' : 'fas fa-play btn-icon'"></i>
          {{ device.status === 'testing' ? '停止测试' : device.status === 'offline' ? '离线' : '测试' }}
        </button>
        <button class="btn btn-info" @click.stop="$emit('health-check')">
          <i class="fas fa-heartbeat btn-icon"></i>
          健康检查
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AlgorithmTag from '../../components/algorithm/AlgorithmTag.vue'

interface DeviceLike {
  id: string | number
  name: string
  status: string
  description?: string
  supportedAlgorithms?: string[]
  [key: string]: any
}

const props = withDefaults(defineProps<{
  device: DeviceLike
  selected: boolean
  statusTextMap: Record<string, string>
  showTest?: boolean
}>(), {
  showTest: true,
})

const emit = defineEmits<{
  (e: 'toggle-select'): void
  (e: 'edit'): void
  (e: 'delete'): void
  (e: 'test'): void
  (e: 'health-check'): void
}>()

const statusText = computed(() => props.statusTextMap[props.device.status] || props.device.status)
const subtitle = computed(() => props.device.model || props.device.url || '')
</script>
