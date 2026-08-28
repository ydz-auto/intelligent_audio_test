import { ref } from 'vue'

export function useAlgorithmMappingOps(formState: any) {
  const mappingExpanded = ref<Record<string, boolean>>({
    device: true,
    api: true,
    evaluation: true
  })

  function updateMappings(componentType: 'device' | 'api' | 'evaluation', mappings: any[]) {
    formState.mappings[componentType] = mappings
    console.log('更新映射:', componentType, mappings)
  }

  function toggleMapping(key: 'device' | 'api' | 'evaluation') {
    mappingExpanded.value[key] = !mappingExpanded.value[key]
  }

  return {
    mappingExpanded,
    updateMappings,
    toggleMapping,
  }
}
