<template>
  <div class="export-form">
    <div class="form-section">
      <h5>
        导出配置
        <button type="button" class="btn btn-outline-primary btn-sm ml-2" @click="downloadTemplate">
          <i class="fas fa-download"></i> 下载模板
        </button>
      </h5>
      <div class="form-row">
        <div class="form-group">
          <label for="export-groups">选择测试组 <span class="required">*</span></label>
          <div class="form-check" v-for="group in testCaseGroups" :key="group">
            <input type="checkbox" class="form-check-input" :id="`group-${group}`" v-model="localFormData.groups" :value="group">
            <label class="form-check-label" :for="`group-${group}`">{{ group }}</label>
          </div>
          <div v-if="localFormData.groups.length === 0" class="text-danger mt-1">请至少选择一个测试组</div>
        </div>
      </div>
      <div class="form-row mt-3">
        <div class="form-group">
          <label for="export-test-type">导出配置类型</label>
          <select id="export-test-type" class="form-control" v-model="localFormData.testType">
            <option value="all">所有配置</option>
            <option value="api">仅API测试配置</option>
            <option value="e2e">仅端到端测试配置</option>
          </select>
        </div>
        <div class="form-group">
          <label for="export-format">导出格式 <span class="required">*</span></label>
          <select id="export-format" class="form-control" v-model="localFormData.format" required>
            <option value="xlsx">Excel格式（.xlsx，多Sheet结构，推荐）</option>
            <option value="json">JSON格式（完整数据）</option>
          </select>
        </div>
      </div>
      <div class="form-row mt-3">
        <div class="form-group">
          <div class="form-check">
            <input type="checkbox" class="form-check-input" id="include-config" v-model="localFormData.includeConfig">
            <label class="form-check-label" for="include-config">包含完整配置信息</label>
          </div>
        </div>
        <div class="form-group">
          <div class="form-check">
            <input type="checkbox" class="form-check-input" id="include-deleted" v-model="localFormData.includeDeleted">
            <label class="form-check-label" for="include-deleted">包含已删除用例</label>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section mt-4">
      <h5>导出预览</h5>
      <div class="preview-stats">
        <span class="stat-item">预计导出：{{ previewData.total }} 条</span>
        <span class="stat-item">API测试配置：{{ previewData.apiCount }} 条</span>
        <span class="stat-item">端到端测试配置：{{ previewData.e2eCount }} 条</span>
      </div>
      <div class="preview-table-container mt-3">
        <table class="table table-sm">
          <thead>
            <tr>
              <th>分组</th>
              <th>用例数量</th>
              <th>API测试配置</th>
              <th>端到端测试配置</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(group, index) in previewData.groupStats" :key="index">
              <td>{{ group.name }}</td>
              <td>{{ group.total }}</td>
              <td>{{ group.api }}</td>
              <td>{{ group.e2e }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { testcasesApi } from '../../../../utils/api';
import type { ExportFormData, GroupStat } from './types';

const props = defineProps<{
  testCaseGroups: string[];
  testType?: string;
}>();

const emit = defineEmits<{
  (e: 'update', data: ExportFormData & { ids: (string | number)[] }): void;
  (e: 'submit'): void;
}>();

const localFormData = ref<ExportFormData>({
  groups: [],
  testType: props.testType || 'all',
  format: 'json',
  includeConfig: true,
  includeDeleted: false
});

const exportCaseIds = ref<(string | number)[]>([]);
const previewData = ref<{
  total: number;
  apiCount: number;
  e2eCount: number;
  groupStats: GroupStat[];
}>({
  total: 0,
  apiCount: 0,
  e2eCount: 0,
  groupStats: []
});

let isUpdatingPreview = false;

async function updateExportPreview() {
  if (isUpdatingPreview) return;
  isUpdatingPreview = true;

  try {
    previewData.value = { total: 0, apiCount: 0, e2eCount: 0, groupStats: [] };
    exportCaseIds.value = [];

    if (localFormData.value.groups.length === 0) return;

    const fetchAllTestCases = async () => {
      const allTestCases = [];
      let page = 1;
      let hasMore = true;

      while (hasMore) {
        const response = await testcasesApi.getAll({ page, perPage: 100 });
        const items = response?.items || [];
        const pages = response?.pages || 1;

        allTestCases.push(...items);

        if (page >= pages || items.length === 0) {
          hasMore = false;
        } else {
          page++;
        }
      }

      return allTestCases;
    };

    const getGroupName = (testCase: any): string => {
      return String(testCase?.group_name || testCase?.group || testCase?.groupName || testCase?.group_id || testCase?.groupId || '');
    };

    const getTypesSet = (testCase: any): Set<string> => {
      const types = new Set<string>();
      const raw = testCase?.type ?? testCase?.testType;
      if (Array.isArray(raw)) {
        for (const t of raw) {
          if (t === 'api' || t === 'e2e') types.add(t);
        }
      } else if (raw === 'api' || raw === 'e2e') {
        types.add(raw);
      }
      const config = testCase?.config || {};
      const audios = Array.isArray(config.audios) ? config.audios : [];
      for (const audio of audios) {
        if (audio?.testType === 'api' || audio?.testType === 'e2e') {
          types.add(audio.testType);
        }
      }
      return types;
    };

    const testCases = await fetchAllTestCases();

    let filteredCases = [...testCases];

    const normalize = (s: string | number | undefined | null): string => String(s || '').trim().toLowerCase();
    const selectedGroupsNorm = localFormData.value.groups.map(normalize);

    filteredCases = filteredCases.filter(testCase => {
      const groupName = normalize(getGroupName(testCase));
      return selectedGroupsNorm.includes(groupName);
    });

    if (localFormData.value.testType !== 'all') {
      filteredCases = filteredCases.filter(testCase => {
        if (localFormData.value.testType === 'api') {
          return getTypesSet(testCase).has('api');
        } else if (localFormData.value.testType === 'e2e') {
          return getTypesSet(testCase).has('e2e');
        }
        return true;
      });
    }

    const apiCount = filteredCases.filter(testCase => getTypesSet(testCase).has('api')).length;
    const e2eCount = filteredCases.filter(testCase => getTypesSet(testCase).has('e2e')).length;

    const groupStats: GroupStat[] = [];
    localFormData.value.groups.forEach(group => {
      const groupCases = filteredCases.filter(testCase => normalize(getGroupName(testCase)) === normalize(group));
      groupStats.push({
        name: group,
        total: groupCases.length,
        api: groupCases.filter(testCase => getTypesSet(testCase).has('api')).length,
        e2e: groupCases.filter(testCase => getTypesSet(testCase).has('e2e')).length
      });
    });

    previewData.value = {
      total: filteredCases.length,
      apiCount,
      e2eCount,
      groupStats
    };

    exportCaseIds.value = filteredCases.map((testCase: any) => testCase.id).filter((id: any) => id !== undefined && id !== null);
  } finally {
    isUpdatingPreview = false;
  }
}

async function downloadTemplate() {
  try {
    const response = await testcasesApi.downloadTemplate();
    const blob = response instanceof Blob ? response : new Blob([response]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `测试用例导入模板_${new Date().toLocaleDateString()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error: unknown) {
    console.error('下载模板失败:', error);
    alert('下载模板失败: ' + ((error as Error).message || '未知错误'));
  }
}

function handleSubmit() {
  if (localFormData.value.groups.length === 0) {
    alert('请至少选择一个测试组');
    return;
  }

  const ids = exportCaseIds.value;
  if (ids.length === 0) {
    alert('没有可导出的用例');
    return;
  }

  emit('update', { ...localFormData.value, ids });
}

watch(
  () => [localFormData.value.groups, localFormData.value.testType, localFormData.value.includeDeleted],
  () => {
    updateExportPreview();
  },
  { deep: true }
);

onMounted(() => {
  updateExportPreview();
});

defineExpose({
  handleSubmit,
  localFormData,
  exportCaseIds
});
</script>

<style scoped>
.export-form {
  padding: 0;
}

.form-section {
  margin: 16px 0;
}

.form-section h5 {
  margin-bottom: 16px;
  font-weight: 600;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-check {
  margin-bottom: 8px;
}

.form-check-label {
  margin-left: 8px;
  cursor: pointer;
}

.preview-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 14px;
}

.stat-item {
  background: #e9ecef;
  padding: 4px 12px;
  border-radius: 4px;
}

.preview-table-container {
  max-height: 300px;
  overflow-y: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 8px 12px;
  border: 1px solid #dee2e6;
  text-align: left;
}

.table th {
  background: #f8f9fa;
  font-weight: 600;
}
</style>
