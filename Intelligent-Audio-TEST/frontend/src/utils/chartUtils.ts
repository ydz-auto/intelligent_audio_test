import { Chart, ChartConfiguration } from 'chart.js/auto';
import { TaskStatus } from '@/domain/enums';

/**
 * 图表工具函数
 */

/**
 * 创建任务类型分布图表
 * @param ctx - Canvas上下文
 * @param typeCounts - 任务域全量类型派生分布 {api, e2e, mixed}（INT-200，后端 /tasks/stats 聚合）
 * @param options - 图表配置选项
 */
export function createTaskTypeChart(ctx: HTMLCanvasElement | CanvasRenderingContext2D, typeCounts: { api: number; e2e: number; mixed: number }, options: any = {})
{
  // 转换为图表数据格式
  const chartData = {
    labels: ['API测试', '端到端测试', '混合任务'],
    datasets: [{
      data: [typeCounts.api, typeCounts.e2e, typeCounts.mixed],
      backgroundColor: ['#FF6A00', '#1976D2', '#9C27B0'],
      borderColor: '#ffffff',
      borderWidth: 2,
      hoverOffset: 4
    }]
  };
  
  const config : ChartConfiguration = {
    type: 'doughnut', 
    data: chartData,
    options: {
      responsive: true, 
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            usePointStyle: true,
            padding: 8,
            font: {
              size: 10
            }
          }
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: 12,
          cornerRadius: 8,
          boxPadding: 8,
          usePointStyle: true
        }
      },
      animation: {
        duration: 0, // 禁用动画，避免切换时抖动
        easing: 'linear'
      },
      ...options
    }
  };

  return new Chart(ctx, config);
}

/**
 * 获取日期所在周数
 * @param date - 日期对象
 * @returns 周数
 */
function getWeekNumber(date: Date): number {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayNum = d.getDay() || 7;
  d.setDate(d.getDate() + 4 - dayNum);
  const yearStart = new Date(d.getFullYear(), 0, 1);
  return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

/**
 * 根据时间粒度格式化日期
 * @param date - 日期对象
 * @param granularity - 时间粒度
 * @returns 格式化后的日期字符串
 */
function formatDateByGranularity(date: Date, granularity: string): string {
  switch (granularity) {
    case 'day':
      return `${date.getMonth() + 1}/${date.getDate()}`;
    case 'week':
      const weekNumber = getWeekNumber(date);
      return `${date.getFullYear()}年第${weekNumber}周`;
    case 'month':
      return `${date.getFullYear()}/${date.getMonth() + 1}`;
    case 'year':
      return `${date.getFullYear()}`;
    default:
      return `${date.getMonth() + 1}/${date.getDate()}`;
  }
}

/**
 * 获取时间范围
 * @param granularity - 时间粒度
 * @returns 日期数组
 */
function getDateRange(granularity: string): Date[] {
  const dates: Date[] = [];
  const today = new Date();
  
  switch (granularity) {
    case 'day':
      // 过去30天
      for (let i = 29; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        dates.push(date);
      }
      break;
    case 'week':
      // 过去12周
      for (let i = 11; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i * 7);
        dates.push(date);
      }
      break;
    case 'month':
      // 过去12个月
      for (let i = 11; i >= 0; i--) {
        const date = new Date(today);
        date.setMonth(date.getMonth() - i);
        dates.push(date);
      }
      break;
    case 'year':
      // 过去5年
      for (let i = 4; i >= 0; i--) {
        const date = new Date(today);
        date.setFullYear(date.getFullYear() - i);
        dates.push(date);
      }
      break;
    default:
      // 默认过去30天
      for (let i = 29; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        dates.push(date);
      }
  }
  
  return dates;
}

/**
 * 创建任务完成趋势图表
 * @param ctx - Canvas上下文
 * @param trendBuckets - 完成任务按 createdAt 的分桶序列 [{key, count}]（INT-200，后端聚合）
 * @param options - 图表配置选项（granularity 需与后端分桶粒度一致）
 */
export function createTaskTrendChart(ctx: HTMLCanvasElement | CanvasRenderingContext2D, trendBuckets: { key: string; count: number }[], options: any = {})
{
  const granularity = options.granularity || 'day';

  // 后端分桶为稀疏序列（仅有数据的桶），按 key 索引后对时间轴补零
  const tasksByTime: Record<string, number> = {};
  trendBuckets.forEach(bucket => {
    tasksByTime[bucket.key] = bucket.count;
  });
  
  // 获取时间范围
  const dateRange = getDateRange(granularity);
  
  // 准备图表数据
  const labels: string[] = [];
  const data: number[] = [];
  
  dateRange.forEach(date => {
    let key;
    let label;

    switch (granularity) {
      case 'day':
        // INT-200：轴键改为本地日期（与后端 trend 分桶键一致）；
        // 原实现 toISOString 生成 UTC 日期键，与标签（本地日期）错位一天
        key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
        label = formatDateByGranularity(date, 'day');
        break;
      case 'week':
          const year = date.getFullYear();
          const weekNumber = getWeekNumber(date);
          key = `${year}-W${weekNumber}`;
          label = formatDateByGranularity(date, 'week');
          break;
      case 'month':
        key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        label = formatDateByGranularity(date, 'month');
        break;
      case 'year':
        key = `${date.getFullYear()}`;
        label = formatDateByGranularity(date, 'year');
        break;
      default:
        key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
        label = formatDateByGranularity(date, 'day');
    }
    
    labels.push(label);
    data.push(tasksByTime[key] || 0);
  });
  
  // 创建图表数据
  const chartData = {
    labels: labels,
    datasets: [{
      label: '完成任务数',
      data: data,
      fill: true,
      tension: 0.3,
      borderColor: '#FF6A00', // 使用橙色，与原HTML一致
      backgroundColor: 'rgba(255, 106, 0, 0.1)', // 橙色半透明背景
      borderWidth: 3,
      pointBackgroundColor: '#FF6A00',
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      pointRadius: 6
    }]
  };
  
  const config : ChartConfiguration = {
    type: 'line', 
    data: chartData,
    options: {
      responsive: true, 
      maintainAspectRatio: false, // 禁用自动调整宽高比，使用固定高度
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            font: {
              size: 10
            }
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.1)',
            drawBorder: false
          }
        },
        x: {
          grid: {
            display: true,
            color: 'rgba(0, 0, 0, 0.1)',
            drawBorder: false
          },
          ticks: {
            font: {
              size: 10
            }
          }
        }
      },
      plugins: {
        legend: {
          display: false // 隐藏图例
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: 12,
          cornerRadius: 8,
          boxPadding: 8,
          usePointStyle: true
        }
      },
      animation: {
        duration: 0, // 禁用动画，避免切换时抖动
        easing: 'linear'
      },
      interaction: {
        intersect: false,
        mode: 'index'
      },
      ...options
    }
  };

  return new Chart(ctx, config);
}

/**
 * 创建任务状态分布图表
 * @param ctx - Canvas上下文
 * @param statusCounts - 任务域全量状态计数（status → count，INT-200，后端 /tasks/stats 聚合）
 * @param options - 图表配置选项
 */
export function createTaskStatusChart(ctx: HTMLCanvasElement | CanvasRenderingContext2D, statusCounts: Record<string, number>, options: any = {})
{
  const countOf = (status: string) => statusCounts[status] ?? 0;

  // 转换为图表数据格式
  const chartData = {
    labels: ['待执行', '排队中', '执行中', '已完成', '执行失败'],
    datasets: [{
      label: '任务数量',
      data: [countOf(TaskStatus.PENDING), countOf(TaskStatus.QUEUED), countOf(TaskStatus.RUNNING), countOf(TaskStatus.COMPLETED), countOf(TaskStatus.FAILED)],
      backgroundColor: ['#1976D2', '#1976D2', '#FF6A00', '#52C41A', '#F5222D'], // 使用多种颜色
      borderColor: ['#1976D2', '#1976D2', '#FF6A00', '#52C41A', '#F5222D'],
      borderWidth: 2,
      borderRadius: 4
    }]
  };
  
  const config : ChartConfiguration = {
    type: 'bar', 
    data: chartData,
    options: {
      responsive: true, 
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            font: {
              size: 10
            }
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.1)',
            drawBorder: false
          }
        },
        x: {
          grid: {
            display: true,
            color: 'rgba(0, 0, 0, 0.1)',
            drawBorder: false
          },
          ticks: {
            font: {
              size: 10
            }
          }
        }
      },
      plugins: {
        legend: {
          display: false // 隐藏图例
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: 12,
          cornerRadius: 8,
          boxPadding: 8,
          usePointStyle: true
        }
      },
      animation: {
        duration: 0, // 禁用动画，避免切换时抖动
        easing: 'linear'
      },
      interaction: {
        intersect: false,
        mode: 'index'
      },
      ...options
    }
  };

  return new Chart(ctx, config);
}
