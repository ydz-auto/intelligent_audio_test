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
