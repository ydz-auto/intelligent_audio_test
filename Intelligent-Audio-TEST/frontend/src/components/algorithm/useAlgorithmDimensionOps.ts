import { algorithmPort } from '../../composables/algorithm/algorithmPort'

export function useAlgorithmDimensionOps(
  formState: any,
  effectiveMode: any,
  paramIdCounter: { value: number }
) {
  function handleAddDimension() {
    formState.associatedDimensions.push({
      tempId: `temp_dim_${++paramIdCounter.value}`,
      dimensionId: null,
      weight: 1.0,
      isDefault: false
    })
  }

  function handleRemoveDimension(index: number) {
    const dim = formState.associatedDimensions[index]
    formState.associatedDimensions.splice(index, 1)
    if (effectiveMode.value === 'edit' && formState.type && dim) {
      if (dim.id) {
        algorithmPort.deleteDimensionRelation(dim.id).catch(err => {
          console.error('删除维度关联失败:', err)
        })
      } else if (dim.tempId) {
      }
    }
  }

  async function handleDimensionChange(index: number) {
    const dim = formState.associatedDimensions[index]
    if (!dim) return

    if (dim.isDefault) {
      formState.associatedDimensions.forEach((d: any, i: number) => {
        if (i !== index && d.id) {
          d.isDefault = false
          algorithmPort.updateDimensionRelation(d.id, { isDefault: false }).catch(err => {
            console.error('更新默认维度失败:', err)
          })
        }
      })
    }

    if (effectiveMode.value === 'edit' && formState.type && dim.id) {
      try {
        await algorithmPort.updateDimensionRelation(dim.id, {
          weight: dim.weight,
          isDefault: dim.isDefault
        })
      } catch (error) {
        console.error('自动保存维度关联失败:', error)
      }
    }
  }

  async function handleDimensionBlur(index: number) {
    const dim = formState.associatedDimensions[index]
    if (!dim) return

    if (dim.isDefault) {
      formState.associatedDimensions.forEach((d: any, i: number) => {
        if (i !== index && d.id) {
          d.isDefault = false
          algorithmPort.updateDimensionRelation(d.id, { isDefault: false }).catch(err => {
            console.error('更新默认维度失败:', err)
          })
        }
      })
    }

    if (effectiveMode.value === 'edit' && formState.type) {
      try {
        if (dim.id) {
          await algorithmPort.updateDimensionRelation(dim.id, {
            weight: dim.weight,
            isDefault: dim.isDefault,
            dimensionId: dim.dimensionId ?? undefined
          })
        } else if (dim.dimensionId) {
          const result = await algorithmPort.createDimensionRelation({
            algorithmType: formState.type,
            dimensionId: dim.dimensionId,
            weight: dim.weight,
            isDefault: dim.isDefault
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
