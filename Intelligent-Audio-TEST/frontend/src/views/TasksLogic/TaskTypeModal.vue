<template>
  <div class="task-type-modal">
    <div class="modal-content">
      <p class="modal-message">请选择测试类型：</p>
      <div class="task-type-options">
        <button 
          class="task-type-btn e2e-test"
          @click="selectTestType('E2ETest')"
        >
          <i class="fas fa-project-diagram"></i>
          <span>端到端测试</span>
        </button>
        <button 
          class="task-type-btn api-test"
          @click="selectTestType('APITest')"
        >
          <i class="fas fa-exchange-alt"></i>
          <span>API测试</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useModalControl } from '../../composables/useModal'

const props = defineProps({
  modalId: {type: String, required: true}
})

const emit = defineEmits(['close', 'confirm', 'cancel'])

const modalManager = useModalControl()

const selectTestType = (type) => {
  emit('confirm', { testTestType: type })
  modalManager.confirm(props.modalId, { testTestType: type })
}
</script>

<style scoped>
.task-type-modal {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.modal-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.modal-message {
  margin: 0;
  font-size: 16px;
  color: #475569;
  text-align: center;
}

.task-type-options {
  display: flex;
  gap: 20px;
  justify-content: center;
  width: 100%;
}

.task-type-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  width: 160px;
  height: 140px;
}

.task-type-btn i {
  font-size: 32px;
}

.task-type-btn.e2e-test {
  background-color: #e0f2fe;
  color: #0284c7;
  box-shadow: 0 4px 6px -1px rgba(2, 132, 199, 0.1), 0 2px 4px -1px rgba(2, 132, 199, 0.06);
}

.task-type-btn.e2e-test:hover {
  background-color: #bae6fd;
  box-shadow: 0 10px 15px -3px rgba(2, 132, 199, 0.1), 0 4px 6px -2px rgba(2, 132, 199, 0.05);
  transform: translateY(-2px);
}

.task-type-btn.api-test {
  background-color: #fef3c7;
  color: #d97706;
  box-shadow: 0 4px 6px -1px rgba(217, 119, 6, 0.1), 0 2px 4px -1px rgba(217, 119, 6, 0.06);
}

.task-type-btn.api-test:hover {
  background-color: #fde68a;
  box-shadow: 0 10px 15px -3px rgba(217, 119, 6, 0.1), 0 4px 6px -2px rgba(217, 119, 6, 0.05);
  transform: translateY(-2px);
}
</style>