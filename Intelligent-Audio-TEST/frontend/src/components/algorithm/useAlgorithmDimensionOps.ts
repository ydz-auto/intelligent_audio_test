import { algorithmApi } from '../../utils/api'

export function useAlgorithmDimensionOps(
  formState: any,
  effectiveMode: any,
  paramIdCounter: { value: number }
) {
  function handleAddDimension() {
    formState.associated_dimensions.push({
      tempId: `temp_dim_${++paramIdCounter.value}`,
      dimension_id: null,
      weight: 1.0,
      is_default: false
    })
  }

  function handleRemoveDimension(index: number) {
    const dim = formState.associated_dimensions[index]
    formState.associated_dimensions.splice(index, 1)
    if (effectiveMode.value === 'edit' && formState.type && dim) {
      if (dim.id) {
        algorithmApi.deleteDimensionRelation(dim.id).catch(err => {
          console.error('删除维度关联失败:', err)
        })
      } else if (dim.tempId) {
      }
    }
  }

  async function handleDimensionChange(index: number) {
    const dim = formState.associated_dimensions[index]
    if (!dim) return

    if (dim.is_default) {
      formState.associated_dimensions.forEach((d: any, i: number) => {
        if (i !== index && d.id) {
          d.is_default = false
          algorithmApi.updateDimensionRelation(d.id, { is_default: false }).catch(err => {
            console.error('更新默认维度失败:', err)
          })
        }
      })
    }

    if (effectiveMode.value === 'edit' && formState.type && dim.id) {
      try {
        await algorithmApi.updateDimensionRelation(dim.id, {
          weight: dim.weight,
          is_default: dim.is_default
        })
      } catch (error) {
        console.error('自动保存维度关联失败:', error)
      }
    }
  }

  async function handleDimensionBlur(index: number) {
    const dim = formState.associated_dimensions[index]
    if (!dim) return

    if (dim.is_default) {
      formState.associated_dimensions.forEach((d: any, i: number) => {
        if (i !== index && d.id) {
          d.is_default = false
          algorithmApi.updateDimensionRelation(d.id, { is_default: false }).catch(err => {
            console.error('更新默认维度失败:', err)
          })
        }
      })
    }

    if (effectiveMode.value === 'edit' && formState.type) {
      try {
        if (dim.id) {
          await algorithmApi.updateDimensionRelation(dim.id, {
            weight: dim.weight,
            is_default: dim.is_default,
            dimension_id: dim.dimension_id
          })
        } else if (dim.dimension_id) {
          const result = await algorithmApi.createDimensionRelation({
            algorithm_type: formState.type,
            dimension_id: dim.dimension_id,
            weight: dim.weight,
            is_default: dim.is_default
          })
          dim.id = result.id
          dim.tempId = undefined
        }
      } catch (error) {
        console.error('自动保存维度关联失败:', error)
      }
    }
  }

  return {
    handleAddDimension,
    handleRemoveDimension,
    handleDimensionChange,
    handleDimensionBlur,
  }
}
