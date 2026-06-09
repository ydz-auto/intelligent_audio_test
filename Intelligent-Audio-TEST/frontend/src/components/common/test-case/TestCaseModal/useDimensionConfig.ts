import { ref, computed } from 'vue';
import { useDimensions } from '../../../../composables/useDimensions';
import type { Dimension, DimensionConfig, AssociatedDimension } from './types';

export function useDimensionConfig() {
  const availableDimensions = ref<Dimension[]>([]);
  const dimensionSearchQuery = ref('');
  const showDimensionModal = ref(false);
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

  function isDimensionSelected(dimensionName: string, dimensions: DimensionConfig[]): boolean {
    return dimensions.some(dim => dim.name === dimensionName);
  }

  function toggleDimensionSelection(dimension: Dimension, dimensions: DimensionConfig[]) {
    const index = dimensions.findIndex(dim => dim.name === dimension.name);

    if (index > -1) {
      dimensions.splice(index, 1);
    } else {
      dimensions.push({
        id: dimension.id,
        name: dimension.name,
        weight: 50,
        threshold: 80
      });
    }
  }

  function openDimensionSelectModal(index: number) {
    currentDimensionIndex.value = index;
    showDimensionModal.value = true;
  }

  function handleDimensionSelect(dimension: Dimension, dimensions: DimensionConfig[]) {
    if (currentDimensionIndex.value !== null) {
      dimensions[currentDimensionIndex.value] = {
        ...dimensions[currentDimensionIndex.value],
        id: dimension.id,
        name: dimension.name
      };
    }
    showDimensionModal.value = false;
  }

  function addDimension(dimensions: DimensionConfig[]) {
    dimensions.push({ name: '', weight: 50, threshold: 80 });
  }

  function removeDimension(index: number, dimensions: DimensionConfig[]) {
    if (dimensions.length > 0) {
      dimensions.splice(index, 1);
    }
  }

  function convertDimensionIdsToObjects(dimensions: DimensionConfig[]) {
    for (let i = 0; i < dimensions.length; i++) {
      const dim = dimensions[i];
      if (typeof dim === 'string') {
        const dimension = availableDimensions.value.find(d => String(d.id) === dim);
        if (dimension) {
          dimensions[i] = { id: dimension.id, name: dimension.name, weight: 50, threshold: 80 };
        }
      }
    }
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
    currentDimensionIndex,
    associatedDimensions,
    filteredAvailableDimensions,
    filteredDimensions,
    loadDimensions,
    isDimensionSelected,
    toggleDimensionSelection,
    openDimensionSelectModal,
    handleDimensionSelect,
    addDimension,
    removeDimension,
    convertDimensionIdsToObjects,
    updateAssociatedDimensions
  };
}
