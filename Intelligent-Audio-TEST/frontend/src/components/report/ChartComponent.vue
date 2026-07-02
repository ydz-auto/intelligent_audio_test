<template>
  <div class="chart-component-container">
    <!-- 图表标题 -->
    <div class="chart-header" v-if="showHeader && title">
      <h3 class="chart-title" v-if="title">{{ title }}</h3>
    </div>
    
    <!-- 正态分布统计信息卡片 -->
    <ChartStatsCard 
      v-if="type === 'distribution' && hasData" 
      :distributionStats="distributionStats" 
      :distributionStatsByDevice="distributionStatsByDevice" 
    />
    
    <!-- 图表操作按钮 -->
    <ChartActions 
      v-if="showActions && hasData" 
      :hasData="hasData"
      @resetZoom="resetZoom"
      @exportChart="exportChart"
    />
    
    <!-- 图表容器 -->
    <div class="chart-wrapper" :style="{ height: `${height}px` }">
      <div class="chart-container">
        <canvas ref="chartCanvas" :id="chartId"></canvas>
      </div>
      <div class="chart-loading" v-if="loading">
        <i class="fas fa-spinner fa-spin"></i>
        <span>图表加载中...</span>
      </div>
      <div class="chart-empty" v-if="!loading && !hasData">
        <i class="fas fa-chart-line"></i>
        <p>暂无数据</p>
      </div>
    </div>
    
    <!-- 图表底部统计信息 -->
    <div class="chart-footer" v-if="showFooter">
      <div class="chart-stats" v-if="stats">
        <span v-for="(stat, key) in stats" :key="key" class="stat-item">
          <strong>{{ stat.label }}:</strong> {{ stat.value }}
        </span>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useChart } from '../../chart/composables/useChart';
import ChartStatsCard from '../../chart/components/ChartStatsCard.vue';
import ChartActions from '../../chart/components/ChartActions.vue';

export default {
  name: 'ChartComponent',
  components: { ChartStatsCard, ChartActions },
  props: {
    title: {
      type: String, default: ''
    },
    data: {
      type: Object, required: true, default: () => ({
        labels: [], datasets: []
      })
    },
    type: {
      type: String, default: 'bar', validator: (value) => {
        return ['bar', 'line', 'pie', 'doughnut', 'radar', 'polarArea', 'distribution'].includes(value);
      }
    },
    options: {
      type: Object, default: () => ({})
    },
    showHeader: {
      type: Boolean, default: true
    },
    showFooter: {
      type: Boolean, default: true
    },
    showActions: {
      type: Boolean, default: true
    },
    loading: {
      type: Boolean, default: false
    },
    stats: {
      type: Object, default: null
    },
    height: {
      type: Number, default: 500
    },
    enableZoom: {
      type: Boolean, default: true
    }
  },
  emits: ['chartReady', 'export', 'typeChange'],
  setup(props, { emit }) {
    // Canvas元素引用
    const chartCanvas = ref(null);
    const chartId = ref(`chart-${Date.now()}-${Math.floor(Math.random() * 1000)}`);
    
    // 使用图表管理composable
    const {
      hasData,
      distributionStats,
      distributionStatsByDevice,
      resetZoom,
      exportChart,
      mountChart,
      unmountChart
    } = useChart(props, emit, chartCanvas);
    
    // 组件挂载时初始化图表
    onMounted(() => {
      mountChart();
    });
    
    // 组件销毁前销毁图表
    onBeforeUnmount(() => {
      unmountChart();
    });
    
    return {
      chartCanvas,
      chartId,
      hasData,
      distributionStats,
      distributionStatsByDevice,
      resetZoom,
      exportChart
    };
  }
};
</script>

<style scoped>
.chart-component-container {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 24px;
  margin-bottom: 24px;
  box-sizing: border-box;
  width: 100%;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}

.chart-title {
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin: 0;
}

.chart-wrapper {
  position: relative;
  width: 100%;
  overflow: visible;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 0;
  box-sizing: border-box;
}

.chart-wrapper .chart-container {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: visible;
}

.chart-wrapper canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.chart-loading,
.chart-empty {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.8);
  color: #666;
  font-size: 16px;
  gap: 12px;
}

.chart-loading i {
  font-size: 32px;
  color: #1677FF;
  animation: spin 1s linear infinite;
}

.chart-empty i {
  font-size: 32px;
  color: #999;
  opacity: 0.5;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.chart-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.chart-stats {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.stat-item {
  font-size: 14px;
  color: #666;
}

.stat-item strong {
  color: #333;
}
</style>