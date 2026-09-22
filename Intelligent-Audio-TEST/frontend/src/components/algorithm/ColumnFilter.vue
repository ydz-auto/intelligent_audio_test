<template>
  <span class="col-filter">
    <i
      ref="iconRef"
      class="fas fa-filter col-filter-icon"
      :class="{ 'col-filter-icon--active': active }"
      :title="active ? '已过滤：' + (filterLabel || modelValue) + '（点击修改）' : '过滤'"
      @click.stop="toggle"
    ></i>
    <Teleport to="body">
      <div
        v-if="open"
        ref="popoverRef"
        class="col-filter-popover"
        :style="{ top: popoverStyle.top, left: popoverStyle.left }"
        @click.stop
      >
        <div class="col-filter-popover-head">
          <span class="col-filter-popover-title">{{ label }}</span>
          <button class="col-filter-popover-reset" type="button" @click="reset">重置</button>
        </div>
        <select
          class="form-input col-filter-select"
          :value="modelValue"
          @change="onChange"
        >
          <option value="all">全部</option>
          <option v-for="opt in optList" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, onBeforeUnmount } from 'vue'

interface FilterOption {
  value: string
  label: string
}

const props = withDefaults(defineProps<{
  /** 当前筛选值，'all' 表示不过滤 */
  modelValue: string
  /** 列名，用于弹层标题 */
  label: string
  /** 可选项：字符串数组 或 { value, label } 数组 */
  options?: (string | FilterOption)[]
  /** 是否已启用过滤（用于图标高亮） */
  active?: boolean
}>(), {
  options: () => [],
  active: false
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const optList = computed<FilterOption[]>(() =>
  props.options.map(o => (typeof o === 'string' ? { value: o, label: o } : o))
)

// 当前选中项的文字（用于图标提示）
const filterLabel = computed(() => {
  if (props.modelValue === 'all') return ''
  return optList.value.find(o => o.value === props.modelValue)?.label || props.modelValue
})

const open = ref(false)
const iconRef = ref<HTMLElement>()
const popoverRef = ref<HTMLElement>()
const popoverStyle = reactive({ top: '0px', left: '0px' })

function toggle() {
  if (open.value) {
    open.value = false
    return
  }
  const r = iconRef.value?.getBoundingClientRect()
  if (r) {
    const POP_H = 120 // 估算弹层高度，用于底部越界时向上展开
    const w = Math.min(200, window.innerWidth - 16)
    let top = r.bottom + 4
    if (top + POP_H > window.innerHeight) {
      top = Math.max(4, r.top - POP_H - 4)
    }
    popoverStyle.top = `${Math.round(top)}px`
    popoverStyle.left = `${Math.max(8, Math.min(Math.round(r.left), window.innerWidth - w - 8))}px`
  }
  open.value = true
}

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
  open.value = false
}

function reset() {
  emit('update:modelValue', 'all')
  open.value = false
}

// 点击弹层或图标外部时关闭。
// 注意：模态窗 .modal 上带有 @click.stop，click 事件到不了 document，
// 因此监听 mousedown（不受 click.stop 影响）+ 目标包含判断。
function onDocMousedown(e: MouseEvent) {
  const target = e.target as Node
  if (popoverRef.value?.contains(target) || iconRef.value?.contains(target)) return
  open.value = false
}

function onScroll() {
  open.value = false
}

watch(open, (v) => {
  if (v) {
    document.addEventListener('mousedown', onDocMousedown)
    document.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onScroll)
  } else {
    document.removeEventListener('mousedown', onDocMousedown)
    document.removeEventListener('scroll', onScroll, true)
    window.removeEventListener('resize', onScroll)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMousedown)
  document.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', onScroll)
})
</script>

<style scoped>
.col-filter {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  vertical-align: middle;
}
.col-filter-icon {
  font-size: 11px;
  color: var(--text-tertiary, #999);
  cursor: pointer;
  padding: 2px 3px;
  border-radius: 4px;
  transition: color 0.15s, background-color 0.15s;
  line-height: 1;
}
.col-filter-icon:hover {
  color: var(--primary-color, #1677ff);
  background: var(--primary-light, rgba(22, 119, 255, 0.1));
}
.col-filter-icon--active {
  color: var(--primary-color, #1677ff);
  background: var(--primary-light, rgba(22, 119, 255, 0.1));
}
.col-filter-popover {
  position: fixed;
  /* 模态窗 z-index 为 13000，弹层需在其之上 */
  z-index: 21000;
  width: 180px;
  background: #fff;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
  padding: 8px;
  box-sizing: border-box;
}
.col-filter-popover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.col-filter-popover-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary, #333);
}
.col-filter-popover-reset {
  border: none;
  background: none;
  color: var(--primary-color, #1677ff);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}
.col-filter-popover-reset:hover {
  text-decoration: underline;
}
.col-filter-select {
  width: 100%;
  height: 30px;
  box-sizing: border-box;
}
</style>
