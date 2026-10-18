<template>
  <div
    class="avatar-badge"
    :style="{ backgroundColor: bgColor }"
    :title="name"
  >
    <span :style="{ color: fgColor }">{{ initials }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  name: string
  size?: number
}>()

/** 哈希底色：把用户名散列映射到一组固定底色（深色可用） */
const AVATAR_COLORS = [
  { bg: '#ff6a00', fg: '#ffffff' },
  { bg: '#1976d2', fg: '#ffffff' },
  { bg: '#52c41a', fg: '#ffffff' },
  { bg: '#7c4dff', fg: '#ffffff' },
  { bg: '#00a2ae', fg: '#ffffff' },
  { bg: '#d81b60', fg: '#ffffff' },
  { bg: '#5c6bc0', fg: '#ffffff' },
  { bg: '#e65100', fg: '#ffffff' },
]

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

const palette = computed(() => {
  const idx = hashString(props.name || '?') % AVATAR_COLORS.length
  return AVATAR_COLORS[idx]
})

const bgColor = computed(() => palette.value.bg)
const fgColor = computed(() => palette.value.fg)

const initials = computed(() => {
  const name = props.name || '?'
  const trimmed = name.trim()
  if (!trimmed) return '?'
  // 取用户名前两个字符（中文用户名直接取前两字）
  return trimmed.slice(0, 2).toUpperCase()
})
</script>

<style scoped>
.avatar-badge {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  user-select: none;
  font-weight: 600;
  font-size: 13px;
}
.avatar-badge span {
  line-height: 1;
}
</style>
