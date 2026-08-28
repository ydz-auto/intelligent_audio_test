import type { TestCaseConfig, RoundAlgorithmParams, RoundReferenceParams } from '../../components/common/test-case/TestCaseModal/types';

export type TaskType = 'api' | 'e2e' | 'playback' | 'evaluation' | 'report' | 'task' | 'execution' | 'comparison' | 'performance' | 'stress' | 'audio_import';
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'stopped' | 'queued' | 'skipped' | 'evaluating' | 'reevaluate_queued' | 'reevaluating';

export interface Task {
    id: string | number;
    name: string;
    type: TaskType;
    status: TaskStatus;
    progress: number;
    description?: string;
    created_at: string;
    updated_at: string;
    finished_at?: string;
    error?: string;
    config?: Record<string, any>;
    result?: any;
    tags?: string[];
    case_count?: number;
    completed_count?: number;
    failed_count?: number;
    total_cases?: number;
    completed_cases?: number;
    failed_cases?: number;
    device_count?: number;
    deleted?: boolean;
    algorithm_type?: string;
    algorithm_params?: Record<string, any>;
}

export interface AudioInfo {
    id: string | number;
    name: string;
    filename: string;
    filepath: string;
    size: number;
    duration: number;
    format: string;
    sample_rate: number;
    channels: number;
    type: 'dry' | 'noise' | 'prompt' | 'mixed';
    audio_type?: 'dry' | 'noise' | 'prompt' | 'mixed';
    tags?: string[];
    created_at: string;
    updated_at?: string;
    asr_text?: string;
    translations?: Array<{ text: string, direction: string }>;
    annotations?: any[];
    source_language?: string;
    description?: string;
}

export type Audio = AudioInfo;

export interface AudioUploadFile {
    file: File;
    id: string;
    file_id: string;
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
    audio_id?: string | number;
    folder_group_name?: string;
    /** 最子级文件夹名（无文件夹结构时为去扩展名的文件名），用于按分组独立创建测试用例 */
    group_key?: string;
    asr_text?: string;
    translations?: Array<{ text: string, direction: string }>;
    tags?: string[];
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
    total_files?: number;
    completed_files?: number;
    failed_files?: number;
    total_size?: number;
    uploaded_size?: number;
    start_time?: string;
    end_time?: string;
}

export interface AudioUploadOptions {
    audio_type: 'dry' | 'noise' | 'prompt' | 'mixed';
    create_test_case: boolean;
    tags: string[];
    description?: string;
    test_types: ('api' | 'e2e')[];
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    playback_device_id?: string | number | null;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    spl?: number;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    noise_audio_id?: string | number | null;
    /** @deprecated 已移到 CaseForm 的 RoundConfigEditor 里配置 */
    noise_spl?: number;
    inherit_tags?: boolean;
    /** 评估维度数组，每条可带 test_type 标记属于 api/e2e */
    dimensions?: SelectedEvaluationDimension[];
    algorithm_type?: string;
    algorithm_relations?: Array<{
        algorithm_type: string;
        is_primary: boolean;
        weight: number;
        params?: Record<string, any>;
    }>;
    algorithm_params?: any[];
    prompt_device_id?: string | number | null;
    prompt_source_language?: string;
    prompt_target_language?: string;
    prompt_translation_direction?: string;
    prompt_algorithm_type?: string;
    group_name_type?: 'root' | 'folder' | 'custom';
    custom_group_name?: string;
}

export interface SelectedEvaluationDimension {
    id: number | string;
    name: string;
    weight?: number;
    threshold?: number;
    /** 标记该维度属于哪种 test_type，'api' / 'e2e'，未标记则通用 */
    test_type?: 'api' | 'e2e';
    /** 维度使用范围：'single' = 每轮独立评估，'multi' = 多轮聚合评估。默认 'single' */
    round_scope?: 'single' | 'multi';
}

export interface EvaluationDimensionsConfig {
    dimensions: SelectedEvaluationDimension[];
}

export interface Tag {
    id: number;
    name: string;
    description?: string;
    created_at?: string;
}

export interface TestCase {
    id: string | number;
    name: string;
    description?: string;
    type?: string;
    test_type?: 'api' | 'e2e';
    config?: TestCaseConfig;
    /** 按轮分组的算法参数，独立列，对应 test_cases.algorithm_params */
    algorithm_params?: RoundAlgorithmParams[];
    /** 按轮分组的参考参数路径，独立列，对应 test_cases.reference_params */
    reference_params?: RoundReferenceParams[];
    group_id?: string | number;
    group_name?: string;
    tags?: string[] | { id: number; name: string }[];
    algorithm_type?: string;
    created_at?: string;
    updated_at?: string;
    deleted?: boolean;
    total_duration?: number;
}

export interface APIConfig {
    id: string | number;
    name: string;
    vendor?: string;
    api_url?: string;
    method?: string;
    status: 'online' | 'offline' | 'busy' | 'error';
    health_score?: number;
    api_endpoints?: any[];
    api_settings?: Record<string, any>;
    algorithm_type?: string;
    created_at?: string;
    updated_at?: string;
    current_concurrent?: number;
    max_concurrent?: number;
    queue_length?: number;
    avg_response_time?: number;
}

export interface PlaybackDevice {
    id: string | number;
    name: string;
    model?: string;
    type: 'speaker' | 'headphone' | 'lineout' | 'noise' | 'dry';
    device_type?: string;
    sample_rate?: number;
    channel_index?: number;
    device_unique_id?: string;
    status: 'online' | 'offline' | 'busy' | 'error' | 'available' | 'unavailable' | 'testing';
    current_spl_mapping_id?: number | null;
    selected?: boolean;
    created_at?: string;
    updated_at?: string;
}

export interface AlgorithmAssociation {
    algorithm_type: string;
    is_default: boolean;
    weight: number;
}

export interface LlmJudgeConfig {
    model?: string;
    prompt_template?: string;
    max_tokens?: number;
    temperature?: number;
}

export interface Dimension {
    id: number | string;
    name: string;
    description?: string;
    keywords?: string;
    dimension_type?: 'main' | 'sub';
    parent_dimension_id?: number | null;
    task_type_code?: string;
    category_id?: number;
    api_url?: string;
    api_endpoints?: DimensionAPIEndpoint[];
    api_settings?: Record<string, any> | string;
    api_status?: string;
    type?: string;
    result_type?: string | number;
    result_min?: number;
    result_max?: number;
    decimal_places?: number;
    weight?: number;
    estimated_exec_time?: number;
    rule?: any;
    required_inputs?: string;
    requires_audio?: boolean;
    associated_algorithms?: AlgorithmAssociation[];
    status?: string;
    created_at?: string;
    updated_at?: string;
    score_unit?: string;
    llm_judge_config?: LlmJudgeConfig;
}

export interface EvaluationCategory {
    id: number;
    name: string;
    description?: string;
    icon?: string;
    created_at?: string;
    updated_at?: string;
}

export interface DimensionAPIEndpoint {
    url: string;
    name: string;
    priority: number;
    max_process: number;
    max_timeout: number;
    max_audio_duration: number;
}

export type EvaluationDimension = Dimension;

export interface Report {
    id: string | number;
    name: string;
    type: TaskType;
    status: 'completed' | 'failed' | 'running' | 'draft' | 'final' | 'published';
    created_at: string;
    updated_at?: string;
    task_id?: string | number;
    task_name?: string;
    algorithm_type?: string;
    description?: string;
    summary?: ReportSummary;
    detailed_results?: DetailedResult[];
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
    total_cases: number;
    success_rate: number;
    avg_response_time: number;
    stability: number;
}

export interface CaseExecutionItem {
    id: string | number;
    name: string;
    total: number;
    executed: number;
    completed: number;
    failed: number;
    success_rate: number;
    failed_rate: number;
}

export interface Device {
    id: string | number;
    name: string;
    keywords?: string;
    type?: string;
    model?: string;
    status?: string;
    selected?: boolean;
    created_at?: string;
    updated_at?: string;
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
    category_id: string;
    category_name: string;
    metrics: ReportMetricValue[];
}

export interface ReportMetricByResource {
    resource: string;
    categories: ReportMetricCategoryGroup[];
}

export interface ReportTagMetricTagGroup {
    tag_id: string;
    tag_name: string;
    metrics: ReportMetricValue[];
}

export interface ReportTagMetricByResource {
    resource: string;
    tags: ReportTagMetricTagGroup[];
}

export interface ReportCaseTypeStatRow {
    group_id: string;
    group_name: string;
    metrics: Array<{ metric: string; value: number }>;
}

export interface ReportMetricConfig {
    id?: string | number;
    name: string;
    unit?: string;
    decimal_places?: number;
}

export interface ReportSummary {
    total_cases: number;
    passed_cases: number;
    failed_cases: number;
    pass_rate: number;
    avg_score: number;
    all_metrics?: ReportMetricConfig[];
    detailed_results?: any[];
    device_stats?: any[];
    api_stats?: any[];
    metrics?: Record<string, any>;
    raw_data?: ReportRawDataGroup[];
    metric_data?: ReportMetricByResource[];
    tag_metric_data?: ReportTagMetricByResource[];
    case_type_stats?: ReportCaseTypeStatRow[];
    overall_success_rate?: number;
    stability?: number;
    dimension_values?: Record<string, any>;
    devices?: Array<string | {
        id: string | number;
        name: string;
        model?: string;
        description?: string;
        type?: string;
        system?: string;
        system_version?: string;
        app_name?: string;
        app_version?: string;
        location?: string;
        max_audio_duration?: number;
        needs_prompt_audio?: boolean;
        connection_type?: string;
        keywords?: string;
        serialNumber?: string;
        ip?: string;
        status?: string;
        last_online_at?: string;
        created_at?: string;
        updated_at?: string;
    }>;
    apis?: Array<string | {
        id: string | number;
        name: string;
        vendor?: string;
        api_url?: string;
        description?: string;
        status?: string;
        max_process?: number;
        max_timeout?: number;
        max_audio_duration?: number;
        health_score?: number;
        created_at?: string;
        updated_at?: string;
    }>;
    [key: string]: any;
}

export interface DetailedResult {
    id: string | number;
    case_name: string;
    score: number;
    result: string;
    [key: string]: any;
}

export interface CompareResult {
    report_ids: (string | number)[];
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
    created_at: string;
    task_id?: number | string;
    device_id?: number;
    thread_id?: string | number;
    mark?: string;
    test_case_id?: string | number;
    algorithm_type?: string;
}

export interface LogFilters {
    start_date_time: string;
    end_date_time: string;
    log_category: string;
    log_module: string;
    mark_filter: string;
    algorithm_type: string;
}

export interface AdvancedLogFilters {
    device_id?: string;
    task_id?: string;
    userId?: string;
    thread_id?: string;
    content_include?: string;
    content_exclude?: string;
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
    per_page?: number;
    algorithm_type?: string;
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
    algorithm_type?: string;
    created_at?: string;
    updated_at?: string;
}

export interface CalibrationPoint {
    input: number;
    output: number;
    spl_value: number;
    gain?: number;
    spl?: number;
    measured_spl?: number;
    target_spl?: number;
    frequency?: number;
    db?: number;
    linear_gain?: number;
    created_at?: string;
}

export interface CalibrationData {
    id: string | number;
    mapping_id: string | number;
    points: CalibrationPoint[];
    created_at?: string;
    updated_at?: string;
    method?: string;
    notes?: string;
    min_db?: number;
    max_db?: number;
    mode?: 'linear' | 'db_curve';
}

export interface SPLMapping {
    id: string | number;
    name: string;
    description?: string;
    device_id: string | number;
    device?: PlaybackDevice;
    distance?: number;
    test_frequency?: number;
    calibration_status?: 'calibrated' | 'uncalibrated';
    calibration_data?: CalibrationData;
    status: 'active' | 'inactive' | 'calibrating';
    created_at?: string;
    updated_at?: string;
    last_calibrated_at?: string;
    device_name?: string;
    device_model?: string;
    gain1_spl?: number;
    gain50_spl?: number;
    gain100_spl?: number;
    measurement_date?: string;
}

export interface SPLQueryParams {
    keyword?: string;
    device_id?: string | number;
    calibration_status?: string;
    status?: string;
    page?: number;
    per_page?: number;
    sort_by?: string;
    order?: 'asc' | 'desc';
}

export interface PaginationInfo {
    page: number;
    pages: number;
    per_page: number;
    total: number;
}
