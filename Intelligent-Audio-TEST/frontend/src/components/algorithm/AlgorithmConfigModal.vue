<template>
  <BasicModal
    :visible="visible"
    :title="title"
    :width="modalWidth"
    :show-footer="effectiveMode !== 'list'"
    :confirm-text="okText"
    :cancel-text="cancelText"
    @close="handleCancel"
    @cancel="handleCancel"
    @confirm="handleOk"
  >
    <div class="algorithm-config-modal">
      <div v-if="effectiveMode === 'list'" class="mode-list">
        <div class="modal-toolbar">
          <button class="btn btn-primary btn-sm" @click="handleCreate">
            <i class="fas fa-plus btn-icon"></i>新建算法
          </button>
          <div class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input
              type="text"
              class="search-input"
              placeholder="搜索算法"
              v-model="searchKeyword"
              @input="handleSearch"
            >
          </div>
        </div>

        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>名称</th>
                <th>分组</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="filteredAlgorithms.length === 0">
                <td colspan="5" class="empty-row">暂无数据</td>
              </tr>
              <tr v-else v-for="record in filteredAlgorithms" :key="record.type">
                <td>{{ record.type }}</td>
                <td>{{ record.name }}</td>
                <td>
                  <span class="status-tag" :class="getGroupTagClass(record.group_name)">
                    {{ record.group_name || '-' }}
                  </span>
                </td>
                <td>
                  <span class="status-badge" :class="record.status === 'online' ? 'active' : 'inactive'">
                    {{ record.status === 'online' ? '上线' : '下线' }}
                  </span>
                </td>
                <td>
                  <div class="table-actions">
                    <button class="btn btn-text btn-sm" @click="handleEdit(record)">
                      <i class="fas fa-edit btn-icon"></i>编辑
                    </button>
                    <button class="btn btn-text btn-sm" @click="handleToggleStatus(record)">
                      <i :class="record.status === 'online' ? 'fas fa-toggle-off' : 'fas fa-toggle-on'" class="btn-icon"></i>
                      {{ record.status === 'online' ? '禁用' : '启用' }}
                    </button>
                    <button class="btn btn-text btn-sm" @click="handleSelect(record)">
                      <i class="fas fa-check btn-icon"></i>选择
                    </button>
                    <button class="btn btn-text btn-sm btn-danger" @click="confirmDelete(record)">
                      <i class="fas fa-trash btn-icon"></i>删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="mode-form">
        <div class="tabs-nav">
          <button
            v-for="tab in formTabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <div v-show="activeTab === 'basic'" class="tab-content">
          <div class="form-row">
            <div class="form-group">
              <label>算法代码 <span class="required">*</span></label>
              <input
                type="text"
                class="form-input"
                v-model="formState.type"
                :disabled="effectiveMode === 'edit'"
                placeholder="如: translation, asr"
              >
            </div>
            <div class="form-group">
              <label>显示名称 <span class="required">*</span></label>
              <input
                type="text"
                class="form-input"
                v-model="formState.name"
                placeholder="如: 翻译"
              >
            </div>
            <div class="form-group">
              <label>所属分组 <span class="required">*</span></label>
              <select class="form-input" v-model="groupSelectValue">
                <option :value="null">请选择分组</option>
                <option v-for="group in groups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
                <option :value="NEW_GROUP_SENTINEL">+ 新建分组</option>
              </select>
              <input
                v-if="creatingNewGroup"
                type="text"
                class="form-input"
                style="margin-top: 8px;"
                placeholder="输入新分组名称"
                v-model="newGroupName"
              >
            </div>
            <div class="form-group">
              <label>排序</label>
              <input type="number" class="form-input" v-model.number="formState.display_order" min="0">
            </div>
          </div>

          <div class="form-row">
            <div class="form-group full-width">
              <label>描述</label>
              <textarea class="form-input" v-model="formState.description" rows="3"></textarea>
            </div>
          </div>
                    <div class="form-row">
            <div class="form-group status-switch-group">
              <label>状态</label>
              <div class="switch-container">
                <label class="custom-switch">
                  <input type="checkbox" class="switch-checkbox" v-model="formState.statusSwitch">
                  <span class="switch-slider"></span>
                </label>
                <span class="switch-label">{{ formState.statusSwitch ? '上线' : '下线' }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'params'" class="tab-content">
          <!-- 功能特性快捷开关 -->
          <div class="feature-bundles" v-if="paramConfigType === 'case'">
            <div class="feature-bundles-header">
              <i class="fas fa-bolt"></i>
              <span class="feature-bundles-title">功能特性快捷开关</span>
              <span class="feature-bundles-hint">勾选后自动批量添加/删除对应参数</span>
            </div>
            <div class="feature-bundles-list">
              <label
                v-for="(bundle, key) in FEATURE_BUNDLES"
                :key="key"
                class="feature-bundle-chip"
                :class="{ 'feature-bundle-chip--active': isBundleActive(key as string) }"
              >
                <input
                  type="checkbox"
                  :checked="isBundleActive(key as string)"
                  @change="toggleBundle(key as string)"
                />
                <span class="feature-bundle-label">{{ bundle.label }}</span>
                <span class="feature-bundle-count">{{ bundle.params.length }}个参数</span>
              </label>
            </div>
          </div>
          <div class="params-toolbar">
            <div class="param-type-tabs">
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'device' }"
                @click="paramConfigType = 'device'"
              >
                设备参数
              </button>
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'api' }"
                @click="paramConfigType = 'api'"
              >
                API参数
              </button>
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'case' }"
                @click="paramConfigType = 'case'"
              >
                用例参数
              </button>
            </div>
            <button class="btn btn-primary btn-sm" @click="handleAddParam">
              <i class="fas fa-plus btn-icon"></i>添加参数
            </button>
          </div>

          <!-- 设备参数和API参数表格 -->
          <div v-if="paramConfigType !== 'case'" class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>参数代码</th>
                  <th>参数名称</th>
                  <th>方向</th>
                  <th>类型</th>
                  <th>必填</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="currentParams.length === 0">
                  <td colspan="6" class="empty-row">暂无参数</td>
                </tr>
                <tr v-else v-for="(param, index) in currentParams" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" class="form-input form-input-sm param-code-input" v-model="param.param_code" @blur="handleParamBlur(param, index, paramConfigType)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.param_name" @blur="handleParamBlur(param, index, paramConfigType)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.direction" @change="handleParamBlur(param, index, paramConfigType)">
                      <option value="input">输入</option>
                      <option value="output">输出</option>
                    </select>
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.param_type" @change="handleParamBlur(param, index, paramConfigType)">
                      <option value="text">文本</option>
                      <option value="audio_stream">音频流</option>
                      <option value="audio_file">音频文件</option>
                      <option value="text_file">文本文件</option>
                      <option value="rttm">RTTM标注</option>
                      <option value="stm">STM标注</option>
                      <option value="json">JSON结构化</option>
                    </select>
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="param.required" @change="handleParamBlur(param, index, paramConfigType)">
                    </label>
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 用例参数表格 -->
          <div v-if="paramConfigType === 'case'" class="table-container">
            <table class="data-table" style="table-layout: fixed;">
              <thead>
                <tr>
                  <th style="width: 110px;">参数代码</th>
                  <th style="width: 100px;">参数名称</th>
                  <th style="width: 90px;">类型</th>
                  <th style="width: 80px;">适用范围</th>
                  <th style="width: 50px;">必填</th>
                  <th style="width: 80px;">默认值</th>
                  <th style="width: 160px;">范围约束</th>
                  <th style="width: 120px;">标注代码</th>
                  <th style="width: 120px;">字段路径</th>
                  <th style="width: 100px;">帮助文本</th>
                  <th style="width: 50px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="formState.case_params.length === 0">
                  <td colspan="11" class="empty-row">暂无用例参数</td>
                </tr>
                <tr v-else v-for="(param, index) in formState.case_params" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" list="case-param-code-presets" class="form-input form-input-sm param-code-input" v-model="param.param_code" @change="handleParamCodeSelect(param, index)" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.param_name" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.param_type" @change="handleCaseParamTypeChange(param, index)">
                      <option value="text">文本</option>
                      <option value="number">数字</option>
                      <option value="textarea">多行文本</option>
                      <option value="switch">开关</option>
                      <option value="slider">滑块</option>
                      <option value="audio_select">音频选择</option>
                      <option value="device_select">设备选择</option>
                      <option value="json">JSON结构化</option>
                    </select>
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.scope" @change="handleCaseParamBlur(param, index)">
                      <option value="common">通用</option>
                      <option value="api">API</option>
                      <option value="e2e">E2E</option>
                    </select>
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="param.required" @change="handleCaseParamBlur(param, index)">
                    </label>
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.default_value" placeholder="默认值" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <div v-if="['slider', 'number'].includes(param.param_type)" class="range-constraints">
                      <input type="number" class="form-input form-input-sm range-input" v-model="param.min_value" placeholder="最小" @blur="handleCaseParamBlur(param, index)">
                      <span class="range-sep">~</span>
                      <input type="number" class="form-input form-input-sm range-input" v-model="param.max_value" placeholder="最大" @blur="handleCaseParamBlur(param, index)">
                      <input type="number" class="form-input form-input-sm range-input" v-model="param.step" placeholder="步长" @blur="handleCaseParamBlur(param, index)">
                      <input type="text" class="form-input form-input-sm range-input range-unit" v-model="param.unit" placeholder="单位" @blur="handleCaseParamBlur(param, index)">
                    </div>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.annotation_code" placeholder="默认同算法类型" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.field_path" placeholder="默认同参数代码" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.help_text" placeholder="帮助提示" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveCaseParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <datalist id="case-param-code-presets">
            <option v-for="(preset, code) in PARAM_CODE_PRESETS" :key="code" :value="code">{{ preset.param_name }} ({{ preset.param_type }})</option>
          </datalist>
        </div>

        <!-- 参考参数配置 -->
        <div v-show="activeTab === 'reference'" class="tab-content">
          <div class="reference-config-intro">
            <p>配置算法的参考参数，用于存储参考文本、音频、文件等数据。</p>
            <p>参考类型支持：文本、音频、RTTM、STM等。配置的参考字段可参与评估参数映射。</p>
          </div>

          <div class="params-toolbar">
            <button class="btn btn-primary btn-sm" @click="handleAddReferenceParam">
              <i class="fas fa-plus btn-icon"></i>添加参考字段
            </button>
          </div>

          <div class="table-container">
            <table class="data-table" style="table-layout: fixed;">
              <thead>
                  <tr>
                    <th style="width: 120px;">参数代码</th>
                    <th style="width: 120px;">标注代码</th>
                    <th style="width: 100px;">参数名称</th>
                    <th style="width: 100px;">参考类型</th>
                    <th style="width: 100px;">标注格式</th>
                    <th style="width: 140px;">字段路径</th>
                    <th style="width: 90px;">合并方式</th>
                    <th style="width: 120px;">帮助文本</th>
                    <th style="width: 60px;">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="formState.reference_params.length === 0">
                    <td colspan="9" class="empty-row">暂无参考参数</td>
                  </tr>
                <tr v-else v-for="(param, index) in formState.reference_params" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.code" placeholder="如: asr_reference_text" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.annotation_code" placeholder="标注匹配代码，默认同算法代码" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.name" placeholder="参数名称" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.type" @change="handleReferenceParamBlur(param, index)">
                      <option value="text">文本</option>
                      <option value="audio">音频</option>
                      <option value="json">JSON</option>
                      <option value="rttm">RTTM</option>
                      <option value="stm">STM</option>
                    </select>
                  </td>
                  <td>
                      <select class="form-input form-input-sm" v-model="param.annotation_format" @change="handleReferenceParamBlur(param, index)">
                        <option value="">不指定</option>
                        <option value="text">文本</option>
                        <option value="json">JSON</option>
                        <option value="rttm">RTTM</option>
                        <option value="stm">STM</option>
                      </select>
                    </td>
                    <td>
                      <input type="text" class="form-input form-input-sm" v-model="param.field_path" placeholder="如: model 或 segments[].emotion" @blur="handleReferenceParamBlur(param, index)">
                    </td>
                    <td>
                      <select class="form-input form-input-sm" v-model="param.merge_mode" @change="handleReferenceParamBlur(param, index)">
                        <option value="join">拼接</option>
                        <option value="collect">收集数组</option>
                        <option value="first">取第一个</option>
                      </select>
                    </td>
                    <td>
                      <input type="text" class="form-input form-input-sm" v-model="param.help_text" placeholder="可选提示" @blur="handleReferenceParamBlur(param, index)">
                    </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveReferenceParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-show="activeTab === 'mappings'" class="tab-content">
          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('device')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.device }"></i>
              <span>设备参数映射 (用例参数 → 设备参数)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.device">
              <MappingEditor
                :mappings="formState.mappings.device"
                :algorithm-type="formState.type"
                :case-params="[...caseParams, ...referenceParams]"
                :device-params="deviceParams"
                component-type="device"
                @update="updateMappings('device', $event)"
              />
            </div>
          </div>

          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('api')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.api }"></i>
              <span>API参数映射 (用例参数 → API参数)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.api">
              <MappingEditor
                :mappings="formState.mappings.api"
                :algorithm-type="formState.type"
                :case-params="[...caseParams, ...referenceParams]"
                :api-params="apiParams"
                component-type="api"
                @update="updateMappings('api', $event)"
              />
            </div>
          </div>

          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('evaluation')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.evaluation }"></i>
              <span>评估参数映射 (用例参数/设备输出/API输出 → 评估维度)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.evaluation">
              <MappingEditor
                :mappings="formState.mappings.evaluation"
                :algorithm-type="formState.type"
                :case-params="caseParams"
                :reference-params="referenceParams"
                :device-params="[...deviceParams, ...deviceOutputParams]"
                :api-params="[...apiParams, ...apiOutputParams]"
                :main-dimensions="mainDimensions"
                component-type="evaluation"
                @update="updateMappings('evaluation', $event)"
              />
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'dimensions'" class="tab-content">
          <div class="dimensions-toolbar">
            <button class="btn btn-primary btn-sm" @click="handleAddDimension">
              <i class="fas fa-plus btn-icon"></i>添加关联维度
            </button>
          </div>

          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>评估维度</th>
                  <th>权重</th>
                  <th>默认</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="formState.associated_dimensions.length === 0">
                  <td colspan="4" class="empty-row">暂无关联维度</td>
                </tr>
                <tr v-else v-for="(dim, index) in formState.associated_dimensions" :key="index">
                  <td>
                    <select class="form-input form-input-sm" v-model="dim.dimension_id" @blur="handleDimensionBlur(index)">
                      <option :value="null">请选择维度</option>
                      <option v-for="dimension in availableDimensions" :key="dimension.id" :value="dimension.id">
                        {{ dimension.name }}
                      </option>
                    </select>
                  </td>
                  <td>
                    <input type="number" class="form-input form-input-sm" v-model.number="dim.weight" min="0" max="1" step="0.1" @blur="handleDimensionBlur(index)">
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="dim.is_default" @change="handleDimensionChange(index)">
                    </label>
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveDimension(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import BasicModal from '../common/modal/BasicModal.vue'
import MappingEditor from './MappingEditor.vue'
import { useAlgorithmConfigModal } from './AlgorithmConfigModal'
import type { ModalProps, AlgorithmRecord } from './AlgorithmConfigModal'

const props = withDefaults(defineProps<ModalProps>(), {
  visible: false,
  mode: 'list',
  editData: null
})

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'select', data: AlgorithmRecord): void
  (e: 'success'): void
}>()

const {
  PARAM_CODE_PRESETS,
  FEATURE_BUNDLES,
  title,
  modalWidth,
  effectiveMode,
  okText,
  cancelText,
  handleCancel,
  handleOk,
  handleCreate,
  searchKeyword,
  handleSearch,
  filteredAlgorithms,
  getGroupTagClass,
  handleEdit,
  handleToggleStatus,
  handleSelect,
  confirmDelete,
  formTabs,
  activeTab,
  formState,
  groupSelectValue,
  groups,
  NEW_GROUP_SENTINEL,
  creatingNewGroup,
  newGroupName,
  paramConfigType,
  isBundleActive,
  toggleBundle,
  currentParams,
  handleParamBlur,
  handleCaseParamBlur,
  handleCaseParamTypeChange,
  handleRemoveParam,
  handleParamCodeSelect,
  handleRemoveCaseParam,
  handleAddParam,
  handleAddReferenceParam,
  handleReferenceParamBlur,
  handleRemoveReferenceParam,
  caseParams,
  referenceParams,
  deviceParams,
  deviceOutputParams,
  apiParams,
  apiOutputParams,
  mappingExpanded,
  toggleMapping,
  updateMappings,
  mainDimensions,
  availableDimensions,
  handleAddDimension,
  handleDimensionBlur,
  handleDimensionChange,
  handleRemoveDimension,
} = useAlgorithmConfigModal(props, emit)
</script>

<style scoped>
@import './AlgorithmConfigModal.css';
</style>
