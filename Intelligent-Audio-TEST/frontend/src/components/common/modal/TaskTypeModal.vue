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
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

const props = defineProps({
  modalId: {type: String, required: true}
})

const emit = defineEmits(['close', 'confirm', 'cancel'])

const selectTestType = (type) => {
  // INT-309：载荷键统一为 testType（与 Tasks.vue handleCreateTask 读取一致；
  // 原 testTestType 为拼写断点，任务页创建入口静默失效）
  emit('confirm', { testType: type })
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
  color: var(--color-slate-600);
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
  border-radius: var(--radius-lg);
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
  background-color: var(--color-sky-100);
  color: var(--color-sky-600);
  box-shadow: 0 4px 6px -1px color-mix(in srgb, var(--color-sky-600) 10%, transparent), 0 2px 4px -1px color-mix(in srgb, var(--color-sky-600) 6%, transparent);
}

.task-type-btn.e2e-test:hover {
  background-color: var(--color-sky-200);
  box-shadow: 0 10px 15px -3px color-mix(in srgb, var(--color-sky-600) 10%, transparent), 0 4px 6px -2px color-mix(in srgb, var(--color-sky-600) 5%, transparent);
  transform: translateY(-2px);
}

.task-type-btn.api-test {
  background-color: var(--color-amber-100);
  color: var(--color-amber-600);
  box-shadow: 0 4px 6px -1px color-mix(in srgb, var(--color-amber-600) 10%, transparent), 0 2px 4px -1px color-mix(in srgb, var(--color-amber-600) 6%, transparent);
}

.task-type-btn.api-test:hover {
  background-color: var(--color-amber-200);
  box-shadow: 0 10px 15px -3px color-mix(in srgb, var(--color-amber-600) 10%, transparent), 0 4px 6px -2px color-mix(in srgb, var(--color-amber-600) 5%, transparent);
  transform: translateY(-2px);
}
</style>