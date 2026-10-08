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
          <i :class="device.status === DeviceStatus.TESTING ? 'fas fa-play-circle testing-indicator' : 'fas fa-circle online-indicator'"></i>
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
          :class="device.status === DeviceStatus.TESTING ? 'btn-danger' : 'btn-success'"
          :disabled="device.status === DeviceStatus.OFFLINE"
          @click.stop="$emit('test')"
        >
          <i :class="device.status === DeviceStatus.TESTING ? 'fas fa-stop btn-icon' : 'fas fa-play btn-icon'"></i>
          {{ device.status === DeviceStatus.TESTING ? '停止测试' : device.status === DeviceStatus.OFFLINE ? '离线' : '测试' }}
        </button>
        <button class="btn btn-info" @click.stop="$emit('health-check')">
          <i class="fas fa-heartbeat btn-icon"></i>
          健康检查
        </button>
      </div>
    </div>
  </div>
</template>
<style scoped>

.device-checkbox{
width: 16px;
height: 16px;
cursor: pointer;
margin-right: 8px ;
-webkit-appearance: none ;
appearance: none ;
background-color: var(--color-white) !important;
border: 2px solid var(--border-color) !important;
border-radius: 4px ;
position: relative ;
transition: all 0.2s ease ;
display: flex ;
align-items: center ;
justify-content: center ;
flex-shrink: 0 ;
vertical-align: middle ;
z-index: 10 ;
opacity: 1 ;
visibility: visible ;
}

.device-checkbox:disabled{
cursor: not-allowed;
opacity: 0.5 ;
}

.device-card{
border: 2px solid transparent;
padding: 20px;
margin-bottom: 20px;
display: flex;
flex-direction: column;
gap: 16px;
background: white;
border-radius: 12px;
box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 8%, transparent);
transition: all 0.3s ease;
cursor: pointer;
overflow: hidden;
}

.device-card:hover{
border-color: var(--primary-color);
transform: translateY(-5px);
box-shadow: 0 8px 24px color-mix(in srgb, var(--color-black) 12%, transparent);
}



.device-checkbox:checked{
    background-color: var(--primary-color) !important;
    border-color: var(--primary-color) ;
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 20%, transparent) ;
}

.device-checkbox:checked::after{
    content: '✓' ;
    color: white ;
    font-size: 16px ;
    font-weight: bold ;
    position: absolute ;
}







.testing-indicator{
    font-size: 10px;
    animation: spin 1s linear infinite;
}

























/* device-specs - 自全局样式就近迁移 */
.device-specs{
display: grid;
grid-template-columns: 1fr 1fr;
gap: 12px;
padding: 16px;
border-top: 1px solid var(--border-color);
border-bottom: 1px solid var(--border-color);
background: var(--color-bs-gray-100);
border-radius: 8px;
}



@media (max-width: 768px){
.device-specs {
        grid-template-columns: 1fr;
}
}

.test-view-common .device-specs{
  margin-bottom: 16px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
/* device-select - 自全局样式就近迁移 */
.device-select{
    flex-shrink: 0;
}

/* device-card-content - 自全局样式就近迁移 */
.device-card-content{
    padding: 20px;
}

/* connection-controls - 自全局样式就近迁移 */
.connection-controls{
    display: flex;
    gap: 8px;
    margin: 8px 0;
    flex-wrap: wrap;
    align-items: center;
}

/* fade-in - 自全局样式就近迁移 */
.fade-in{
    animation: fadeIn 0.3s ease forwards;
}

</style>

<script setup lang="ts">
import { computed } from 'vue'
import AlgorithmTag from '../../components/algorithm/AlgorithmTag.vue'
import type { Device } from '../../domain/model/device'
import { DeviceStatus } from '../../domain/enums'

/**
 * 卡片设备形状：从 Domain 的 Device 派生（归集内联类型）。
 * 消费方实际传入 TestDevice / APIDevice / PlaybackDevice 联合，
 * 且插槽中会访问视图层扩展展示字段（非 Domain 契约），
 * 故以显式可选字段列出，替代原 [key: string]: any 索引签名兜底。
 */
type DeviceLike = Pick<Device, 'id' | 'name'> & Partial<Device> & {
  /** API 设备端点地址（视图层扩展字段） */
  url?: string
  /** 设备分类（视图层扩展字段） */
  category?: string
  /** 固件版本（视图层扩展字段） */
  firmwareVersion?: string
  /** 最后在线时间（视图层扩展字段） */
  lastOnline?: string
  /** 延迟 ms（视图层扩展字段） */
  delay?: number
  /** 音量 dB（视图层扩展字段） */
  volume?: number
  /** 连接稳定性 %（视图层扩展字段） */
  stability?: number
  /** 采样率 kHz（视图层扩展字段） */
  sampleRate?: number
  /** API 调用方式（视图层扩展字段） */
  method?: string
  /** 响应时间 ms（视图层扩展字段） */
  responseTime?: number
  /** API 版本（视图层扩展字段） */
  version?: string
  /** 最后测试时间（视图层扩展字段） */
  lastTested?: string
  /** 成功率 %（视图层扩展字段） */
  successRate?: number
  /** 认证类型（视图层扩展字段） */
  authType?: string
  /** 关联算法类型（视图层扩展字段） */
  algorithmType?: string
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

const statusText = computed(() => props.statusTextMap[props.device.status ?? ''] || props.device.status || '')
const subtitle = computed(() => props.device.model || props.device.url || '')
</script>
