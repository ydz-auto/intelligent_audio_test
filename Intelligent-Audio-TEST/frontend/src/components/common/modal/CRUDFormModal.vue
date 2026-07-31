<template>
  <div class="crud-form-modal">
    <form @submit.prevent="handleSubmit" novalidate>
      <h3>{{ title || (isEditMode ? '编辑' : '添加') + entityName }}</h3>
      
      <DeviceSelector
        v-if="showDeviceSelector"
        :is-scanning="isScanning"
        :display-devices="displayDevices"
        :selected-device-id="selectedDeviceId"
        @select="handleDeviceSelect"
        @rescan="handleRescanDevices"
      />
      
      <div class="form-content">
        <template v-for="(fields, groupName) in groupedFields" :key="groupName">
          <div class="form-group-section" v-if="fields && fields.length > 0">
            <h4 class="section-title">{{ groupName }}</h4>
            <div class="form-grid">
              <template v-for="field in fields" :key="field?.key">
                <div 
                  v-if="field && typeof field === 'object'"
                  :class="{ 'full-width': field.type === 'array' || field.fullWidth === true }"
                >
                  <ArrayField
                    v-if="field.type === 'array'"
                    :field="field"
                    v-model="formValues[field.key]"
                    :error="validationErrors[field.key]"
                    @test-spl="handleTestSPL"
                    @stop-spl="handleStopSPL"
                    @test-spl-complete="handleTestSPLComplete"
                  />
                  <FormField
                    v-else
                    :field="field"
                    v-model="formValues[field.key]"
                    :error="validationErrors[field.key]"
                    @file-upload="handleFileUpload"
                    @button-action="handleButtonAction"
                  />
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
      
      <div class="modal-footer">
        <button type="button" class="btn-secondary" @click="$emit('close')">
          取消
        </button>
        <button type="submit" class="btn-primary" :disabled="submitting">
          <span v-if="submitting" class="loading-spinner"></span>
          {{ submitting ? '处理中...' : (isEditMode ? '保存' : '添加') }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import FormField from '../form/FormField.vue'
import ArrayField from '../form/ArrayField.vue'
import DeviceSelector from './DeviceSelector.vue'

import { useCRUDFormModal } from './CRUDFormModal'

const props = defineProps({
  modalId: { type: String, default: '' },
  entityName: { type: String, default: '数据' },
  title: { type: String, default: '' },
  fields: { type: Array, default: () => [] },
  formData: { type: Object, default: () => ({}) },
  mode: { type: String, default: 'create', validator: (value) => ['create', 'edit'].includes(value) }
})

const emit = defineEmits(['close', 'confirm', 'cancel', 'update:props', 'action', 'test-spl-complete'])

const {
  formValues,
  submitting,
  groupedFields,
  validationErrors,
  showDeviceSelector,
  displayDevices,
  selectedDeviceId,
  isScanning,
  isEditMode,
  handleDeviceSelect,
  handleRescanDevices,
  handleFileUpload,
  handleTestSPL,
  handleStopSPL,
  handleTestSPLComplete,
  handleButtonAction,
  handleSubmit
} = useCRUDFormModal(props, emit)
</script>

<style scoped>
@import './CRUDFormModal.css';
</style>
