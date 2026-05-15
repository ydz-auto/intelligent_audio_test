import { ref, computed } from 'vue';
import { useDimensions } from '../../../../composables/useDimensions';
import type { Dimension, DimensionConfig, AssociatedDimension } from './types';

export function useDimensionConfig() {
  const availableDimensions = ref<Dimension[]>([]);
  const dimensionSearchQuery = ref('');
  const showDimensionModal = ref(false);
  const currentDimensionType = ref<'api' | 'e2e'>('api');
  const currentDimensionIndex = ref<number | null>(null);
  const associatedDimensions = ref<AssociatedDimension[]>([]);

  const { fetchAllDimensions, fetchDimensionsByAlgorithmType } = useDimensions();

  async function loadDimensions(algorithmType?: string) {
    try {
      let dimensions;
      if (algorithmType) {
        dimensions = await fetchDimensionsByAlgorithmType(algorithmType);
      } else {
        dimensions = await fetchAllDimensions({ forceRefresh: true });
      }

      const uniqueDimensions: Dimension[] = [];
      const dimensionNames = new Set<string>();
      for (const dim of dimensions) {
        if (!dimensionNames.has(dim.name)) {
          dimensionNames.add(dim.name);
          uniqueDimensions.push(dim as Dimension);
        }
      }
      availableDimensions.value = uniqueDimensions;
    } catch (err) {
      console.error('加载评测维度失败:', err);
      availableDimensions.value = [];
    }
  }

  const filteredAvailableDimensions = computed(() => {
    if (!associatedDimensions.value || associatedDimensions.value.length === 0) {
      return availableDimensions.value;
    }
    const associatedIds = new Set(associatedDimensions.value.map(d => d.id));
    return availableDimensions.value.filter(dim => associatedIds.has(dim.id));
  });

  const filteredDimensions = computed(() => {
    if (!dimensionSearchQuery.value) return filteredAvailableDimensions.value;
    const query = dimensionSearchQuery.value.toLowerCase();
    return filteredAvailableDimensions.value.filter(dim =>
      dim.name.toLowerCase().includes(query) ||
      (dim.description && dim.description.toLowerCase().includes(query))
    );
  });

  function isDimensionSelected(dimensionName: string, dimensionType: 'api' | 'e2e', dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }): boolean {
    return dimensions[dimensionType].some(dim => dim.name === dimensionName);
  }

  function toggleDimensionSelection(dimension: Dimension, dimensionType: 'api' | 'e2e', dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    const dims = dimensions[dimensionType];
    const index = dims.findIndex(dim => dim.name === dimension.name);

    if (index > -1) {
      dims.splice(index, 1);
    } else {
      dims.push({
        id: dimension.id,
        name: dimension.name,
        weight: 50,
        threshold: 80
      });
    }
  }

  function openDimensionSelectModal(dimensionType: 'api' | 'e2e', index: number) {
    currentDimensionType.value = dimensionType;
    currentDimensionIndex.value = index;
    showDimensionModal.value = true;
  }

  function handleDimensionSelect(dimension: Dimension, dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    if (currentDimensionType.value === 'api' && currentDimensionIndex.value !== null) {
      dimensions.api[currentDimensionIndex.value] = {
        ...dimensions.api[currentDimensionIndex.value],
        id: dimension.id,
        name: dimension.name
      };
    } else if (currentDimensionType.value === 'e2e' && currentDimensionIndex.value !== null) {
      dimensions.e2e[currentDimensionIndex.value] = {
        ...dimensions.e2e[currentDimensionIndex.value],
        id: dimension.id,
        name: dimension.name
      };
    }
    showDimensionModal.value = false;
  }

  function addAPIDimension(dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    if (!dimensions.api) {
      dimensions.api = [];
    }
    dimensions.api.push({ name: '', weight: 50, threshold: 80 });
  }

  function removeAPIDimension(index: number, dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    if (dimensions.api && dimensions.api.length > 0) {
      dimensions.api.splice(index, 1);
    }
  }

  function addE2EDimension(dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    if (!dimensions.e2e) {
      dimensions.e2e = [];
    }
    dimensions.e2e.push({ name: '', weight: 50, threshold: 80 });
  }

  function removeE2EDimension(index: number, dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    if (dimensions.e2e && dimensions.e2e.length > 0) {
      dimensions.e2e.splice(index, 1);
    }
  }

  function convertDimensionIdsToObjects(dimensions: { api: DimensionConfig[]; e2e: DimensionConfig[] }) {
    dimensions.api = dimensions.api.map(dim => {
      if (typeof dim === 'string') {
        const dimension = availableDimensions.value.find(d => String(d.id) === dim);
        if (dimension) {
          return { id: dimension.id, name: dimension.name, weight: 50, threshold: 80 };
        }
      }
      return dim;
    });

    dimensions.e2e = dimensions.e2e.map(dim => {
      if (typeof dim === 'string') {
        const dimension = availableDimensions.value.find(d => String(d.id) === dim);
        if (dimension) {
          return { id: dimension.id, name: dimension.name, weight: 50, threshold: 80 };
        }
      }
      return dim;
    });
  }

  async function updateAssociatedDimensions(algorithmType: string) {
    if (!algorithmType) {
      associatedDimensions.value = [];
      return;
    }

    try {
      const dimensions = await fetchDimensionsByAlgorithmType(algorithmType);
      associatedDimensions.value = dimensions.map(d => ({
        id: d.id,
        name: d.name,
        type: (d as any).type,
        description: (d as any).description,
        weight: 50,
        is_default: false
      }));
    } catch (err) {
      console.error('加载关联维度失败:', err);
      associatedDimensions.value = [];
    }
  }

  return {
    availableDimensions,
    dimensionSearchQuery,
    showDimensionModal,
    currentDimensionType,
    currentDimensionIndex,
    associatedDimensions,
    filteredAvailableDimensions,
    filteredDimensions,
    loadDimensions,
    isDimensionSelected,
    toggleDimensionSelection,
    openDimensionSelectModal,
    handleDimensionSelect,
    addAPIDimension,
    removeAPIDimension,
    addE2EDimension,
    removeE2EDimension,
    convertDimensionIdsToObjects,
    updateAssociatedDimensions
  };
}
