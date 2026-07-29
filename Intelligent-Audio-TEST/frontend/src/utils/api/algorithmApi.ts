/**
 * Algorithm API module
 */
import type {
  AlgorithmDefinition,
  AlgorithmParam,
  AlgorithmGroup,
  ParamMapping,
  FormSchema
} from '../../shared/types';
import { request, type RequestOptions } from './http';

export const algorithmApi = {
  async getDefinitions(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ data: AlgorithmDefinition[]; total: number }>('GET', '/algorithm/definitions', null, { ...options, params });
  },

  async getDefinition(algoType: string) {
    return request<AlgorithmDefinition>('GET', `/algorithm/definitions/${algoType}`);
  },

  async createDefinition(data: Partial<AlgorithmDefinition>) {
    return request<AlgorithmDefinition>('POST', '/algorithm/definitions', data);
  },

  async updateDefinition(algoType: string, data: Partial<AlgorithmDefinition>) {
    return request<AlgorithmDefinition>('PUT', `/algorithm/definitions/${algoType}`, data);
  },

  async deleteDefinition(algoType: string) {
    return request<void>('DELETE', `/algorithm/definitions/${algoType}`);
  },

  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ data: AlgorithmGroup[]; total: number }>('GET', '/algorithm/groups', null, { ...options, params });
  },

  async getGroup(groupId: number) {
    return request<AlgorithmGroup>('GET', `/algorithm/groups/${groupId}`);
  },

  async createGroup(data: Partial<AlgorithmGroup>) {
    return request<AlgorithmGroup>('POST', '/algorithm/groups', data);
  },

  async updateGroup(groupId: number, data: Partial<AlgorithmGroup>) {
    return request<AlgorithmGroup>('PUT', `/algorithm/groups/${groupId}`, data);
  },

  async deleteGroup(groupId: number) {
    return request<void>('DELETE', `/algorithm/groups/${groupId}`);
  },

  async getParams(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ parameters: AlgorithmParam[]; total: number }>('GET', '/algorithm/params', null, { ...options, params });
  },

  async getParam(paramId: number) {
    return request<AlgorithmParam>('GET', `/algorithm/params/${paramId}`);
  },

  async createParam(data: Partial<AlgorithmParam>) {
    return request<AlgorithmParam>('POST', '/algorithm/params', data);
  },

  async updateParam(paramId: number, data: Partial<AlgorithmParam>) {
    return request<AlgorithmParam>('PUT', `/algorithm/params/${paramId}`, data);
  },

  async deleteParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/params/${paramId}`);
  },

  async getMappings(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ mappings: ParamMapping[]; total: number }>('GET', '/algorithm/mappings', null, { ...options, params });
  },

  async createMapping(data: Partial<ParamMapping>) {
    return request<ParamMapping>('POST', '/algorithm/mappings', data);
  },

  async updateMapping(mappingId: number, data: Partial<ParamMapping>) {
    return request<ParamMapping>('PUT', `/algorithm/mappings/${mappingId}`, data);
  },

  async deleteMapping(mappingId: number) {
    return request<void>('DELETE', `/algorithm/mappings/${mappingId}`);
  },

  async getOptions() {
    return request<{ algorithms: { value: string; name: string; group_id?: number; group_name?: string; icon?: string }[] }>('GET', '/algorithm/options');
  },

  async getFormSchema(algoType: string) {
    return request<FormSchema>('GET', `/algorithm/form-schema/${algoType}`);
  },

  async getDimensions(algoType: string) {
    return request<{
      dimensions: Array<{ id: number; name: string; description?: string; type?: string; weight: number; is_default: boolean }>;
      dimension_ids: number[];
      default_dimension_id: number | null;
      weights: Record<number, number>;
    }>('GET', `/algorithm/dimensions/${algoType}`);
  },

  async associateDimensions(algoType: string, dimensions: Array<{ dimension_id: number; weight?: number; is_default?: boolean }>) {
    return request<void>('POST', `/algorithm/dimensions/${algoType}`, { dimensions });
  },

  async createDimensionRelation(data: { algorithm_type: string; dimension_id: number; weight?: number; is_default?: boolean }) {
    return request<{ id: number; algorithm_type: string; dimension_id: number; weight: number; is_default: boolean }>('POST', '/algorithm/dimension-relations', data);
  },

  async updateDimensionRelation(relationId: number, data: { weight?: number; is_default?: boolean; dimension_id?: number }) {
    return request<{ id: number; algorithm_type: string; dimension_id: number; weight: number; is_default: boolean }>('PUT', `/algorithm/dimension-relations/${relationId}`, data);
  },

  async deleteDimensionRelation(relationId: number) {
    return request<void>('DELETE', `/algorithm/dimension-relations/${relationId}`);
  },

  async reloadConfig() {
    return request<{ success: boolean; message: string; reload_time: string }>('POST', '/algorithm/reload');
  },

  async importAlgorithms(data: { algorithms: any[] }) {
    return request<{ imported: string[] }>('POST', '/algorithm/import', data);
  },

  async bulkDelete(algorithmTypes: string[]) {
    return request<{ deleted_types: string[] }>('POST', '/algorithm/bulk-delete', { algorithm_types: algorithmTypes });
  },

  async extractParams(caseConfig: Record<string, any>) {
    return request<Record<string, any>>('POST', '/algorithm/extract-params', { case_config: caseConfig });
  },

  async getDimensionParams(dimensionId: number) {
    return request<{ params: Array<{ id: number; code: string; name: string; label: string; field_type: string; required: boolean; default_value: any }> }>('GET', `/algorithm/dimension-params/${dimensionId}`);
  },

  async getCaseParams(algorithmType: string, scope?: string, options: RequestOptions = {}) {
    const params: Record<string, any> = {};
    if (algorithmType) params.algorithm_type = algorithmType;
    if (scope) params.scope = scope;
    return request<{ parameters: any[]; total: number }>('GET', '/algorithm/case-params', null, { ...options, params });
  },

  async getCaseParam(paramId: number) {
    return request<any>('GET', `/algorithm/case-params/${paramId}`);
  },

  async createCaseParam(data: Partial<any>) {
    return request<any>('POST', '/algorithm/case-params', data);
  },

  async updateCaseParam(paramId: number, data: Partial<any>) {
    return request<any>('PUT', `/algorithm/case-params/${paramId}`, data);
  },

  async deleteCaseParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/case-params/${paramId}`);
  },

  async getReferenceParams(algoType: string, options: RequestOptions = {}) {
    return request<{ data: any[]; total: number }>('GET', '/algorithm/reference-params', null, { ...options, params: { algorithm_type: algoType } });
  },

  async getReferenceParam(paramId: number, algoType: string) {
    return request<any>('GET', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
  },

  async createReferenceParam(data: Partial<any>) {
    return request<any>('POST', '/algorithm/reference-params', data);
  },

  async updateReferenceParam(paramId: number, algoType: string, data: Partial<any>) {
    const bodyData = { ...data, algorithm_type: algoType };
    return request<any>('PUT', `/algorithm/reference-params/${paramId}`, bodyData);
  },

  async deleteReferenceParam(paramId: number, algoType: string) {
    return request<void>('DELETE', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
  }
};
