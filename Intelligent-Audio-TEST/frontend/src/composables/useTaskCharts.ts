import { ref, type Ref } from 'vue';
import { Chart } from 'chart.js/auto';
import { createTaskTypeChart, createTaskTrendChart, createTaskStatusChart } from '../utils/chartUtils';
import type { Task } from '../shared/types';

/**
 * 任务图表组合式函数
 *
 * 职责：
 * - 创建任务类型/趋势/状态图表
 * - 更新图表实例
 * - 管理时间粒度切换
 */

export function useTaskCharts(tasks: Ref<Task[]>) {
  let typeChartInstance: Chart | null = null;
  let trendChartInstance: Chart | null = null;
  let statusChartInstance: Chart | null = null;

  const taskTypeChartRef = ref<HTMLCanvasElement | null>(null);
  const taskTrendChartRef = ref<HTMLCanvasElement | null>(null);
  const taskStatusChartRef = ref<HTMLCanvasElement | null>(null);

  const timeGranularity = ref('day');

  const createTaskTypeChartFn = (ctx: HTMLCanvasElement | null) => {
    if (!ctx) return;
    if (typeChartInstance) typeChartInstance.destroy();
    typeChartInstance = createTaskTypeChart(ctx, tasks.value);
  };

  const createTaskTrendChartFn = (ctx: HTMLCanvasElement | null, granularity: string = 'day') => {
    if (!ctx) return;
    if (trendChartInstance) trendChartInstance.destroy();
    trendChartInstance = createTaskTrendChart(ctx, tasks.value, { granularity });
  };

  const createTaskStatusChartFn = (ctx: HTMLCanvasElement | null) => {
    if (!ctx) return;
    if (statusChartInstance) statusChartInstance.destroy();
    statusChartInstance = createTaskStatusChart(ctx, tasks.value);
  };

  const updateCharts = () => {
    // 当任务数据更新时，重新创建所有图表实例
    if (taskTypeChartRef.value) {
      createTaskTypeChartFn(taskTypeChartRef.value);
    }
    if (taskTrendChartRef.value) {
      createTaskTrendChartFn(taskTrendChartRef.value, timeGranularity.value);
    }
    if (taskStatusChartRef.value) {
      createTaskStatusChartFn(taskStatusChartRef.value);
    }
  };

  const changeTimeGranularity = (granularity: string) => {
    timeGranularity.value = granularity;
    updateCharts();
  };

  const isActive = (granularity: string) => {
    return timeGranularity.value === granularity;
  };

  return {
    taskTypeChartRef,
    taskTrendChartRef,
    taskStatusChartRef,
    timeGranularity,
    createTaskTypeChart: createTaskTypeChartFn,
    createTaskTrendChart: createTaskTrendChartFn,
    createTaskStatusChart: createTaskStatusChartFn,
    updateCharts,
    changeTimeGranularity,
    isActive,
  };
}
