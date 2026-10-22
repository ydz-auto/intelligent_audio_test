<template>
  <div class="start-test-page">
    <div class="page-header">
      <div class="header-left">
        <h2>开始测试</h2>
        <p>选择测试用例与设备/API，在同一流程内完成语音测试与报告生成</p>
      </div>
    </div>

    <div class="start-test-grid">
      <router-link to="/start-test" class="test-type-card">
        <div class="test-type-card__icon">
          <i class="fas fa-project-diagram"></i>
        </div>
        <h3>开始测试</h3>
        <p>选择测试用例与设备/API，执行语音测试流程并生成报告。</p>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

</script>

<style scoped>
.start-test-page {
  width: 100%;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--foreground);
}
.page-header p {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--muted-foreground);
}
.start-test-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}
.test-type-card {
  display: block;
  padding: 28px 24px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  text-decoration: none;
  color: var(--foreground);
  transition: all var(--transition-normal);
}
.test-type-card:hover {
  border-color: var(--ring);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.test-type-card__icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--primary);
  margin-bottom: 16px;
}
.test-type-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
}
.test-type-card p {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
  line-height: 1.6;
}
</style>
