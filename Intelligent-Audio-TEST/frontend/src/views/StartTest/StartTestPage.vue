<template>
  <div class="start-test-page">
    <div class="page-header">
      <div class="header-left">
        <h2>开始测试</h2>
        <p>选择测试类型发起测试任务（端到端 / API 合并入口建设中）</p>
      </div>
    </div>

    <div class="start-test-grid">
      <router-link to="/E2ETest" class="test-type-card">
        <div class="test-type-card__icon">
          <i class="fas fa-project-diagram"></i>
        </div>
        <h3>端到端测试</h3>
        <p>选择测试用例与设备，执行端到端语音测试流程。</p>
      </router-link>

      <router-link to="/APITest" class="test-type-card">
        <div class="test-type-card__icon">
          <i class="fas fa-exchange-alt"></i>
        </div>
        <h3>API 测试</h3>
        <p>配置 API 端点与参数，执行接口级语音测试流程。</p>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
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
  color: var(--text-secondary);
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
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
