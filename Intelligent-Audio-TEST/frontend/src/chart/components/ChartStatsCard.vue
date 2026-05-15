<template>
  <div class="chartStatsCard">
    <h4 class="statsCardTitle">统计信息</h4>
    
    <div class="statsGrid basicStats">
      <div class="statItem" v-for="stat in distributionStats.slice(0, 8)" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>
    
    <h5 class="statsSectionTitle">正方向区间：</h5>
    <div class="statsGrid directionStats">
      <div class="statItem" v-for="stat in distributionStats.slice(8, 12)" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>
    
    <h5 class="statsSectionTitle">负方向区间：</h5>
    <div class="statsGrid directionStats">
      <div class="statItem" v-for="stat in distributionStats.slice(12)" :key="stat.label">
        <span class="statLabel">{{ stat.label }}</span>
        <span class="statValue">{{ stat.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StatItem } from '@/shared/types';

interface Props {
  distributionStats?: StatItem[];
}

withDefaults(defineProps<Props>(), {
  distributionStats: () => []
});
</script>

<style scoped>
.chartStatsCard {
  background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid #e2e8f0;
  box-sizing: border-box;
  width: 100%;
  overflow: auto;
}

.statsCardTitle {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #cbd5e1;
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
