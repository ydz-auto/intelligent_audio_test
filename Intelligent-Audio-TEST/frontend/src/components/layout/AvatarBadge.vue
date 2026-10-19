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

/** 哈希底色：把用户名散列映射到一组固定底色（身份色令牌，深浅同值不随主题换色） */
const AVATAR_COLORS = [
  { bg: 'var(--avatar-1)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-2)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-3)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-8)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-9)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-10)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-11)', fg: 'var(--color-white)' },
  { bg: 'var(--avatar-12)', fg: 'var(--color-white)' },
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
  border-radius: var(--radius-pill);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  user-select: none;
  font-weight: var(--font-weight-semibold);
  font-size: 13px;
}
.avatar-badge span {
  line-height: 1;
}
</style>
