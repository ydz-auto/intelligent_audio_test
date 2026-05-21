type SnakeToCamelCase<S extends string> = S extends `${infer P}_${infer Q}` 
  ? `${P}${Capitalize<SnakeToCamelCase<Q>>}` 
  : S;

type CamelToSnakeCase<S extends string> = S extends `${infer P}${infer Q}` 
  ? P extends Uppercase<P> 
    ? `_${Lowercase<P>}${CamelToSnakeCase<Q>}` 
    : `${P}${CamelToSnakeCase<Q>}` 
  : S;

export function snakeToCamel<T extends string>(str: T): SnakeToCamelCase<T> {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()) as SnakeToCamelCase<T>;
}

export function camelToSnake<T extends string>(str: T): CamelToSnakeCase<T> {
  return str.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`) as CamelToSnakeCase<T>;
}

export function snakeToCamelObject<T extends Record<string, any>>(obj: T): Record<string, any> {
  if (obj === null || obj === undefined) {
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return obj.map(item => snakeToCamelObject(item));
  }
  
  if (typeof obj !== 'object') {
    return obj;
  }
  
  const result: Record<string, any> = {};
  
  for (const [key, value] of Object.entries(obj)) {
    const newKey = snakeToCamel(key);
    result[newKey] = snakeToCamelObject(value);
  }
  
  return result;
}

export function camelToSnakeObject<T extends Record<string, any>>(obj: T): Record<string, any> {
  if (obj === null || obj === undefined) {
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return obj.map(item => camelToSnakeObject(item));
  }
  
  if (typeof obj !== 'object') {
    return obj;
  }
  
  const result: Record<string, any> = {};
  
  for (const [key, value] of Object.entries(obj)) {
    const newKey = camelToSnake(key);
    result[newKey] = camelToSnakeObject(value);
  }
  
  return result;
}

export function normalizeReportSummary(summary: Record<string, any>): Record<string, any> {
  if (!summary) return summary;
  
  const fieldMappings: Record<string, string[]> = {
    totalCases: ['total_cases', 'totalCases'],
    completedCases: ['completed_cases', 'completedCases'],
    failedCases: ['failed_cases', 'failedCases'],
    passRate: ['pass_rate', 'passRate', 'overall_success_rate', 'overallSuccessRate'],
    avgScore: ['avg_score', 'avgScore'],
    allMetrics: ['all_metrics', 'allMetrics'],
    detailedResults: ['detailed_results', 'detailedResults'],
    deviceStats: ['device_stats', 'deviceStats'],
    apiStats: ['api_stats', 'apiStats'],
    metricData: ['metric_data', 'metricData'],
    tagMetricData: ['tag_metric_data', 'tagMetricData'],
    rawData: ['raw_data', 'rawData'],
    caseTypeStats: ['case_type_stats', 'caseTypeStats'],
    caseCategories: ['case_categories', 'caseCategories'],
    allCaseTags: ['all_case_tags', 'allCaseTags'],
    resourceHeaders: ['resource_headers', 'resourceHeaders'],
    dimensionValues: ['dimension_values', 'dimensionValues'],
    overallSuccessRate: ['overall_success_rate', 'overallSuccessRate', 'pass_rate', 'passRate'],
  };
  
  const normalized: Record<string, any> = { ...summary };
  
  for (const [camelKey, aliases] of Object.entries(fieldMappings)) {
    let value: any = undefined;
    
    for (const alias of aliases) {
      if (normalized[alias] !== undefined) {
        value = normalized[alias];
        break;
      }
    }
    
    if (value !== undefined) {
      normalized[camelKey] = value;
    }
  }
  
  if (normalized.deviceStats && Array.isArray(normalized.deviceStats)) {
    normalized.deviceStats = normalized.deviceStats.map(stat => snakeToCamelObject(stat));
  }
  
  if (normalized.apiStats && Array.isArray(normalized.apiStats)) {
    normalized.apiStats = normalized.apiStats.map(stat => snakeToCamelObject(stat));
  }
  
  return normalized;
}

export function normalizeReport(report: Record<string, any>): Record<string, any> {
  if (!report) return report;
  
  const normalized = { ...report };
  
  if (normalized.summary) {
    normalized.summary = normalizeReportSummary(normalized.summary);
  }
  
  const taskIdAliases = ['task_id', 'taskId'];
  for (const alias of taskIdAliases) {
    if (normalized[alias] !== undefined && normalized.taskId === undefined) {
      normalized.taskId = normalized[alias];
    }
  }
  
  const taskNameAliases = ['task_name', 'taskName'];
  for (const alias of taskNameAliases) {
    if (normalized[alias] !== undefined && normalized.taskName === undefined) {
      normalized.taskName = normalized[alias];
    }
  }
  
  const algorithmTypeAliases = ['algorithm_type', 'algorithmType'];
  for (const alias of algorithmTypeAliases) {
    if (normalized[alias] !== undefined && normalized.algorithmType === undefined) {
      normalized.algorithmType = normalized[alias];
    }
  }
  
  const createdAtAliases = ['created_at', 'createdAt'];
  for (const alias of createdAtAliases) {
    if (normalized[alias] !== undefined && normalized.createdAt === undefined) {
      normalized.createdAt = normalized[alias];
    }
  }
  
  const updatedAtAliases = ['updated_at', 'updatedAt'];
  for (const alias of updatedAtAliases) {
    if (normalized[alias] !== undefined && normalized.updatedAt === undefined) {
      normalized.updatedAt = normalized[alias];
    }
  }
  
  return normalized;
}

export function getFieldWithAliases(obj: Record<string, any>, primaryField: string, aliases: string[]): any {
  if (obj[primaryField] !== undefined) {
    return obj[primaryField];
  }
  
  for (const alias of aliases) {
    if (obj[alias] !== undefined) {
      return obj[alias];
    }
  }
  
  return undefined;
}
