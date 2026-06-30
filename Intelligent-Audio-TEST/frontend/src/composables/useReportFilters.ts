import { ref, computed, type Ref } from 'vue';

export interface ReportFilterOptions {
  tagPageSize?: number;
  categoryPageSize?: number;
  metricPageSize?: number;
}

export function useReportFilters(options: ReportFilterOptions = {}) {
  const tagSearchQuery = ref('');
  const tagPage = ref(1);
  const tagPageSize = ref(options.tagPageSize || 50);

  const categorySearchQuery = ref('');
  const categoryPage = ref(1);
  const categoryPageSize = ref(options.categoryPageSize || 50);

  const metricSearchQuery = ref('');
  const metricPage = ref(1);
  const metricPageSize = ref(options.metricPageSize || 30);

  const createTagFilter = (source: Ref<string[]>) => {
    const filteredTags = computed(() => {
      if (!tagSearchQuery.value.trim()) {
        return source.value;
      }
      const query = tagSearchQuery.value.toLowerCase();
      return source.value.filter(tag => tag.toLowerCase().includes(query));
    });

    const totalTagPages = computed(() =>
      Math.ceil(filteredTags.value.length / tagPageSize.value) || 1
    );

    const paginatedTags = computed(() => {
      const start = (tagPage.value - 1) * tagPageSize.value;
      const end = start + tagPageSize.value;
      return filteredTags.value.slice(start, end);
    });

    return { filteredTags, totalTagPages, paginatedTags };
  };

  const createCategoryFilter = (source: Ref<string[]>) => {
    const filteredCategories = computed(() => {
      if (!categorySearchQuery.value.trim()) {
        return source.value;
      }
      const query = categorySearchQuery.value.toLowerCase();
      return source.value.filter(cat => cat.toLowerCase().includes(query));
    });

    const totalCategoryPages = computed(() =>
      Math.ceil(filteredCategories.value.length / categoryPageSize.value) || 1
    );

    const paginatedCategories = computed(() => {
      const start = (categoryPage.value - 1) * categoryPageSize.value;
      const end = start + categoryPageSize.value;
      return filteredCategories.value.slice(start, end);
    });

    return { filteredCategories, totalCategoryPages, paginatedCategories };
  };

  const createMetricFilter = (source: Ref<any[]>) => {
    const filteredMetrics = computed(() => {
      if (!metricSearchQuery.value.trim()) {
        return source.value;
      }
      const query = metricSearchQuery.value.toLowerCase();
      return source.value.filter(metric =>
        metric.name.toLowerCase().includes(query)
      );
    });

    const totalMetricPages = computed(() =>
      Math.ceil(filteredMetrics.value.length / metricPageSize.value) || 1
    );

    const paginatedMetrics = computed(() => {
      const start = (metricPage.value - 1) * metricPageSize.value;
      const end = start + metricPageSize.value;
      return filteredMetrics.value.slice(start, end);
    });

    return { filteredMetrics, totalMetricPages, paginatedMetrics };
  };

  const resetFilterState = () => {
    tagSearchQuery.value = '';
    tagPage.value = 1;
    categorySearchQuery.value = '';
    categoryPage.value = 1;
    metricSearchQuery.value = '';
    metricPage.value = 1;
  };

  return {
    tagSearchQuery,
    tagPage,
    tagPageSize,
    categorySearchQuery,
    categoryPage,
    categoryPageSize,
    metricSearchQuery,
    metricPage,
    metricPageSize,
    createTagFilter,
    createCategoryFilter,
    createMetricFilter,
    resetFilterState,
  };
}
