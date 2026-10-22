<template>
  <section class="execution-diagram" aria-label="执行示意">
    <div class="diagram-header">
      <h3 class="diagram-title">执行示意</h3>
      <p class="diagram-subtitle">展示所选目标并行与串行的执行方式，随配置实时更新</p>
    </div>

    <div v-if="empty" class="diagram-empty">
      选择设备或 API 后，此处实时展示并行/串行执行示意
    </div>

    <div v-else class="diagram-body">
      <!-- 双道版式：设备道 / API 道各自独立、互不等待（空道折叠；两侧均存在时并排展示） -->
      <div class="diagram-lanes" :class="{ 'two-lanes': lanes.length > 1 }">
        <div v-for="lane in lanes" :key="lane.targetType" class="lane-block" :data-lane="lane.targetType">
          <h4 class="lane-title">{{ lane.targetType === 'device' ? '设备道' : 'API 道' }}</h4>

          <!-- 道内并行组：同阶段并发（无箭头 + success 色系） -->
          <div v-if="lane.parallelTargets.length" class="parallel-group">
            <h5 class="parallel-title">并行 · 同时执行</h5>
            <ul class="target-list">
              <li v-for="target in lane.parallelTargets" :key="`${target.targetType}:${target.targetId}`">
                <span class="target-node">
                  <i class="target-icon" :class="iconClass(target.iconKind)"></i>
                  <span class="target-name">{{ target.name }}</span>
                  <span class="target-badge parallel-badge">并行</span>
                </span>
              </li>
            </ul>
          </div>

          <!-- 道内阶段箭头：该道并行目标完成后，该道串行目标按顺序依次启动 -->
          <div v-if="lane.hasStageArrow" class="stage-arrow">
            <i class="fas fa-arrow-down"></i>
          </div>

          <!-- 道内串行链：依次排队（箭头链 + info 色系） -->
          <div v-if="lane.serialTargets.length" class="serial-group">
            <h5 class="serial-title">串行 · 依次执行</h5>
            <ul class="target-list serial-list">
              <li
                v-for="(target, index) in lane.serialTargets"
                :key="`${target.targetType}:${target.targetId}`"
                class="serial-item"
              >
                <i v-if="index > 0" class="fas fa-arrow-right target-arrow"></i>
                <span class="target-node">
                  <i class="target-icon" :class="iconClass(target.iconKind)"></i>
                  <span class="target-name">{{ target.name }}</span>
                  <span class="target-badge serial-badge">串行</span>
                </span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- 注记行（恒显）：承载 INT-1115 双道调度语义 -->
      <p class="diagram-note">
        设备与 API 为两条独立执行道、互不等待；并行目标同时启动；串行目标仅等同类道内前序（含并行）目标全部完成后启动
      </p>
    </div>
  </section>
</template>

<script setup>
/**
 * 底部并行/串行示意图（INT-1268/INT-1115 §5.2.4）。
 * 数据由 useMergedTestFlow 的 executionLanes 派生（唯一受控源：卡片受控值 / 载荷 / 示意图同源），
 * 本组件只做呈现。双道语义：设备与 API 两条独立执行道互不等待、始终并发；
 * 道内：并行目标启动即并发、不受门控；串行目标仅等同类道内前序（含并行）目标终态后派发。
 * 并行 = 同组并列 + 无箭头 + success 色系；串行 = 箭头链 + info 色系。
 * 组件不返回 null——空态渲染占位，保持版式稳定。
 */
import { computed } from 'vue'

const props = defineProps({
  /** 执行道（{targetType, parallelTargets[], serialTargets[], hasStageArrow}） */
  lanes: { type: Array, default: () => [] },
  /** 空态（无选中目标） */
  empty: { type: Boolean, default: false },
})

/** 目标节点图标（iconKind：physical/http_api/websocket_api=设备类型；api=API 目标） */
const ICON_CLASS = {
  physical: 'fas fa-mobile-alt',
  http_api: 'fas fa-server',
  websocket_api: 'fas fa-tower-broadcast',
  api: 'fas fa-globe',
}

const iconClass = (kind) => ICON_CLASS[kind] || ICON_CLASS.physical

// lanes 可能为 undefined（父级未传入时），保持渲染稳健
const safeLanes = computed(() => props.lanes || [])
</script>

<style scoped>
.execution-diagram{
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.diagram-header{
  margin-bottom: var(--spacing-sm);
}

.diagram-title{
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--foreground);
  margin: 0;
}

.diagram-subtitle{
  margin-top: 2px;
  font-size: var(--font-size-xs, 12px);
  color: var(--muted-foreground);
}

.diagram-empty{
  padding: var(--spacing-xl) var(--spacing-md);
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--muted-foreground);
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
}

.diagram-lanes{
  display: grid;
  gap: var(--spacing-sm);
  grid-template-columns: 1fr;
}

.diagram-lanes.two-lanes{
  grid-template-columns: repeat(2, 1fr);
}

@media (max-width: 1200px){
  .diagram-lanes.two-lanes{
    grid-template-columns: 1fr;
  }
}

.lane-block{
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
}

.lane-title{
  margin: 0 0 var(--spacing-sm);
  font-size: var(--font-size-xs, 12px);
  font-weight: var(--font-weight-semibold);
  color: var(--muted-foreground);
}

.parallel-group{
  border: 1px dashed color-mix(in srgb, var(--success) 40%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--success) 5%, transparent);
  padding: var(--spacing-sm);
}

.parallel-title{
  margin: 0 0 var(--spacing-sm);
  font-size: var(--font-size-xs, 12px);
  font-weight: var(--font-weight-medium);
  color: var(--success);
}

.serial-group{
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6, 6px);
}

.serial-title{
  margin: 0 0 var(--spacing-6, 6px);
  font-size: var(--font-size-xs, 12px);
  font-weight: var(--font-weight-medium);
  color: var(--info);
}

.target-list{
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.serial-list{
  align-items: center;
}

.serial-item{
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.target-node{
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-6, 6px);
  padding: var(--spacing-6, 6px) var(--spacing-sm);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs, 12px);
}

.target-icon{
  font-size: 12px;
  color: var(--muted-foreground);
}

.target-name{
  max-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
  color: var(--foreground);
}

.target-badge{
  padding: 1px var(--spacing-6, 6px);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-10, 10px);
  font-weight: var(--font-weight-medium);
}

.parallel-badge{
  background: color-mix(in srgb, var(--success) 10%, transparent);
  color: var(--success);
}

.serial-badge{
  background: color-mix(in srgb, var(--info) 10%, transparent);
  color: var(--info);
}

.stage-arrow{
  display: flex;
  justify-content: center;
  padding: var(--spacing-6, 6px) 0;
  color: var(--muted-foreground);
}

.target-arrow{
  font-size: 12px;
  color: var(--muted-foreground);
}

.diagram-note{
  margin: var(--spacing-sm) 0 0;
  font-size: var(--font-size-xs, 12px);
  color: var(--muted-foreground);
}
</style>
