import type { TestCaseConfig } from '../../components/common/test-case/TestCaseModal/types';

export type TaskType = 'api' | 'e2e' | 'playback' | 'evaluation' | 'report' | 'task' | 'execution' | 'comparison' | 'performance' | 'stress' | 'audio_import';
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'stopped' | 'queued' | 'skipped';

export interface Task {
    id: string | number;
    name: string;
    type: TaskType;
    status: TaskStatus;
    progress: number;
    description?: string;
    createdAt: string;
    updatedAt: string;
    finishedAt?: string;
    error?: string;
    config?: Record<string, any>;
    result?: any;
    tags?: string[];
    caseCount?: number;
    completedCount?: number;
    failedCount?: number;
    totalCases?: number;
    completedCases?: number;
    failedCases?: number;
    deviceCount?: number;
    deleted?: boolean;
    algorithmType?: string;
    algorithmParams?: Record<string, any>;
}

export interface AudioInfo {
    id: string | number;
    name: string;
    filename: string;
    filepath: string;
    size: number;
    duration: number;
    format: string;
    sampleRate: number;
    channels: number;
    type: 'dry' | 'noise' | 'prompt' | 'mixed';
    audioType?: 'dry' | 'noise' | 'prompt' | 'mixed';
    tags?: string[];
    createdAt: string;
    asrText?: string;
    translations?: Array<{ text: string, direction: string }>;
}

export type Audio = AudioInfo;

export interface AudioUploadFile {
    file: File;
    id: string;
    fileId: string;
    name: string;
    size: number;
    progress: number;
    status: 'pending' | 'uploading' | 'completed' | 'failed' | 'paused' | 'stopped';
    error?: string;
    md5?: string;
    uploadedSize?: number;
    totalChunks?: number;
    chunkSize?: number;
    uploadedChunks?: number[];
    audioId?: string | number;
    folderGroupName?: string;
    asrText?: string;
    translations?: Array<{ text: string, direction: string }>;
    annotations?: Array<{
        format: string;
        name: string;
        data: any;
        source_language?: string;
        target_language?: string;
    }>;
}

export interface AudioUploadTask {
    id: string;
    files: AudioUploadFile[];
    options: AudioUploadOptions;
    progress: number;
    status: 'pending' | 'running' | 'uploading' | 'completed' | 'failed' | 'paused' | 'stopped';
    totalFiles?: number;
    completedFiles?: number;
    failedFiles?: number;
    totalSize?: number;
    uploadedSize?: number;
    startTime?: string;
    endTime?: string;
}

export interface AudioUploadOptions {
    audioType: 'dry' | 'noise' | 'prompt' | 'mixed';
    createTestCase: boolean;
    tags: string[];
    description?: string;
    testTypes: ('api' | 'e2e')[];
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    playbackDeviceId?: string | number | null;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    spl?: number;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    noiseAudioId?: string | number | null;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    noiseSpl?: number;
    inheritTags?: boolean;
    dimensions?: EvaluationDimensionsConfig;
    algorithmType?: string;
    algorithmRelations?: Array<{
        algorithmType: string;
        isPrimary: boolean;
        weight: number;
        params?: Record<string, any>;
    }>;
    algorithmParams?: Record<string, any>;
    promptDeviceId?: string | number | null;
    promptSourceLanguage?: string;
    promptTargetLanguage?: string;
    promptTranslationDirection?: string;
    promptAlgorithmType?: string;
}

export interface SelectedEvaluationDimension {
    id: number | string;
    name: string;
    weight?: number;
    threshold?: number;
}

export interface EvaluationDimensionsConfig {
    dimensions: SelectedEvaluationDimension[];
}

export interface Tag {
    id: number;
    name: string;
    description?: string;
    createdAt?: string;
}

export interface TestCase {
    id: string | number;
    name: string;
    description?: string;
    type?: string;
    testType?: string;
    test_type?: 'api' | 'e2e';
    config?: TestCaseConfig;
    groupId?: string | number;
    groupName?: string;
    tags?: string[] | { id: number; name: string }[];
    algorithmType?: string;
    createdAt?: string;
    updatedAt?: string;
    deleted?: boolean;
    totalDuration?: number;
}

export interface APIConfig {
    id: string | number;
    name: string;
    vendor?: string;
    apiUrl?: string;
    method?: string;
    status: 'online' | 'offline' | 'busy' | 'error';
    healthScore?: number;
    apiEndpoints?: any[];
    apiSettings?: Record<string, any>;
    algorithmType?: string;
    createdAt?: string;
    updatedAt?: string;
    currentConcurrent?: number;
    maxConcurrent?: number;
    queueLength?: number;
    avgResponseTime?: number;
}

export interface PlaybackDevice {
    id: string | number;
    name: string;
    model?: string;
    type: 'speaker' | 'headphone' | 'lineout' | 'noise' | 'dry';
    deviceType?: string;
    sampleRate?: number;
    channelIndex?: number;
    deviceUniqueId?: string;
    status: 'online' | 'offline' | 'busy' | 'error' | 'available' | 'unavailable' | 'testing';
    currentSplMappingId?: number | null;
    selected?: boolean;
    createdAt?: string;
    updatedAt?: string;
}

export interface AlgorithmAssociation {
    algorithmType: string;
    isDefault: boolean;
    weight: number;
}

export interface LlmJudgeConfig {
    model?: string;
    promptTemplate?: string;
    maxTokens?: number;
    temperature?: number;
}

export interface Dimension {
    id: number | string;
    name: string;
    description?: string;
    keywords?: string;
    dimensionType?: 'main' | 'sub';
    parentDimensionId?: number | null;
    taskTypeCode?: string;
    categoryId?: number;
    apiUrl?: string;
    apiEndpoints?: DimensionAPIEndpoint[];
    apiSettings?: Record<string, any> | string;
    apiStatus?: string;
    type?: string;
    resultType?: string | number;
    resultMin?: number;
    resultMax?: number;
    decimalPlaces?: number;
    weight?: number;
    estimatedExecTime?: number;
    rule?: any;
    requiredInputs?: string;
    associatedAlgorithms?: AlgorithmAssociation[];
    status?: string;
    createdAt?: string;
    updatedAt?: string;
    scoreUnit?: string;
    llmJudgeConfig?: LlmJudgeConfig;
}

export interface EvaluationCategory {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    createdAt?: string;
    updatedAt?: string;
}

export interface DimensionAPIEndpoint {
    url: string;
    name: string;
    priority: number;
    maxProcess: number;
    maxTimeout: number;
    maxAudioDuration: number;
}

export type EvaluationDimension = Dimension;

export interface Report {
    id: string | number;
    name: string;
    type: TaskType;
    status: 'completed' | 'failed' | 'running' | 'draft' | 'final' | 'published';
    createdAt: string;
    updatedAt?: string;
    taskId?: string | number;
    taskName?: string;
    algorithmType?: string;
    description?: string;
    summary?: ReportSummary;
    detailedResults?: DetailedResult[];
    conclusion?: string;
    title?: string;
}

export interface ComparisonDevice {
    id: string | number;
    name: string;
    type: '设备' | 'API';
    selected: boolean;
    version?: string;
}

export interface DeviceAPIComparisonItem {
    id: string | number;
    name: string;
    type: '设备' | 'API';
    version: string;
    status: string;
    totalCases: number;
    successRate: number;
    avgResponseTime: number;
    stability: number;
}

export interface CaseExecutionItem {
    id: string | number;
    name: string;
    total: number;
    executed: number;
    completed: number;
    failed: number;
    successRate: number;
    failedRate: number;
}

export interface Device {
    id: string | number;
    name: string;
    keywords?: string;
    type?: string;
    model?: string;
    status?: string;
    selected?: boolean;
    createdAt?: string;
    updatedAt?: string;
}

export interface StatItem {
    label: string;
    value: number | string;
}

export interface ReportListParams {
    page: number;
    perPage: number;
    sortBy: string;
    order: 'asc' | 'desc';
    [key: string]: any;
}

export interface ReportMetricValue {
    id?: number;
    metric: string;
    value: number;
}

export interface ReportMetricValues {
    metric: string;
    values: number[];
}

export interface ReportRawDataGroup {
    resource: string;
    metrics: ReportMetricValues[];
}

export interface ReportMetricCategoryGroup {
    categoryId: string;
    categoryName: string;
    metrics: ReportMetricValue[];
}

export interface ReportMetricByResource {
    resource: string;
    categories: ReportMetricCategoryGroup[];
}

export interface ReportTagMetricTagGroup {
    tagId: string;
    tagName: string;
    metrics: ReportMetricValue[];
}

export interface ReportTagMetricByResource {
    resource: string;
    tags: ReportTagMetricTagGroup[];
}

export interface ReportCaseTypeStatRow {
    groupId: string;
    groupName: string;
    metrics: Array<{ metric: string; value: number }>;
}

export interface ReportMetricConfig {
    id?: string | number;
    name: string;
    unit?: string;
    decimalPlaces?: number;
    decimal_places?: number;
}

export interface ReportSummary {
    totalCases: number;
    passedCases: number;
    failedCases: number;
    passRate: number;
    avgScore: number;
    allMetrics?: ReportMetricConfig[];
    detailedResults?: any[];
    deviceStats?: any[];
    apiStats?: any[];
    metrics?: Record<string, any>;
    rawData?: ReportRawDataGroup[];
    metricData?: ReportMetricByResource[];
    tagMetricData?: ReportTagMetricByResource[];
    caseTypeStats?: ReportCaseTypeStatRow[];
    overallSuccessRate?: number;
    stability?: number;
    dimensionValues?: Record<string, any>;
    devices?: Array<string | {
        id: string | number;
        name: string;
        model?: string;
        description?: string;
        type?: string;
        system?: string;
        systemVersion?: string;
        appName?: string;
        appVersion?: string;
        location?: string;
        maxAudioDuration?: number;
        needsPromptAudio?: boolean;
        connectionType?: string;
        keywords?: string;
        serialNumber?: string;
        ip?: string;
        status?: string;
        lastOnlineAt?: string;
        createdAt?: string;
        updatedAt?: string;
    }>;
    apis?: Array<string | {
        id: string | number;
        name: string;
        vendor?: string;
        apiUrl?: string;
        description?: string;
        status?: string;
        maxProcess?: number;
        maxTimeout?: number;
        maxAudioDuration?: number;
        healthScore?: number;
        createdAt?: string;
        updatedAt?: string;
    }>;
    [key: string]: any;
}

export interface DetailedResult {
    id: string | number;
    caseName: string;
    score: number;
    result: string;
    [key: string]: any;
}

export interface CompareResult {
    reportIds: (string | number)[];
    differences: any[];
    [key: string]: any;
}

export interface Log {
    id: number;
    level: string;
    module?: string;
    category?: string;
    source?: string;
    content: string;
    time?: string | number;
    timestamp?: string | number;
    createdAt: string;
    taskId?: number | string;
    deviceId?: number;
    threadId?: string | number;
    mark?: string;
    testCaseId?: string | number;
    algorithmType?: string;
}

export interface LogFilters {
    startDateTime: string;
    endDateTime: string;
    logCategory: string;
    logModule: string;
    markFilter: string;
    algorithmType: string;
}

export interface AdvancedLogFilters {
    deviceId?: string;
    taskId?: string;
    userId?: string;
    threadId?: string;
    contentInclude?: string;
    contentExclude?: string;
}

export interface LogStats {
    total: number;
    error: number;
    warning: number;
    info: number;
}

export interface LogQueryParams extends AdvancedLogFilters {
    keyword?: string;
    startTime?: string;
    endTime?: string;
    category?: string;
    module?: string;
    mark?: string;
    level?: string;
    page?: number;
    perPage?: number;
    algorithmType?: string;
    test_case_id?: string;
}

export interface LogLevelOption {
    value: string;
    label: string;
    color?: string;
}

export interface APIHealthResult {
    success: boolean;
    latency?: number;
    status?: string;
    error?: string;
    endpoints?: APIEndpointHealthResult[];
}

export interface APIEndpointHealthResult {
    url: string;
    name: string;
    success: boolean;
    latency: number;
    error?: string;
}

export interface APISettings {
    timeout?: number;
    retry?: number;
    [key: string]: any;
}

export interface APIHealthResultModalData {
    dimension: EvaluationDimension;
    results: APIHealthResult;
}

export interface TestCaseGroup {
    id: string | number;
    name: string;
    description?: string;
    createdAt?: string;
    updatedAt?: string;
}

export interface CalibrationPoint {
    input: number;
    output: number;
    splValue: number;
    gain?: number;
    spl?: number;
    measuredSpl?: number;
    targetSpl?: number;
    frequency?: number;
    db?: number;
    linearGain?: number;
    createdAt?: string;
}

export interface CalibrationData {
    id: string | number;
    mappingId: string | number;
    points: CalibrationPoint[];
    createdAt?: string;
    updatedAt?: string;
    method?: string;
    notes?: string;
    minDb?: number;
    maxDb?: number;
    mode?: 'linear' | 'db_curve';
}

export interface SPLMapping {
    id: string | number;
    name: string;
    description?: string;
    deviceId: string | number;
    device?: PlaybackDevice;
    distance?: number;
    testFrequency?: number;
    calibrationStatus?: 'calibrated' | 'uncalibrated';
    calibrationData?: CalibrationData;
    status: 'active' | 'inactive' | 'calibrating';
    createdAt?: string;
    updatedAt?: string;
    lastCalibratedAt?: string;
    deviceName?: string;
    deviceModel?: string;
    gain1Spl?: number;
    gain50Spl?: number;
    gain100Spl?: number;
    measurementDate?: string;
}

export interface SPLQueryParams {
    keyword?: string;
    deviceId?: string | number;
    calibrationStatus?: string;
    status?: string;
    page?: number;
    perPage?: number;
    sortBy?: string;
    order?: 'asc' | 'desc';
}

export interface PaginationInfo {
    page: number;
    pages: number;
    perPage: number;
    total: number;
}
