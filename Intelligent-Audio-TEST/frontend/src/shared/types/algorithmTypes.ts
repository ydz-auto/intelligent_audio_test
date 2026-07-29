/**
 * Algorithm-related type definitions
 * Shared across API modules and UI components
 */

export interface AlgorithmDefinition {
  id?: number;
  type: string;
  name: string;
  group_id?: number;
  group_name?: string;
  description?: string;
  status: string;
  icon?: string;
  display_order: number;
  params?: AlgorithmParam[];
  mappings?: {
    device: ParamMapping[];
    api: ParamMapping[];
    evaluation: ParamMapping[];
  };
  created_at?: string;
  updated_at?: string;
}

export interface AlgorithmParam {
  id?: number;
  algorithm_type: string;
  param_code: string;
  param_name?: string;
  param_type: string;
  required: boolean;
  default_value?: string;
  validation_rules?: string;
  help_text?: string;
  component?: string;
  ui_order: number;
  ui_group: string;
  hidden: boolean;
}

export interface AlgorithmGroup {
  id?: number;
  name: string;
  description?: string;
  icon?: string;
  display_order: number;
  deleted?: boolean;
  created_at?: string;
  updated_at?: string;
  algorithm_count?: number;
}

export interface ParamMapping {
  id?: number;
  algorithm_type: string;
  component_type: 'device' | 'api' | 'evaluation';
  direction?: 'input' | 'output';
  field_type?: 'text' | 'audio' | 'number' | 'boolean' | 'json';
  source_param: string;
  target_key: string;
  mapped_from?: string;
  transform_type?: 'none' | 'uppercase' | 'lowercase' | 'json_parse' | 'base64' | 'rttm_to_obj' | 'stm_to_obj';
}

export interface FormSchema {
  algorithmType: string;
  algorithmName: string;
  group_id?: number;
  group_name?: string;
  description?: string;
  groups: {
    name: string;
    label: string;
    fields: FormField[];
  }[];
  fields: FormField[];
}

export interface FormField {
  fieldCode: string;
  fieldName: string;
  fieldType: string;
  required: boolean;
  defaultValue?: any;
  component?: string;
  options?: { value: string; label: string }[];
  validation?: string;
  helpText?: string;
  hidden: boolean;
  uiOrder: number;
  uiGroup: string;
  scope?: string;
}

export interface TagCategory {
  id: number;
  name: string;
  description?: string;
  color?: string;
  sortOrder: number;
  tagCount: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface TagItem {
  id: number;
  name: string;
  description?: string;
  color?: string;
  categoryId?: number;
  categoryName?: string;
  createdAt?: string;
  updatedAt?: string;
}
