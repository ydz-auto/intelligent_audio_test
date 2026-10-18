<template>
  <footer class="public-footer">
    <div class="public-footer-inner">
      <div class="footer-brand">
        <i class="fas fa-headset footer-logo"></i>
        <div class="footer-brand-text">
          <span class="footer-title">智能语音测试系统</span>
          <span class="footer-desc">端到端测试 · API 测试 · 多维度评估 · 报告分析</span>
        </div>
      </div>
      <div class="footer-copyright">
        <span>© {{ year }} 智能语音测试平台. 保留所有权利。</span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
/** 页脚（总表 §2.1：品牌列 + 版权行；法务开关 site.legal.* 待后端立项前不渲染） */
const year = new Date().getFullYear()
</script>

<style scoped>
.public-footer {
  border-top: 1px solid var(--border);
  background: var(--background);
}
.public-footer-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.footer-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.footer-logo {
  font-size: 18px;
  color: var(--primary);
}
.footer-brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.footer-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.footer-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}
.footer-copyright {
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
