export interface TestCaseGroup {
  name?: string;
  group?: string;
  id?: string | number;
}

export interface TestCaseGroupItem {
  name?: string;
  group?: string;
  id?: string | number;
  [key: string]: unknown;
}

export interface GroupStat {
  name: string;
  total: number;
  api: number;
  e2e: number;
}

export interface Dimension {
  id: string | number;
  name: string;
  description?: string;
  type?: string;
}

export interface TestCase {
  id?: string | number;
  name?: string;
  group_name?: string;
  group?: string;
  groupName?: string;
  group_id?: string | number;
  groupId?: string | number;
  type?: string | string[];
  testType?: string | string[];
  config?: {
    audios?: AudioConfig[];
    dimensions?: {
      api: DimensionConfig[];
      e2e: DimensionConfig[];
    };
    backgroundNoise?: BackgroundNoiseConfig;
  };
}

export interface AudioItem {
  id: string | number;
  name: string;
  audioType?: string;
  tags?: string | string[];
}

export interface PlaybackDevice {
  id: string | number;
  name: string;
  channelIndex?: number;
}

export interface ImportPreviewItem {
  name: string;
  type: string;
  group: string;
  operation: 'update' | 'insert';
}

export interface ImportPreviewData {
  total: number;
  items: ImportPreviewItem[];
  audioConfigsCount: number;
  apiDimensionsCount: number;
  e2eDimensionsCount: number;
  tagsCount: number;
  groupsCount: number;
  sheetNames: string[];
}

export interface AudioConfig {
  audioId: string;
  testType: 'api' | 'e2e';
  playbackDeviceId: string;
  spl: number;
  playOrder: number;
}

export interface DimensionConfig {
  id?: string | number;
  name: string;
  weight: number;
  threshold: number;
}

export interface BackgroundNoiseConfig {
  audioId: string;
  deviceIds: string[];
  spl: number;
}

export interface TestCaseFormData {
  id?: string | number;
  name: string;
  description?: string;
  group?: string;
  groupId?: string | number;
  group_id?: string;
  groupName?: string;
  group_name?: string;
  tags?: string[];
  tagsInput?: string;
  translationDirectionId?: string | number | null;
  algorithmType?: string;
  algorithm_type?: string;
  algorithmParams?: Record<string, any>;
  algorithm_params?: Array<{ fieldCode: string; fieldValue: any }>;
  referenceParams?: Record<string, any>;
  reference_params?: Array<{ fieldCode: string; fieldValue: any }>;
  config: {
    audios: AudioConfig[];
    dimensions: {
      api: DimensionConfig[];
      e2e: DimensionConfig[];
    };
    backgroundNoise: BackgroundNoiseConfig;
  };
  _originalGroup?: string;
  _originalGroupId?: string;
}

export interface GroupFormData {
  name: string;
  description?: string;
  algorithmType?: string;
}

export interface ExportFormData {
  groups: string[];
  testType: string;
  format: string;
  includeConfig: boolean;
  includeDeleted: boolean;
}

export interface ImportFormData {
  file: File | null;
}

export interface AssociatedDimension {
  id: number;
  name: string;
  description?: string;
  type?: string;
  weight: number;
  is_default: boolean;
}

export interface AlgorithmOption {
  value: string;
  name: string;
  label?: string;
}
