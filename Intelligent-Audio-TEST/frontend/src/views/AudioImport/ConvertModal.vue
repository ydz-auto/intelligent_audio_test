<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal-container">
      <div class="modal-header">
        <h3>音频格式转换</h3>
        <div class="modal-close" @click="$emit('close')">
          <i class="fas fa-times"></i>
        </div>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label>目标格式</label>
          <select v-model="info.targetFormat" class="form-control">
            <option value="wav">WAV</option>
            <option value="mp3">MP3</option>
          </select>
        </div>
        <div class="form-group">
          <label>采样率</label>
          <select v-model="info.targetSampleRate" class="form-control">
            <option value="16000">16000 Hz</option>
            <option value="44100">44100 Hz</option>
            <option value="48000">48000 Hz</option>
          </select>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" @click="$emit('confirm')">开始转换</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  info: {
    targetFormat: string
    targetSampleRate: string
  }
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'confirm'): void
}>()
</script>
