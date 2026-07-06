<template>
  <div class="chartStatsCard">
    <div class="statsHeader">
      <h4 class="statsCardTitle">统计信息</h4>
      <div class="deviceTabs" v-if="deviceList.length >= 1">
        <button
          v-for="device in deviceList"
          :key="device"
          class="deviceTab"
          :class="{ active: selectedDevice === device }"
          @click="selectedDevice = device"
        >
          {{ device }}
        </button>
      </div>
    </div>

    <div class="statsGrid basicStats">
      <div class="statItem" v-for="stat in currentStats.slice(0, 8)" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>

    <h5 class="statsSectionTitle">正方向区间：</h5>
    <div class="statsGrid directionStats">
      <div class="statItem" v-for="stat in positiveStats" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>

    <h5 class="statsSectionTitle" v-if="negativeStats.length > 0">负方向区间：</h5>
    <div class="statsGrid directionStats" v-if="negativeStats.length > 0">
      <div class="statItem" v-for="stat in negativeStats" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { StatItem } from '@/shared/types';

interface Props {
  distributionStats?: StatItem[];
  distributionStatsByDevice?: { [device: string]: StatItem[] };
}

const props = withDefaults(defineProps<Props>(), {
  distributionStats: () => [],
  distributionStatsByDevice: () => ({})
});

const selectedDevice = ref<string>('');

const deviceList = computed<string[]>(() => {
  return Object.keys(props.distributionStatsByDevice || {});
});

// 默认选中第一个设备
watch(deviceList, (list) => {
  if (list.length > 0 && !list.includes(selectedDevice.value)) {
    selectedDevice.value = list[0];
  }
}, { immediate: true });

const currentStats = computed<StatItem[]>(() => {
  if (deviceList.value.length === 0) {
    return props.distributionStats;
  }
  if (!selectedDevice.value) {
    return props.distributionStatsByDevice[deviceList.value[0]] || props.distributionStats;
  }
  return props.distributionStatsByDevice[selectedDevice.value] || props.distributionStats;
});

// 前8个是基础统计，之后正方向在前，负方向在后（以"超出-(μ"标签为分界）
const positiveStats = computed<StatItem[]>(() => {
  const stats = currentStats.value.slice(8);
  const negIdx = stats.findIndex(s => s.label.includes('超出-(') || s.label.includes('[-'));
  return negIdx === -1 ? stats : stats.slice(0, negIdx);
});

const negativeStats = computed<StatItem[]>(() => {
  const stats = currentStats.value.slice(8);
  const negIdx = stats.findIndex(s => s.label.includes('超出-(') || s.label.includes('[-'));
  return negIdx === -1 ? [] : stats.slice(negIdx);
});
</script>

<style scoped>
.chartStatsCard {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-sizing: border-box;
  width: 100%;
  overflow: auto;
}

.statsHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #cbd5e1;
}

.statsCardTitle {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.deviceTabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.deviceTab {
  padding: 4px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 4px;
  background: white;
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.deviceTab:hover {
  border-color: #FF6A00 !important;
  color: #FF6A00 !important;
  background-color: rgba(255, 106, 0, 0.1) !important;
}

.deviceTab.active {
  background-color: rgba(255, 106, 0, 0.1) !important;
  border-color: #FF6A00 !important;
  color: #FF6A00 !important;
  box-shadow: 0 8px 24px rgba(255, 106, 0, 0.2) !important;
}

.statsGrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  width: 100%;
  box-sizing: border-box;
}

.chartStatsCard .statItem {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  box-sizing: border-box;
  min-width: 180px;
}

.chartStatsCard .statLabel {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
  text-align: center;
}

.chartStatsCard .statValue {
  font-size: 20px;
  font-weight: 600;
  color: #1677FF;
  text-align: center;
}

.statsSectionTitle {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin: 20px 0 12px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid #cbd5e1;
}

.basicStats {
  margin-bottom: 12px;
}

.directionStats {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
</style>
