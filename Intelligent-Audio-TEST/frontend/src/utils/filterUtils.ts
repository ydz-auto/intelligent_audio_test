/**
 * 筛选和排序工具函数
 */

export interface TaskFilters {
  type: string;
  status: string;
  timeRange: string;
}

export interface CustomDateRange {
  start: string | null;
  end: string | null;
}

export interface SortConfig {
  field: string;
  order: 'asc' | 'desc';
}

/**
 * 筛选任务
 * @param tasks - 任务数据
 * @param filters - 筛选条件
 * @param searchTerm - 搜索关键词
 * @param selectedTags - 选中的标签集合
 * @param customDateRange - 自定义日期范围
 * @returns 筛选后的任务
 */
export function filterTasks(
  tasks: any[], 
  filters: TaskFilters, 
  searchTerm: string, 
  selectedTags: Set<string>, 
  customDateRange: CustomDateRange
): any[] {
  return tasks.filter(task => {
    if (task.logicDelete) return false;
    
    if (filters.type !== 'all' && task.type !== filters.type) return false;
    
    if (filters.status !== 'all' && task.status !== filters.status) return false;
    
    if (filters.timeRange !== 'all') {
      const taskDate = new Date(task.createdAt);
      const now = new Date();
      let timeLimit: Date | undefined;
      
      switch (filters.timeRange) {
        case 'today':
          timeLimit = new Date(now.setDate(now.getDate() - 1));
          break;
        case 'week':
          timeLimit = new Date(now.setDate(now.getDate() - 7));
          break;
        case 'month':
          timeLimit = new Date(now.setMonth(now.getMonth() - 1));
          break;
        case 'year':
          timeLimit = new Date(now.setFullYear(now.getFullYear() - 1));
          break;
        case 'custom':
          if (customDateRange.start && customDateRange.end) {
            const startDate = new Date(customDateRange.start);
            const endDate = new Date(customDateRange.end);
            if (taskDate < startDate || taskDate > endDate) return false;
          }
          break;
      }
      
      if (filters.timeRange !== 'custom' && timeLimit && taskDate < timeLimit) {
        return false;
      }
    }
    
    if (searchTerm) {
      const searchLower = searchTerm.toLowerCase();
      const matchesName = task.name.toLowerCase().includes(searchLower);
      const matchesDescription = (task.description || '').toLowerCase().includes(searchLower);
      const matchesId = String(task.id).toLowerCase().includes(searchLower);
      
      if (!matchesName && !matchesDescription && !matchesId) return false;
    }
    
    if (selectedTags.size > 0) {
      const taskTags = new Set(task.tags || []);
      const hasAllTags = [...selectedTags].every(tag => taskTags.has(tag));
      if (!hasAllTags) return false;
    }
    
    return true;
  });
}

/**
 * 排序任务
 * @param tasks - 任务数据
 * @param sortConfig - 排序配置 { field, order }
 * @returns 排序后的任务
 */
export function sortTasks(tasks: any[], sortConfig: SortConfig): any[] {
  const sortedTasks = [...tasks];
  
  sortedTasks.sort((a, b) => {
    const valA = a[sortConfig.field];
    const valB = b[sortConfig.field];
    
    if (valA < valB) {
      return sortConfig.order === 'asc' ? -1 : 1;
    }
    if (valA > valB) {
      return sortConfig.order === 'asc' ? 1 : -1;
    }
    return 0;
  });
  
  return sortedTasks;
}

/**
 * 时间范围 → 后端 start_date/end_date 参数（日常/发布/合并三视图统一）
 * @param timeRange - 时间范围选项 (all/today/yesterday/week/month/custom)
 * @param customRange - 自定义日期范围
 */
export function buildTimeRangeParams(
  timeRange: string,
  customRange: { start: string; end: string }
): Record<string, string> {
  const params: Record<string, string> = {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  switch (timeRange) {
    case 'today':
      params.start_date = today.toISOString();
      break;
    case 'yesterday': {
      const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
      params.start_date = yesterday.toISOString();
      params.end_date = today.toISOString();
      break;
    }
    case 'week': {
      const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
      params.start_date = weekAgo.toISOString();
      break;
    }
    case 'month': {
      const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
      params.start_date = monthAgo.toISOString();
      break;
    }
    case 'custom':
      if (customRange.start) params.start_date = new Date(customRange.start).toISOString();
      if (customRange.end) {
        const end = new Date(customRange.end);
        end.setHours(23, 59, 59, 999);
        params.end_date = end.toISOString();
      }
      break;
  }
  return params;
}
