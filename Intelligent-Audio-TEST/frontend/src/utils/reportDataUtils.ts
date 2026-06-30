export const getValidResources = (data: any): any[] => {
  const resources = [
    data.resources,
    data.devices,
    data.apis,
    data.summary?.resources,
    data.summary?.apis,
    data.summary?.devices
  ];

  for (const resource of resources) {
    if (Array.isArray(resource) && resource.length > 0) {
      return resource;
    }
  }
  return [];
};

export const processTags = (tags: any): string[] => {
  if (!tags) return [];
  if (!Array.isArray(tags)) return [];
  return tags.map((tag: any) => typeof tag === 'object' ? tag.name : tag);
};

export const processCategories = (categories: any): string[] => {
  if (!categories) return [];
  if (!Array.isArray(categories)) return [];
  return categories.map((cat: any) => typeof cat === 'object' ? cat.name : cat);
};

export const extractTagsFromReport = (reportData: any): string[] => {
  const tags = reportData.allTags ||
    reportData.summary?.allTags ||
    reportData.allCaseTags ||
    reportData.summary?.allCaseTags || [];
  return processTags(tags);
};

export const extractCategoriesFromReport = (reportData: any): string[] => {
  const categories = reportData.caseCategories ||
    reportData.summary?.caseCategories ||
    reportData.categories ||
    reportData.summary?.categories || [];
  return processCategories(categories);
};

export const buildMetricDecimalPlacesMap = (allMetrics: any[]): Record<string, number> => {
  const map: Record<string, number> = {};
  const list = Array.isArray(allMetrics) ? allMetrics : [];
  list.forEach((m: any) => {
    if (!m || !m.name) return;
    const dp = m.decimalPlaces ?? m.decimal_places;
    if (Number.isInteger(dp) && dp >= 0) map[String(m.name)] = dp;
  });
  return map;
};

export const formatMetricForDisplay = (
  metricName: string,
  value: any,
  decimalPlacesMap?: Record<string, number>
): string => {
  if (value === '-' || value === null || value === undefined) return '-';
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  const dp = decimalPlacesMap?.[metricName];
  if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp);
  return String(num);
};
