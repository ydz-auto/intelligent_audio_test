export interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
}

export interface Dimension {
  id: number
  name: string
  code: string
  description?: string
  dimensionType?: string
  parentDimensionId?: number | null
}

export interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number
  group_name?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  device_params?: any[]
  api_params?: any[]
  case_params?: any[]
  params?: any[]
  mappings?: any
  associated_dimensions?: { dimension_id: number | null; weight: number; is_default: boolean }[]
}

export interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmRecord | null
}
