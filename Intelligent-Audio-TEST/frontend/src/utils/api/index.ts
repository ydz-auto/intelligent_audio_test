/**
 * API integration barrel module
 * Re-exports all API domain modules and core HTTP utilities
 */

// Core HTTP request utilities
export { request, apiBaseUrl, addRequestInterceptor, addResponseInterceptor, type RequestOptions } from './http';

// API domain modules
export { tasksApi } from './tasksApi';
export { logsApi } from './logsApi';
export { devicesApi } from './devicesApi';
export { playbackApi } from './playbackApi';
export { apisApi } from './apisApi';
export { audiosApi } from './audiosApi';
export { groupsApi } from './groupsApi';
export { testcasesApi } from './testcasesApi';
export { evaluationApi } from './evaluationApi';
export { reportsApi } from './reportsApi';
export { splApi } from './splApi';
export { statsApi } from './statsApi';
export { algorithmApi } from './algorithmApi';
export { tagsApi } from './tagsApi';

// Shared types (re-exported for backward compatibility with existing imports)
export type {
  AlgorithmDefinition,
  AlgorithmParam,
  AlgorithmGroup,
  ParamMapping,
  FormSchema,
  FormField,
  TagCategory,
  TagItem
} from '../../shared/types';

// Default export mapping (matches the original api.ts default export)
import { tasksApi } from './tasksApi';
import { logsApi } from './logsApi';
import { devicesApi } from './devicesApi';
import { playbackApi } from './playbackApi';
import { apisApi } from './apisApi';
import { audiosApi } from './audiosApi';
import { groupsApi } from './groupsApi';
import { testcasesApi } from './testcasesApi';
import { evaluationApi } from './evaluationApi';
import { reportsApi } from './reportsApi';
import { splApi } from './splApi';
import { statsApi } from './statsApi';
import { algorithmApi } from './algorithmApi';
import { tagsApi } from './tagsApi';

export default {
  tasks: tasksApi,
  logs: logsApi,
  devices: devicesApi,
  playback: playbackApi,
  apis: apisApi,
  audios: audiosApi,
  groups: groupsApi,
  testcases: testcasesApi,
  reports: reportsApi,
  spl: splApi,
  evaluation: evaluationApi,
  stats: statsApi,
  algorithm: algorithmApi,
  tags: tagsApi
};
