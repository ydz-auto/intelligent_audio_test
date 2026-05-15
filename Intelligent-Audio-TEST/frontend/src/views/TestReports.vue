<template>
  <div class="test-reports-view">
    <h1>测试历史报告数据</h1>
    <div v-if="loading">加载中...</div>
    <div v-else>
      <h2>报告数量{{ reports.length }}</h2>
      <button @click="fetchReports">刷新报告</button>
      <div v-for="report in reports" :key="report.id" class="report-item">
        <h3>{{ report.name }}</h3>
        <p>{{ report.description }}</p>
        <p>类型: {{ getReportTypeLabel(report.type) }}, 状态: {{ report.status === 'published' ? '发布' : '草稿' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useTestReports } from './TestReportsLogic/testReports';

const {
  reports,
  loading,
  fetchReports,
  getReportTypeLabel
} = useTestReports();
</script>

<style scoped>
.test-reports-view {
  padding: 20px;
}

.report-item {
  border: 1px solid #ccc;
  padding: 10px;
  margin: 10px 0;
  border-radius: 5px;
}
</style>
