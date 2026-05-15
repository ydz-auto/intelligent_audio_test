<template>
  <!-- 主模态窗 -->
  <teleport to="body">
    <div 
      class="modal-overlay" 
      v-if="props.visible"
      @click="handleMaskClick($event)"
      style="
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999 !important;
        transition: all 0.3s ease;
        opacity: 1 !important;
        visibility: visible !important;
        pointer-events: auto !important;
      "
    >
      <!-- 调试日志 -->
      <div v-if="props.visible" style="position: absolute; top: 10px; left: 10px; color: white; background: rgba(0, 0, 0, 0.5); padding: 5px 10px; border-radius: 4px; font-size: 12px;">
        模态框可见{{ props.visible}}, 模式{{ props.mode}}
      </div>
      
      <div 
        class="modal-container" 
        @click.stop
        style="
          background-color: #fff;
          border-radius: 12px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
          max-height: 90vh;
          max-width: 800px;
          width: 90%;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          transform: scale(1) translateY(0);
        "
      >
        <div class="modal-header">
          <h3>{{ getModalTitle() }}</h3>
          <button type="button" class="modal-close" @click="() => handleClose()">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body" style="flex: 1; overflow-y: auto; padding: 24px;">
          <div v-if="props.mode === 'group'">
            <div class="form-row">
              <div class="form-group">
                <label for="groupName">组名称</label>
                <input type="text" id="groupName" v-model="localFormData.name" class="form-control">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label for="groupDescription">描述</label>
                <textarea id="groupDescription" v-model="localFormData.description" class="form-control"></textarea>
              </div>
            </div>
          </div>
          <div v-else-if="props.mode === 'case'">
            <div class="form-row">
              <div class="form-group">
                <label for="caseName">用例名称 <span class="required">*</span></label>
                <div class="input-group">
                  <input type="text" id="caseName" v-model="localFormData.name" class="form-control" required>
                  <div class="input-group-append">
                    <button type="button" class="btn btn-outline-secondary auto-generate-btn" @click="autoGenerateName" title="根据标签自动生成名称">
                      <i class="fas fa-wand-magic-sparkles mr-1"></i>自动生成
                    </button>
                  </div>
                </div>
              </div>
              <div class="form-group">
                <label for="caseGroup">所属分组 <span class="required">*</span></label>
                <select id="caseGroup" v-model="localFormData.group" class="form-control" required>
                  <option v-for="group in testCaseGroups" :key="group" :value="group">{{ group }}</option>
                  <option value="new-group">+ 新建分组</option>
                </select>
                <input v-if="localFormData.group === 'new-group'" type="text" class="form-control mt-2" placeholder="输入新分组名称" v-model="newGroupName">
              </div>
            </div>

            <div class="form-row">
              <div class="form-group">
                <label for="caseTags">标签</label>
                <div class="tag-input-wrapper">
                  <input 
                    type="text" 
                    id="caseTags" 
                    v-model="tagsInput" 
                    class="form-control" 
                    placeholder="输入标签，按回车或逗号添加"
                    @keydown.enter.prevent="addTags"
                  >
                </div>
                <div class="tags-container mt-2">
                  <span v-for="(tag, index) in localFormData.tags" :key="index" class="tag-item">
                    {{ tag }}
                    <button type="button" class="tag-remove" @click="removeTag(index)">
                      <i class="fas fa-times"></i>
                    </button>
                  </span>
                </div>
                <div v-if="availableTags && availableTags.length > 0" class="existing-tags mt-2">
                  <span class="existing-tags-label">已有标签：</span>
                  <span 
                    v-for="tag in (showAllTags ? filteredAvailableTags : filteredAvailableTags.slice(0, 15))" 
                    :key="tag" 
                    class="tag-item existing-tag"
                    :class="{ 'already-added': localFormData.tags && localFormData.tags.includes(tag) }"
                    @click="selectTag(tag)"
                  >
                    {{ tag }}
                  </span>
                  <span v-if="filteredAvailableTags.length > 15" class="more-tags" @click="showAllTags = !showAllTags">
                    {{ showAllTags ? '收起' : `+${filteredAvailableTags.length - 15} 更多` }}
                  </span>
                </div>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label for="caseDescription">描述</label>
                <textarea id="caseDescription" v-model="localFormData.description" class="form-control"></textarea>
              </div>
            </div>

            <AlgorithmSelector
              v-model="localFormData.algorithmType"
              :initial-params="algorithmParams"
              @params-change="handleAlgorithmParamsChange"
              @algorithm-type-change="handleAlgorithmTypeChange"
            />

            <!-- 音频配置区域 -->
            <div class="form-section">
              <div class="audio-config-header">
                <h4>音频配置</h4>
                <div class="audio-config-actions" v-if="localFormData.config.audios && localFormData.config.audios.length > 0">
                  <button type="button" class="btn btn-secondary btn-sm" @click="sortByFileName('asc')">
                    <i class="fas fa-sort-alpha-up"></i> 按文件名正序
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="sortByFileName('desc')">
                    <i class="fas fa-sort-alpha-down"></i> 按文件名倒序
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="shuffleAudioConfigs">
                    <i class="fas fa-random"></i> 随机排序
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagSelector" v-if="getUniqueTagsFromConfigs().length > 1">
                    <i class="fas fa-exchange-alt"></i> 标签交叉排列
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagDeviceSelector" v-if="getUniqueTagsFromConfigs().length > 0">
                    <i class="fas fa-tags"></i> 标签设备分配
                  </button>
                  <button type="button" class="btn btn-warning btn-sm" @click="openBatchDeviceModal" v-if="hasE2eAudio">
                    <i class="fas fa-desktop"></i> 批量设置设备
                  </button>
                  <button type="button" class="btn btn-info btn-sm" @click="openCrossDeviceModal" v-if="hasE2eAudio">
                    <i class="fas fa-random"></i> 设备交叉分配
                  </button>
                  <button type="button" class="btn btn-primary btn-sm" @click="openBatchSplModal" v-if="hasE2eAudio">
                    <i class="fas fa-volume-up"></i> 批量设置声压
                  </button>
                  <button type="button" class="btn btn-danger btn-sm" @click="clearAllAudioConfigs">
                    <i class="fas fa-trash-alt"></i> 清空全部
                  </button>
                </div>
              </div>
              <div class="tag-selector-for-interleave" v-if="showTagSelector && getUniqueTagsFromConfigs().length > 1">
                <div class="tag-selector-list">
                  <span
                    v-for="tag in getUniqueTagsFromConfigs()"
                    :key="tag"
                    class="tag-checkbox-item"
                    :class="{ selected: selectedTagsForInterleave.includes(tag) }"
                    @click="toggleTagSelection(tag)"
                  >
                    {{ tag }}
                  </span>
                </div>
                <div class="tag-interleave-preview" v-if="selectedTagsForInterleave.length >= 2">
                  <div class="preview-title">交叉顺序预览：</div>
                  <div class="interleave-order-preview">
                    <span v-for="(tag, index) in selectedTagsForInterleave" :key="index" class="interleave-tag">
                      {{ tag }}
                      <span v-if="index < selectedTagsForInterleave.length - 1" class="interleave-arrow">→</span>
                    </span>
                  </div>
                </div>
                <div class="tag-device-actions">
                  <button type="button" class="btn btn-primary btn-sm" @click="interleaveByTags" :disabled="selectedTagsForInterleave.length < 2">
                    <i class="fas fa-check"></i> 确定
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagSelector">
                    <i class="fas fa-times"></i> 取消
                  </button>
                </div>
              </div>
              <div class="tag-selector-for-interleave" v-if="showTagDeviceSelector && getUniqueTagsFromConfigs().length > 0">
                <div class="tag-device-mapping-list">
                  <div v-for="tag in getUniqueTagsFromConfigs()" :key="tag" class="tag-device-mapping-row">
                    <span class="tag-name">{{ tag }}</span>
                    <span class="arrow">→</span>
                    <select :value="getDeviceForTag(tag)" @change="updateTagDeviceMapping(tag, ($event.target as HTMLSelectElement).value)" class="device-select">
                      <option value="">-- 选择设备 --</option>
                      <option v-for="device in playbackDevices" :key="device.id" :value="device.id">
                        {{ device.name }} (通道 {{ device.channelIndex }})
                      </option>
                    </select>
                    <span class="audio-count">({{ getTagAudioCount(tag) }}个音频)</span>
                  </div>
                </div>
                <div class="tag-device-preview" v-if="hasValidTagDeviceMapping">
                  <div class="preview-title">分配预览：</div>
                  <div v-for="[tag, deviceId] in getTagDeviceMapping" :key="tag" class="preview-item">
                    • {{ tag }} → {{ getDeviceName(deviceId) }}
                  </div>
                </div>
                <div class="tag-device-actions">
                  <button type="button" class="btn btn-primary btn-sm" @click="assignDeviceByTags" :disabled="!hasValidTagDeviceMapping">
                    <i class="fas fa-check"></i> 确定
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" @click="toggleTagDeviceSelector">
                    <i class="fas fa-times"></i> 取消
                  </button>
                </div>
              </div>
              <div v-if="!localFormData.config.audios || localFormData.config.audios.length === 0" class="empty-state">
                <p>暂无音频配置，请添加</p>
              </div>
              <div
                v-for="(audioConfig, index) in localFormData.config.audios"
                :key="`audio-${audioConfig.audioId}`"
                class="dry-audio-item"
                :class="{ 'is-dragging': draggedAudioIndex === index, 'drag-over': dragOverAudioIndex === index }"
                draggable="true"
                @dragstart="handleAudioDragStart(index, $event)"
                @dragend="handleAudioDragEnd"
                @dragover="handleAudioDragOver(index, $event)"
                @drop="handleAudioDrop(index, $event)"
              >
                <div class="dry-audio-header">
                  <div class="dry-audio-header-left">
                    <span class="drag-handle" title="拖动调整顺序">
                      <i class="fas fa-bars"></i>
                    </span>
                    <span class="dry-audio-index">音频 {{ index + 1 }}</span>
                  </div>
                  <div class="audio-header-actions">
                    <button type="button" class="btn btn-secondary btn-sm" @click="copyAudioConfig(index)">
                      <i class="fas fa-copy"></i> 复制
                    </button>
                    <button type="button" class="btn btn-danger btn-sm" @click="removeAudioConfig(index)">
                      <i class="fas fa-trash"></i> 删除
                    </button>
                  </div>
                </div>
                <div class="form-row">
                  <div class="form-group">
                    <label for="audioFile">音频文件 <span class="required">*</span></label>
                    <div class="audio-selector-container" style="cursor: pointer;" @click="openAudioSelectModal('dry', index)">
                      <div class="selected-audio-info" v-if="audioConfig.audioId" :title="getAudioName(audioConfig.audioId)">
                        {{ getAudioName(audioConfig.audioId) }}
                      </div>
                      <div class="placeholder" v-else title="未选择音频">
                        未选择音频
                      </div>
                    </div>
                    <div class="audio-actions">
                      <button type="button" class="btn btn-primary" @click="openAudioSelectModal('dry', index)">
                        <i class="fas fa-search"></i> 选择音频
                      </button>
                      <button type="button" class="btn btn-secondary" @click="previewAudio(audioConfig.audioId, 'dry')" :disabled="!audioConfig.audioId">
                        <i class="fas fa-play"></i> 试听
                      </button>
                    </div>
                  </div>

                  <div class="form-group">
                    <label for="testType">测试类型 <span class="required">*</span></label>
                    <select v-model="audioConfig.testType" class="form-control" required>
                      <option value="api">API测试</option>
                      <option value="e2e">端到端测试</option>
                    </select>
                  </div>

                  <div class="form-group" v-if="audioConfig.testType === 'e2e'">
                    <label for="playbackDevice">播放设备 <span class="required" v-if="audioConfig.testType === 'e2e'">*</span></label>
                    <div class="audio-selector-container" style="cursor: pointer;" @click="openDeviceSelectModal(index)">
                      <div class="selected-audio-info" v-if="audioConfig.playbackDeviceId" :title="getDeviceName(audioConfig.playbackDeviceId)">
                        {{ getDeviceName(audioConfig.playbackDeviceId) }}
                      </div>
                      <div class="placeholder" v-else title="未选择设备">
                        未选择设备
                      </div>
                    </div>
                    <div class="audio-actions">
                      <button type="button" class="btn btn-primary" @click="openDeviceSelectModal(index)">
                        <i class="fas fa-search"></i> 选择设备
                      </button>
                    </div>
                  </div>
                  <div class="form-group" v-if="audioConfig.testType === 'e2e'">
                    <label for="audioSPL">声压级 (dB) <span class="required" v-if="audioConfig.testType === 'e2e'">*</span></label>
                    <input type="number" v-model.number="audioConfig.spl" class="form-control" min="0" max="120" required>
                  </div>
                  <div class="form-group">
                    <label for="playOrder">播放顺序 <span class="required">*</span></label>
                    <input type="number" v-model.number="audioConfig.playOrder" class="form-control" min="0" required>
                  </div>
                  <div class="audio-tags-full-row" v-if="audioConfig.audioId && getAudioTags(audioConfig.audioId)">
                    <span class="audio-tag-label">标签：</span>
                    <div class="audio-tags-container">
                      <template v-if="!expandedAudioTags[audioConfig.audioId]">
                        <span
                          v-for="(tag, idx) in getNormalizedTags(getAudioTags(audioConfig.audioId)).slice(0, MAX_AUDIO_TAGS)"
                          :key="idx"
                          class="tag-item"
                        >{{ tag }}</span>
                        <span
                          v-if="getNormalizedTags(getAudioTags(audioConfig.audioId)).length > MAX_AUDIO_TAGS"
                          class="tag-more"
                          @click.stop="toggleAudioTags(audioConfig.audioId)"
                        >+{{ getNormalizedTags(getAudioTags(audioConfig.audioId)).length - MAX_AUDIO_TAGS }} 更多</span>
                      </template>
                      <template v-else>
                        <span
                          v-for="(tag, idx) in getNormalizedTags(getAudioTags(audioConfig.audioId))"
                          :key="idx"
                          class="tag-item"
                        >{{ tag }}</span>
                        <span
                          class="tag-collapse"
                          @click.stop="toggleAudioTags(audioConfig.audioId)"
                        >收起</span>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
              <button type="button" class="btn btn-secondary" @click="addAudioConfig">
                <i class="fas fa-plus"></i> 添加音频配置
              </button>
            </div>



            <!-- E2E测试配置 -->
            <div class="form-section" v-if="hasE2eAudio">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4>端到端测试配置</h4>
                <button type="button" class="btn btn-danger btn-sm" @click="clearNoiseConfig" v-if="localFormData.config.backgroundNoise.audioId || (localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0)">
                  <i class="fas fa-trash"></i> 删除噪声配置
                </button>
              </div>
              <div class="form-section">
                <h5>噪声配置</h5>
                <div class="form-row">
                  <div class="form-group">
                    <label for="noiseAudio">噪声文件</label>
                    <div class="audio-selector-container" style="cursor: pointer;" @click="openAudioSelectModal('noise')">
                      <div class="selected-audio-info" v-if="localFormData.config.backgroundNoise.audioId" :title="getAudioName(localFormData.config.backgroundNoise.audioId)">
                        {{ getAudioName(localFormData.config.backgroundNoise.audioId) }}
                      </div>
                      <div class="placeholder" v-else title="无">
                        无
                      </div>
                    </div>
                    <div class="audio-actions">
                      <button type="button" class="btn btn-primary" @click="openAudioSelectModal('noise')">
                        <i class="fas fa-search"></i> 选择音频
                      </button>
                      <button v-if="localFormData.config.backgroundNoise.audioId" type="button" class="btn btn-secondary" @click="previewNoiseAudio" :disabled="!localFormData.config.backgroundNoise.audioId">
                        <i class="fas fa-play"></i> 试听
                      </button>
                    </div>
                  </div>
                  <div class="form-group">
                    <label for="noiseAudioSPL">噪声声压级 (dB)</label>
                    <input type="number" v-model.number="localFormData.config.backgroundNoise.spl" class="form-control" min="0" max="120">
                  </div>
                  <div class="form-group">
                    <label for="noisePlaybackDevices">播放设备</label>
                    <div class="audio-selector-container" style="cursor: pointer;" @click="openNoiseDeviceSelectModal">
                      <div class="selected-audio-info" v-if="localFormData.config.backgroundNoise.deviceIds && localFormData.config.backgroundNoise.deviceIds.length > 0" :title="getNoiseDeviceNames()">
                        {{ getNoiseDeviceNames() }}
                      </div>
                      <div class="placeholder" v-else title="未选择设备">
                        未选择设备
                      </div>
                    </div>
                    <div class="audio-actions">
                      <button type="button" class="btn btn-primary" @click="openNoiseDeviceSelectModal">
                        <i class="fas fa-search"></i> 选择设备
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 评测维度配置 -->
            <div class="form-section">
              <h4>评测维度配置</h4>
              <p v-if="localFormData.algorithmType && associatedDimensions.length > 0" class="dimension-filter-hint">
                <i class="fas fa-filter"></i> 已根据算法类型「{{ algorithmOptions.find(a => a.value === localFormData.algorithmType)?.name || localFormData.algorithmType }}」过滤可用维度
              </p>
              
              <!-- API评测维度 -->
              <div v-if="hasAPIAudio" class="form-sub-section">
                <h5>API测试评测维度</h5>
                <!-- 维度云选择 -->
                <div class="dimension-cloud-container">
                  <div 
                    v-for="dim in filteredAvailableDimensions" 
                    :key="dim.id"
                    class="dimension-tag"
                    :class="{ 'selected': isDimensionSelected(dim.name, 'api') }"
                    @click="toggleDimensionSelection(dim, 'api')"
                  >
                    {{ dim.name }}
                  </div>
                </div>
                
                <!-- 已选择维度的权重和阈值配置 -->
                <div class="selected-dimensions-config" v-if="localFormData.config.dimensions.api.length > 0">
                  <h6>已选择维度配置</h6>
                  <div v-for="(dimension, index) in localFormData.config.dimensions.api" :key="index" class="selected-dimension-config-item">
                    <div class="dimension-config-header">
                      <span class="dimension-config-name">{{ dimension.name }}</span>
                      <button type="button" class="btn btn-xs btn-danger" @click="removeAPIDimension(index)">
                        <i class="fas fa-times"></i> 移除
                      </button>
                    </div>
                    <div class="dimension-config-fields">
                      <div class="form-row">
                        <div class="form-group">
                          <label for="apiWeight-{{ index }}">权重（0-100） <span class="required">*</span></label>
                          <input type="number" id="apiWeight-{{ index }}" v-model.number="dimension.weight" class="form-control" min="0" max="100" required>
                        </div>
                        <div class="form-group">
                          <label for="apiThreshold-{{ index }}">阈值（0-100） <span class="required">*</span></label>
                          <input type="number" id="apiThreshold-{{ index }}" v-model.number="dimension.threshold" class="form-control" min="0" max="100" required>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- E2E评测维度 -->
              <div v-if="hasE2eAudio" class="form-sub-section mt-4">
                <h5>端到端测试评测维度</h5>
                <!-- 维度云选择 -->
                <div class="dimension-cloud-container">
                  <div 
                    v-for="dim in filteredAvailableDimensions" 
                    :key="dim.id"
                    class="dimension-tag"
                    :class="{ 'selected': isDimensionSelected(dim.name, 'e2e') }"
                    @click="toggleDimensionSelection(dim, 'e2e')"
                  >
                    {{ dim.name }}
                  </div>
                </div>
                
                <!-- 已选择维度的权重和阈值配置 -->
                <div class="selected-dimensions-config" v-if="localFormData.config.dimensions.e2e.length > 0">
                  <h6>已选择维度配置</h6>
                  <div v-for="(dimension, index) in localFormData.config.dimensions.e2e" :key="index" class="selected-dimension-config-item">
                    <div class="dimension-config-header">
                      <span class="dimension-config-name">{{ dimension.name }}</span>
                      <button type="button" class="btn btn-xs btn-danger" @click="removeE2EDimension(index)">
                        <i class="fas fa-times"></i> 移除
                      </button>
                    </div>
                    <div class="dimension-config-fields">
                      <div class="form-row">
                        <div class="form-group">
                          <label for="e2eWeight-{{ index }}">权重（0-100） <span class="required">*</span></label>
                          <input type="number" id="e2eWeight-{{ index }}" v-model.number="dimension.weight" class="form-control" min="0" max="100" required>
                        </div>
                        <div class="form-group">
                          <label for="e2eThreshold-{{ index }}">阈值（0-100） <span class="required">*</span></label>
                          <input type="number" id="e2eThreshold-{{ index }}" v-model.number="dimension.threshold" class="form-control" min="0" max="100" required>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 批量导入测试用例 -->
          <div v-else-if="props.mode === 'import'">
            <div class="form-section">
              <h5>
                导入配置
                <button type="button" class="btn btn-outline-primary btn-sm ml-2" @click="downloadTemplate">
                  <i class="fas fa-download"></i> 下载模板
                </button>
              </h5>
              <div class="form-row">
                <div class="form-group">
                  <label for="import-file">选择文件 <span class="required">*</span></label>
                  <div
                    class="file-upload"
                    :class="{ 'is-dragging': isImportDragging }"
                    style="border: 2px dashed var(--border-color); border-radius: var(--border-radius-md); padding: 24px; text-align: center; cursor: pointer; transition: all var(--transition-normal);"
                    @click="triggerImportFileSelect"
                    @dragenter.prevent="handleImportDragEnter"
                    @dragover.prevent="handleImportDragOver"
                    @dragleave.prevent="handleImportDragLeave"
                    @drop.prevent="handleImportDrop"
                  >
                    <i class="fas fa-upload" style="font-size: 32px; color: var(--primary-color); margin-bottom: 12px;"></i>
                    <p style="margin: 0 0 12px 0; color: var(--text-secondary);">点击或拖拽文件到此处上传</p>
                    <p style="margin: 0; font-size: 12px; color: var(--text-tertiary);">支持 .xlsx/.xls, .json 格式文件，单个文件不超过10MB</p>
                    <input ref="importFileInputRef" type="file" id="import-file" accept=".xlsx,.xls,.json" style="display: none;" @change="handleFileChange">
                    <div v-if="importFormData.file" class="file-info mt-2">
                      <i class="fas fa-file-alt"></i>
                      <span>{{ importFormData.file.name }}</span>
                      <button type="button" class="btn btn-danger ml-2" @click.stop="clearImportFile">
                        <i class="fas fa-times"></i> 移除
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <div class="form-section mt-4" v-if="importPreviewData">
              <h5>导入预览</h5>
              <div class="preview-stats">
                <span class="stat-item">用例数量：{{ importPreviewData.total }} 条</span>
                <span class="stat-item" v-if="importPreviewData.audioConfigsCount > 0">音频配置：{{ importPreviewData.audioConfigsCount }} 条</span>
                <span class="stat-item" v-if="importPreviewData.apiDimensionsCount > 0">API维度：{{ importPreviewData.apiDimensionsCount }} 条</span>
                <span class="stat-item" v-if="importPreviewData.e2eDimensionsCount > 0">E2E维度：{{ importPreviewData.e2eDimensionsCount }} 条</span>
                <span class="stat-item" v-if="importPreviewData.tagsCount > 0">标签：{{ importPreviewData.tagsCount }} 个</span>
              </div>
              <div class="preview-table-container mt-3">
                <table class="table table-sm">
                  <thead>
                    <tr>
                      <th>用例名称</th>
                      <th>类型</th>
                      <th>分组</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, index) in importPreviewData.items.slice(0, 10)" :key="index">
                      <td>{{ item.name }}</td>
                      <td>
                        <span class="badge" :class="item.type === 'api' ? 'badge-api' : 'badge-e2e'">
                          {{ item.type === 'api' ? 'API' : 'E2E' }}
                        </span>
                      </td>
                      <td>{{ item.group }}</td>
                      <td>
                        <span v-if="item.operation === 'update'" class="status-existing">更新</span>
                        <span v-else class="status-new">新增</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="importPreviewData.items.length > 10" class="preview-more">
                  显示前10条，共 {{ importPreviewData.items.length }} 条...
                </div>
              </div>
            </div>
          </div>
          
          <!-- 批量导出测试用例 -->
          <div v-else-if="props.mode === 'export'">
            <div class="form-section">
              <h5>
                导出配置
                <button type="button" class="btn btn-outline-primary btn-sm ml-2" @click="downloadTemplate">
                  <i class="fas fa-download"></i> 下载模板
                </button>
              </h5>
              <div class="form-row">
                <div class="form-group">
                  <label for="export-groups">选择测试组 <span class="required">*</span></label>
                  <div class="form-check" v-for="group in testCaseGroups" :key="group">
                    <input type="checkbox" class="form-check-input" :id="`group-${group}`" v-model="exportFormData.groups" :value="group">
                    <label class="form-check-label" :for="`group-${group}`">{{ group }}</label>
                  </div>
                  <div v-if="exportFormData.groups.length === 0" class="text-danger mt-1">请至少选择一个测试组</div>
                </div>
              </div>
              <div class="form-row mt-3">
                <div class="form-group">
                  <label for="export-test-type">导出配置类型</label>
                  <select id="export-test-type" class="form-control" v-model="exportFormData.testType">
                    <option value="all">所有配置</option>
                    <option value="api">仅API测试配置</option>
                    <option value="e2e">仅端到端测试配置</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="export-format">导出格式 <span class="required">*</span></label>
                  <select id="export-format" class="form-control" v-model="exportFormData.format" required>
                    <option value="xlsx">Excel格式（.xlsx，多Sheet结构，推荐）</option>
                    <option value="json">JSON格式（完整数据）</option>
                  </select>
                </div>
              </div>
              <div class="form-row mt-3">
                <div class="form-group">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="include-config" v-model="exportFormData.includeConfig">
                    <label class="form-check-label" for="include-config">包含完整配置信息</label>
                  </div>
                </div>
                <div class="form-group">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="include-deleted" v-model="exportFormData.includeDeleted">
                    <label class="form-check-label" for="include-deleted">包含已删除用例</label>
                  </div>
                </div>
              </div>
            </div>
            
            <div class="form-section mt-4">
              <h5>导出预览</h5>
              <div class="preview-stats">
                <span class="stat-item">预计导出：{{ exportPreviewData.total }} 条</span>
                <span class="stat-item">API测试配置：{{ exportPreviewData.apiCount }} 条</span>
                <span class="stat-item">端到端测试配置：{{ exportPreviewData.e2eCount }} 条</span>
              </div>
              <div class="preview-table-container mt-3">
                <table class="table table-sm">
                  <thead>
                    <tr>
                      <th>分组</th>
                      <th>用例数量</th>
                      <th>API测试配置</th>
                      <th>端到端测试配置</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(group, index) in exportPreviewData.groupStats" :key="index">
                      <td>{{ group.name }}</td>
                      <td>{{ group.total }}</td>
                      <td>{{ group.api }}</td>
                      <td>{{ group.e2e }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="() => handleClose()">取消</button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="props.mode === 'export' && (exportFormData.groups.length === 0 || (Array.isArray(exportCaseIds) ? exportCaseIds.length === 0 : exportCaseIds?.length === 0))"
            @click="() => getSubmitHandler()()"
          >
            {{ getSubmitButtonText() }}
          </button>
        </div>
      </div>
    </div>
    
  </teleport>
  
  <!-- 新的音频选择模态窗 -->
  <teleport to="body">
    <AudioSelectModal
      :visible="showAudioModal"
      :audio-type="currentAudioType"
      :is-multi-select="true"
      title="选择音频文件"
      @close="showAudioModal = false"
      @select="handleAudioSelect"
      @select-multiple="handleMultipleAudioSelect"
      @select-current-page="handleSelectCurrentPage"
      @select-all-pages="handleSelectAllPages"
      @toggle-select-all="handleToggleSelectAll"
    />
  </teleport>
  
  <!-- 音频试听模态窗 -->
  <teleport to="body">
    <AudioPreviewModal
      :visible="showAudioPreviewModal"
      :audio-id="currentPreviewAudioId ?? undefined"
      :audio-type="currentPreviewAudioType"
      :playback-devices="playbackDevices"
      :initial-selected-devices="currentPreviewDeviceId ? [currentPreviewDeviceId] : []"
      :initial-spl="currentPreviewSpl"
      :initial-offset="currentPreviewOffset"
      @close="showAudioPreviewModal = false"
      @preview="handleAudioPreview"
    />
  </teleport>
  
  <!-- 全局播放设备选择模态窗 -->
  <teleport to="body">
    <GlobalPlaybackDeviceModal
      :visible="showDeviceModal"
      :title="'选择播放设备'"
      :is-multi-select="false"
      :initial-selected-devices="initialSelectedDevices"
      :playback-devices="playbackDevices"
      :audio-type="'dry'"
      :show-scan-devices="false"
      @close="showDeviceModal = false"
      @confirm="handleDeviceSelect"
    />
  </teleport>
  
  <!-- 噪声音频设备选择模态窗 -->
  <teleport to="body">
    <GlobalPlaybackDeviceModal
      :visible="showNoiseDeviceModal"
      :title="'选择噪声播放设备'"
      :is-multi-select="true"
      :initial-selected-devices="noiseInitialSelectedDevices"
      :playback-devices="playbackDevices"
      :audio-type="'noise'"
      :show-scan-devices="false"
      :is-required="false"
      @close="showNoiseDeviceModal = false"
      @confirm="handleNoiseDeviceSelect"
    />
  </teleport>

  <!-- 批量设置非噪声音频播放设备模态窗 -->
  <teleport to="body">
    <GlobalPlaybackDeviceModal
      :visible="showBatchDeviceModal"
      :title="'批量设置播放设备'"
      :is-multi-select="false"
      :initial-selected-devices="batchInitialSelectedDevices"
      :playback-devices="playbackDevices"
      :audio-type="'dry'"
      :show-scan-devices="false"
      @close="showBatchDeviceModal = false"
      @confirm="handleBatchDeviceSelect"
    />
  </teleport>

  <!-- 设备交叉分配模态窗 -->
  <teleport to="body">
    <GlobalPlaybackDeviceModal
      :visible="showCrossDeviceModal"
      :title="'选择设备进行交叉分配'"
      :is-multi-select="true"
      :initial-selected-devices="crossDeviceInitialSelectedDevices"
      :playback-devices="playbackDevices"
      :audio-type="'noise'"
      :show-scan-devices="false"
      :is-required="true"
      @close="showCrossDeviceModal = false"
      @confirm="handleCrossDeviceSelect"
    />
  </teleport>

  <!-- 批量设置干声声压模态窗 -->
  <teleport to="body">
    <div class="modal-overlay" v-if="showBatchSplModal" @click="showBatchSplModal = false" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; z-index: 10000 !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>批量设置干声声压</h3>
          <button type="button" class="modal-close" @click="showBatchSplModal = false">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-section">
            <label for="batchSplInput">声压级 (dB)</label>
            <input type="number" id="batchSplInput" v-model.number="batchSplValue" class="form-control" min="0" max="120" placeholder="请输入0-120之间的声压级">
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="showBatchSplModal = false">取消</button>
          <button type="button" class="btn btn-primary" @click="handleBatchSplConfirm">
            <i class="fas fa-check"></i> 确认
          </button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- 维度选择模态窗 -->
  <teleport to="body">
    <div class="modal-overlay" v-if="showDimensionModal" @click="showDimensionModal = false" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; z-index: 9999 !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>选择评测维度</h3>
          <button type="button" class="modal-close" @click="showDimensionModal = false">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="search-box mb-4">
            <i class="fas fa-search search-icon"></i>
            <input type="text" class="search-input" placeholder="搜索评测维度..." v-model="dimensionSearchQuery">
          </div>
          <div class="dimension-list-container">
            <div 
              v-for="dimension in filteredDimensions" 
              :key="dimension.id" 
              class="dimension-item"
              @click="handleDimensionSelect(dimension)"
            >
              <div class="dimension-info">
                <div class="dimension-name">{{ dimension.name }}</div>
                <div class="dimension-description">{{ dimension.description || '无描述' }}</div>
              </div>
              <button type="button" class="btn btn-primary" @click.stop="handleDimensionSelect(dimension)">
                选择
              </button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="showDimensionModal = false">取消</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useModalStore } from '../../../store/modalStore';
import { playbackApi, audiosApi, testcasesApi, evaluationApi } from '../../../utils/api';
import { normalizeTestCaseConfig } from '../../../utils/utils';
import { useAlgorithmConfig } from '../../../composables/useAlgorithmConfig';
import { useAlgorithmLabels } from '../../../composables/useAlgorithmLabels';
import { useDimensions } from '../../../composables/useDimensions';
import AudioSelectModal from '../AudioSelectModal.vue';
import AudioPreviewModal from '../modal/AudioPreviewModal.vue';
import GlobalPlaybackDeviceModal from '../modal/GlobalPlaybackDeviceModal.vue';
import AudioPlayerModal from '../AudioPlayerModal.vue';
import AlgorithmSelector from '../AlgorithmSelector.vue';

const {
  getAlgorithmOptions,
  getFormSchema,
  getAssociatedDimensions
} = useAlgorithmConfig()

const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

onMounted(() => {
  loadAlgorithms();
});

const props = defineProps({
  visible: { type: Boolean, default: false },
  mode: { type: String, default: 'case', validator: (value: string) => ['case', 'group', 'import', 'export'].includes(value) },
  testType: { type: String, default: 'api' },
  formData: { type: Object, default: () => ({}) }
});

const modalStore = useModalStore();
const isDraftRestored = ref(false);
const isInitializing = ref(false);

// 根据模式生成唯一的草稿ID
const draftId = computed(() => {
  // 编辑模式下不使用草稿
  if (props.formData?.id) {
    return null;
  }
  if (props.mode === 'case') return 'addTestCase';
  if (props.mode === 'group') return 'addTestGroup';
  return null;
});

// 初始化函数
  async function performInitialization() {
    if (isInitializing.value) {
      console.log('[TestCaseModal] 跳过初始化，因为正在初始化中');
      return;
    }
    isInitializing.value = true;
    console.log('[TestCaseModal] 开始执行初始化...');

    algorithmParams.value = {};
    referenceParams.value = {};

    try {
      const data = initFormData();
      localFormData.value = data;
      console.log('[TestCaseModal] localFormData.value 已更新:', JSON.stringify(localFormData.value));

      await Promise.all([
        loadTestGroups(),
        loadAlgorithmOptions(),
        loadAvailableTags(),
        loadResources()
      ]);

      // 标签显示在下方标签容器中，输入框保持空
      tagsInput.value = '';

      if (data.algorithmType) {
        await loadAlgorithmFormSchema(data.algorithmType);
        await loadDimensions(data.algorithmType);
      } else {
        await loadDimensions();
      }
    } finally {
      setTimeout(() => {
        isInitializing.value = false;
        console.log('[TestCaseModal] 初始化完成');
      }, 0);
    }
  };

// 监听props.visible的变化
watch(() => props.visible, (newValue, oldValue) => {
  console.log('[TestCaseModal] props.visible变化:', oldValue, '→', newValue);
  if (newValue) {
    console.log('[TestCaseModal] 即将执行初始化，isInitializing:', isInitializing.value);
    performInitialization();
    console.log('[TestCaseModal] 初始化执行完成');
  } else {
    isDraftRestored.value = false;
  }
});

// 监听props.mode的变化
watch(() => props.mode, (newValue, oldValue) => {
  console.log('[TestCaseModal] props.mode变化:', oldValue, '→', newValue);
  if (newValue !== oldValue && props.visible) {
    performInitialization();
  }
});

// 监听props.formData的变化
watch(() => props.formData, (newValue, oldValue) => {
  console.log('[TestCaseModal] props.formData变化:', oldValue, '→', newValue);
  if (props.visible && !isInitializing.value && !isDraftRestored.value && newValue && JSON.stringify(newValue) !== JSON.stringify(oldValue)) {
    performInitialization();
  }
}, { deep: true });

// 专门监听 algorithmType 的变化，更新 localFormData
watch(() => props.formData?.algorithmType, async (newValue, oldValue) => {
  console.log('[TestCaseModal] algorithmType watch:', newValue, 'oldValue:', oldValue, 'visible:', props.visible);
  if (newValue !== undefined && newValue !== '' && newValue !== oldValue) {
    console.log('[TestCaseModal] algorithmType 变化:', oldValue, '→', newValue);
    localFormData.value.algorithmType = newValue;
    await loadAlgorithmFormSchema(newValue);
    if (newValue) {
      const dimensions = await fetchDimensionsByAlgorithmType(newValue);
      availableDimensions.value = dimensions as Dimension[];
      associatedDimensions.value = dimensions.map(d => ({
        id: d.id,
        name: d.name,
        type: (d as any).type,
        description: (d as any).description,
        weight: 50,
        is_default: false
      }));
      const newAssociatedIds = new Set(associatedDimensions.value.map(d => d.id));
      localFormData.value.config.dimensions.api = localFormData.value.config.dimensions.api.filter(
        (dim: any) => newAssociatedIds.has(dim.id)
      );
      localFormData.value.config.dimensions.e2e = localFormData.value.config.dimensions.e2e.filter(
        (dim: any) => newAssociatedIds.has(dim.id)
      );
    } else {
      availableDimensions.value = [];
      associatedDimensions.value = [];
    }
  }
});

// 计算属性：判断是否是编辑模式
const isEditMode = computed(() => {
  if (props.mode === 'group') {
    return !!props.formData.name;
  } else if (props.mode === 'case') {
    return !!props.formData.id;
  }
  return false;
});

const importFormData = ref<{ file: File | null }>({
  file: null
});

const importFileInputRef = ref<HTMLInputElement | null>(null);
const isImportDragging = ref(false);

const exportFormData = ref({
  groups: [],
  testType: props.testType,
  format: 'json',
  includeConfig: true,
  includeDeleted: false
});

const exportCaseIds = ref<(string | number)[]>([]);

const importPreviewData = ref<ImportPreviewData | null>(null);
const exportPreviewData = ref<{
  total: number;
  apiCount: number;
  e2eCount: number;
  groupStats: GroupStat[];
}>({
  total: 0,
  apiCount: 0,
  e2eCount: 0,
  groupStats: []
});

interface TestCaseGroup {
  name?: string;
  group?: string;
  id?: string | number;
}

interface TestCaseGroupItem {
  name?: string;
  group?: string;
  id?: string | number;
  [key: string]: unknown;
}

interface GroupStat {
  name: string;
  total: number;
  api: number;
  e2e: number;
}

interface Dimension {
  id: string | number;
  name: string;
  description?: string;
}

interface TestCase {
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
    audios?: Array<{
      testType: string;
      audioId?: string;
    }>;
  };
}

interface AudioItem {
  id: string | number;
  name: string;
  audioType?: string;
}

interface PlaybackDevice {
  id: string | number;
  name: string;
  channelIndex?: number;
}

interface ImportPreviewItem {
  name: string;
  type: string;
  group: string;
  operation: 'update' | 'insert';
}

interface ImportPreviewData {
  total: number;
  items: ImportPreviewItem[];
  audioConfigsCount: number;
  apiDimensionsCount: number;
  e2eDimensionsCount: number;
  tagsCount: number;
  groupsCount: number;
  sheetNames: string[];
}

const testCaseGroups = ref<string[]>([]);

  // 标签相关状态
  const tagsInput = ref('');
  const newGroupName = ref('');
  const availableTags = ref<string[]>([]);
  const showAllTags = ref(false);
  
  async function loadAvailableTags() {
    try {
      console.log('[TestCaseModal] 开始加载标签列表...');
      const tags = await testcasesApi.getTags();
      console.log('[TestCaseModal] 获取到的标签列表原始值:', tags, '类型:', typeof tags);
      
      let parsedTags: string[] = [];
      if (Array.isArray(tags)) {
        parsedTags = tags;
      } else if (tags && typeof tags === 'object') {
        if (tags.data && Array.isArray(tags.data)) {
          parsedTags = tags.data;
        } else if (tags.items && Array.isArray(tags.items)) {
          parsedTags = tags.items;
        }
      }
      
      availableTags.value = parsedTags;
      console.log('[TestCaseModal] availableTags 已设置:', availableTags.value);
    } catch (error) {
      console.error('加载标签列表失败:', error);
      availableTags.value = [];
    }
  }

// 过滤掉已添加的标签（用于"已有标签"展示）
  const filteredAvailableTags = computed(() => {
    const tags = availableTags.value;
    if (!Array.isArray(tags)) {
      return [];
    }
    return tags.filter(tag => !localFormData.value.tags?.includes(tag));
  });

  const selectTag = (tag: string) => {
    if (!localFormData.value.tags) {
      localFormData.value.tags = [];
    }
    if (!localFormData.value.tags.includes(tag)) {
      localFormData.value.tags.push(tag);
    }
    tagsInput.value = '';
  };

  const autoGenerateName = () => {
    const tags = localFormData.value.tags;
    if (tags && tags.length > 0) {
      const filteredTags = tags.filter((tag: string) => tag.length <= 25);
      const sortedTags = filteredTags.sort((a: string, b: string) => a.length - b.length);
      localFormData.value.name = sortedTags.join('-');
    }
  };

  const algorithmOptions = ref<{ value: string; name: string }[]>([
    { value: 'translation', name: '翻译' },
    { value: 'asr', name: 'ASR识别' },
    { value: 'speaker_recognition', name: '说话人识别' },
    { value: 'tts', name: '语音合成' },
    { value: 'asr_eval', name: 'ASR评估' }
  ]);
  const algorithmFormSchema = ref<any>(null);
  const algorithmParams = ref<Record<string, any>>({});
  const referenceParams = ref<Record<string, any>>({});
  const associatedDimensions = ref<Array<{ id: number; name: string; description?: string; type?: string; weight: number; is_default: boolean }>>([]);

  async function loadAlgorithmOptions() {
    try {
      const options = await getAlgorithmOptions();
      algorithmOptions.value = (options || []).map((opt: any) => ({
        value: opt.value,
        name: opt.name || opt.label || opt.value
      }));
    } catch (error) {
      console.error('加载算法选项失败:', error);
      algorithmOptions.value = fallbackOptions.value.length > 0
        ? fallbackOptions.value.map((opt: any) => ({ value: opt.value, name: opt.label }))
        : [
          { value: 'translation', name: '翻译' },
          { value: 'asr', name: 'ASR识别' },
          { value: 'speaker_recognition', name: '说话人识别' },
          { value: 'tts', name: '语音合成' },
          { value: 'asr_eval', name: 'ASR评估' }
        ];
    }
  }

  async function loadAlgorithmFormSchema(algorithmType: string) {
    if (!algorithmType) {
      algorithmFormSchema.value = null;
      algorithmParams.value = {};
      associatedDimensions.value = [];
      return;
    }

    const savedParams = { ...algorithmParams.value };

    try {
      const schema = await getFormSchema(algorithmType);
      console.log('[TestCaseModal] 加载 schema:', schema);
      algorithmFormSchema.value = schema;

      const newParams: Record<string, any> = {};
      
      if (schema?.fields) {
        schema.fields.forEach((field: any) => {
          const fieldCode = field.fieldCode;
          if (savedParams[fieldCode] !== undefined) {
            newParams[fieldCode] = savedParams[fieldCode];
            console.log(`[TestCaseModal] 匹配字段 ${fieldCode}:`, savedParams[fieldCode]);
          } else if (field.defaultValue !== undefined) {
            newParams[fieldCode] = field.defaultValue;
          }
        });

        for (const [key, value] of Object.entries(savedParams)) {
          if (newParams[key] === undefined) {
            newParams[key] = value;
          }
        }
      }
      
      algorithmParams.value = newParams;
      console.log('[TestCaseModal] 最终 algorithmParams:', algorithmParams.value);

      const dimResult = await getAssociatedDimensions(algorithmType);
      if (dimResult && dimResult.dimensions) {
        associatedDimensions.value = dimResult.dimensions;
        
        const defaultDim = dimResult.dimensions.find((d: any) => d.is_default);
        if (defaultDim) {
          const existingApiDim = localFormData.value.config.dimensions.api.find((d: any) => d.id === defaultDim.id || d.name === defaultDim.name);
          if (!existingApiDim) {
            localFormData.value.config.dimensions.api.push({
              id: defaultDim.id,
              name: defaultDim.name,
              weight: defaultDim.weight || 50,
              threshold: 80
            });
          }
        }
      } else {
        associatedDimensions.value = [];
      }
    } catch (error) {
      console.error('加载算法表单Schema失败:', error);
      algorithmFormSchema.value = null;
      associatedDimensions.value = [];
    }
  }

  async function handleAlgorithmTypeChange() {
    const previousAssociatedIds = new Set(associatedDimensions.value.map(d => d.id));

    await loadAlgorithmFormSchema(localFormData.value.algorithmType);

    if (localFormData.value.algorithmType) {
      const dimensions = await fetchDimensionsByAlgorithmType(localFormData.value.algorithmType);
      availableDimensions.value = dimensions as Dimension[];
      associatedDimensions.value = dimensions.map(d => ({
        id: d.id,
        name: d.name,
        type: (d as any).type,
        description: (d as any).description,
        weight: 50,
        is_default: false
      }));
    } else {
      availableDimensions.value = [];
      associatedDimensions.value = [];
    }

    if (associatedDimensions.value.length > 0) {
      const newAssociatedIds = new Set(associatedDimensions.value.map(d => d.id));

      localFormData.value.config.dimensions.api = localFormData.value.config.dimensions.api.filter(
        (dim: any) => newAssociatedIds.has(dim.id)
      );

      localFormData.value.config.dimensions.e2e = localFormData.value.config.dimensions.e2e.filter(
        (dim: any) => newAssociatedIds.has(dim.id)
      );
    }
  }

  function handleAlgorithmParamsChange(params: Record<string, any>) {
    algorithmParams.value = params;
  }

  // 计算属性：检查是否有API音频配置
const hasAPIAudio = computed(() => {
  if (!localFormData.value.config.audios) return false;
  return localFormData.value.config.audios.some((audio: { testType: string }) => audio.testType === 'api');
});

// 计算属性：检查是否有E2E音频配置
const hasE2eAudio = computed(() => {
  if (!localFormData.value.config.audios) return false;
  return localFormData.value.config.audios.some((audio: { testType: string }) => audio.testType === 'e2e');
});

// 计算已选音频的所有标签（去重）
const selectedAudioTags = computed(() => {
  const allTags = new Set<string>();
  
  // 获取干声和噪声音频的标签
  const allAudios = [...dryAudios.value, ...noiseAudios.value];
  
  // 遍历所有音频配置
  if (localFormData.value.config.audios) {
    localFormData.value.config.audios.forEach((audioConfig: { audioId: string }) => {
      if (audioConfig.audioId) {
        const audio = allAudios.find(a => String(a.id) === String(audioConfig.audioId));
        if (audio && audio.tags) {
          const tags = Array.isArray(audio.tags) ? audio.tags : String(audio.tags).split(',');
          tags.forEach((tag: string) => {
            const trimmedTag = tag.trim();
            if (trimmedTag) {
              allTags.add(trimmedTag);
            }
          });
        }
      }
    });
  }
  
  // 也检查背景噪声
  if (localFormData.value.config.backgroundNoise?.audioId) {
    const noiseAudio = allAudios.find(a => String(a.id) === String(localFormData.value.config.backgroundNoise.audioId));
    if (noiseAudio && noiseAudio.tags) {
      const tags = Array.isArray(noiseAudio.tags) ? noiseAudio.tags : String(noiseAudio.tags).split(',');
      tags.forEach((tag: string) => {
        const trimmedTag = tag.trim();
        if (trimmedTag) {
          allTags.add(trimmedTag);
        }
      });
    }
  }
  
  return Array.from(allTags);
});

// 同步音频标签到用例标签（只添加，不删除手动输入的标签）
const syncAudioTagsToCase = () => {
  if (!localFormData.value.tags) {
    localFormData.value.tags = [];
  }
  
  const currentTags = new Set(localFormData.value.tags.map((t: string) => t.trim()).filter((t: string) => t));
  
  selectedAudioTags.value.forEach((tag: string) => {
    if (!currentTags.has(tag)) {
      localFormData.value.tags.push(tag);
    }
  });
};

  // 初始化本地表单数据
  const initFormData = () => {
    console.log(`[TestCaseModal] initFormData called, mode: ${props.mode}, draftId: ${draftId.value}`);
    console.log(`[TestCaseModal] props.formData:`, JSON.stringify(props.formData));
    
    // 0. 如果 props.formData 中有 algorithmType，优先使用
    const rawFormData = props.formData ?? {};
    let initialAlgorithmType = '';
    if (rawFormData.algorithmType !== undefined && rawFormData.algorithmType !== '') {
      initialAlgorithmType = rawFormData.algorithmType;
      console.log(`[TestCaseModal] 检测到外部传入的 algorithmType:`, initialAlgorithmType);
    }
    
    // 1. 只有在非编辑模式下才尝试恢复草稿
    if (!isEditMode.value && draftId.value) {
      const draft = modalStore.getDraft(draftId.value);
      if (draft) {
        console.log(`[TestCaseModal] 发现草稿 (${draftId.value}):`, JSON.stringify(draft));
        const formDataCopy = JSON.parse(JSON.stringify(rawFormData));
        
        // 合并数据：props.formData 的非空值优先
        const mergedData = { ...draft };
        for (const key of Object.keys(formDataCopy)) {
          const value = (formDataCopy as any)[key];
          // 只有当值是非空字符串、非空对象/数组时才覆盖
          if (value !== '' && value !== null && value !== undefined) {
            if (typeof value === 'object' && Object.keys(value).length > 0) {
              (mergedData as any)[key] = value;
            } else if (typeof value !== 'object') {
              (mergedData as any)[key] = value;
            }
          }
        }
        
        // 清除草稿，因为已经使用了新的 formData
        modalStore.clearDraft(draftId.value);
        
        console.log(`[TestCaseModal] 合并后的数据:`, JSON.stringify(mergedData));
        isDraftRestored.value = true;
        return mergedData;
      }
    }

    console.log(`[TestCaseModal] 未发现草稿或处于编辑模式，初始化常规数据`);
    isDraftRestored.value = false;
    const rawFormDataForCopy = props.formData ?? {};
    const formDataCopy = JSON.parse(JSON.stringify(rawFormDataForCopy));
    
    // 确保配置对象存在
    if (!formDataCopy.config) {
      formDataCopy.config = {};
    }
    
    const normalizedConfig = normalizeTestCaseConfig(formDataCopy.config);
    delete (normalizedConfig as any).apiAudios;
    delete (normalizedConfig as any).dryAudios;
    formDataCopy.config = normalizedConfig;

    if (!Array.isArray(formDataCopy.config.audios) || formDataCopy.config.audios.length === 0) {
      formDataCopy.config.audios = [
        {
          audioId: '',
          testType: 'api',
          playbackDeviceId: '',
          spl: 65,
          playOrder: 0
        }
      ];
    }

    if (!formDataCopy.config.dimensions || Array.isArray(formDataCopy.config.dimensions)) {
      formDataCopy.config.dimensions = { api: [], e2e: [] };
    } else {
      formDataCopy.config.dimensions.api = formDataCopy.config.dimensions.api || [];
      formDataCopy.config.dimensions.e2e = formDataCopy.config.dimensions.e2e || [];
    }

    if (!formDataCopy.config.backgroundNoise) {
      formDataCopy.config.backgroundNoise = { audioId: '', deviceIds: [], spl: 0 };
    } else {
      formDataCopy.config.backgroundNoise.audioId = formDataCopy.config.backgroundNoise.audioId ?? '';
      formDataCopy.config.backgroundNoise.deviceIds = Array.isArray(formDataCopy.config.backgroundNoise.deviceIds) 
        ? formDataCopy.config.backgroundNoise.deviceIds 
        : formDataCopy.config.backgroundNoise.deviceId 
          ? [formDataCopy.config.backgroundNoise.deviceId] 
          : [];
      formDataCopy.config.backgroundNoise.spl = formDataCopy.config.backgroundNoise.spl ?? 0;
    }
    
    // 确保tags数组存在
    if (!formDataCopy.tags) {
      formDataCopy.tags = [];
    }

    // 确保group字段存在 - 兼容groupName/group_name
    if (formDataCopy.group === undefined || formDataCopy.group === '') {
      formDataCopy.group = formDataCopy.groupName || formDataCopy.group_name || '';
    }

    // 删除后端返回的原始参数格式，只保留算法需要的参数
    delete formDataCopy.algorithm_params;
    delete formDataCopy.reference_params;

    formDataCopy._originalGroup = formDataCopy.group;
    formDataCopy._originalGroupId = formDataCopy.groupId || formDataCopy.group_id || '';
    console.log('[initFormData] group:', formDataCopy.group, 'groupId:', formDataCopy.groupId, 'group_id:', formDataCopy.group_id);

    // 确保算法类型字段存在
    if (!formDataCopy.algorithmType) {
      formDataCopy.algorithmType = formDataCopy.algorithm_type || initialAlgorithmType || '';
    }
    console.log('[TestCaseModal] 算法类型:', formDataCopy.algorithmType);

    // 加载已有的算法参数（数组转对象）- 兼容 snake_case 和 camelCase
    if (formDataCopy.algorithm_params || formDataCopy.algorithmParams) {
      const params = formDataCopy.algorithm_params || formDataCopy.algorithmParams || [];
      if (Array.isArray(params)) {
        algorithmParams.value = params.reduce((acc: Record<string, any>, item: any) => {
          const code = item.fieldCode || item.field_code;
          const value = item.fieldValue || item.field_value;
          if (code) {
            acc[code] = value;
          }
          return acc;
        }, {});
      } else {
        algorithmParams.value = params;
      }
      console.log('[TestCaseModal] 算法参数已加载:', algorithmParams.value);
    }

    // 加载已有的参考参数（数组转对象）- 兼容 snake_case 和 camelCase
    if (formDataCopy.reference_params || formDataCopy.referenceParams) {
      const params = formDataCopy.reference_params || formDataCopy.referenceParams || [];
      if (Array.isArray(params)) {
        referenceParams.value = params.reduce((acc: Record<string, any>, item: any) => {
          const code = item.fieldCode || item.field_code;
          const value = item.fieldValue || item.field_value;
          if (code) {
            acc[code] = value;
          }
          return acc;
        }, {});
      } else {
        referenceParams.value = params;
      }
      console.log('[TestCaseModal] 参考参数已加载:', referenceParams.value);
    }

    return formDataCopy;
  };

  const localFormData = ref(initFormData());

  // 监听本地数据变化，保存草稿
  watch(() => localFormData.value, (newValues) => {
    if (isInitializing.value) {
      console.log(`[TestCaseModal] 正在初始化，跳过保存草稿`);
      return;
    }
    
    if (!isEditMode.value && draftId.value && newValues && Object.keys(newValues).length > 0) {
      console.log(`[TestCaseModal] 正在保存草稿 (${draftId.value})`);
      modalStore.setDraft(draftId.value, newValues);
    }
  }, { deep: true });

  // 监听标签输入变化
  watch(() => tagsInput.value, (newValue) => {
    if (newValue.endsWith(',') || newValue.endsWith('，')) {
      addTags();
    }
  });

  // 监听分组变化
  watch(() => localFormData.value.group, (newValue) => {
    if (newValue !== 'new-group') {
      newGroupName.value = '';
    }
  });

  // 监听导出配置变化，更新预览数据
watch(
  () => [exportFormData.value.groups, exportFormData.value.testType, exportFormData.value.includeDeleted],
  () => {
    updateExportPreview();
  },
  { deep: true }
);

  // 更新导出预览数据
  let isUpdatingExportPreview = false;
  
  const updateExportPreview = async () => {
    // 防止重复执行
    if (isUpdatingExportPreview) {
      console.log('[Export Preview] 函数正在执行中，跳过重复调用');
      return;
    }
    isUpdatingExportPreview = true;
    
    try {
      exportPreviewData.value = { total: 0, apiCount: 0, e2eCount: 0, groupStats: [] };
      exportCaseIds.value = [];
      
      if (exportFormData.value.groups.length === 0) {
        return;
      }
      
      const fetchAllTestCases = async () => {
        const allTestCases = [];
        let page = 1;
        let hasMore = true;
        
        while (hasMore) {
          const response = await testcasesApi.getAll({ page, perPage: 100 });
          const items = response?.items || [];
          const total = response?.total || 0;
          const pages = response?.pages || 1;
          
          allTestCases.push(...items);
          
          if (page >= pages || items.length === 0) {
            hasMore = false;
          } else {
            page++;
          }
        }
        
        return allTestCases;
      };
      
      const getGroupName = (testCase: TestCase): string => {
        const name = testCase?.group_name || testCase?.group || testCase?.groupName || testCase?.group_id || testCase?.groupId || '';
        return String(name);
      };
      
      const getTypesSet = (testCase: TestCase): Set<string> => {
        const types = new Set<string>();
        const raw = testCase?.type ?? testCase?.testType;
        if (Array.isArray(raw)) {
          for (const t of raw) {
            if (t === 'api' || t === 'e2e') types.add(t);
          }
        } else if (raw === 'api' || raw === 'e2e') {
          types.add(raw);
        }
        const config = testCase?.config || {};
        const audios = Array.isArray(config.audios) ? config.audios : [];
        for (const audio of audios) {
          if (audio?.testType === 'api' || audio?.testType === 'e2e') {
            types.add(audio.testType);
          }
        }
        return types;
      };
      
      const testCases = await fetchAllTestCases();
      
      let filteredCases = [...testCases];
      
      // 按测试组过滤
      const normalize = (s: string | number | undefined | null): string => String(s || '').trim().toLowerCase();
      const selectedGroupsNorm = exportFormData.value.groups.map(normalize);
      
      filteredCases = filteredCases.filter(testCase => {
        const groupName = normalize(getGroupName(testCase));
        return selectedGroupsNorm.includes(groupName);
      });
      
      // 测试类型过滤
      if (exportFormData.value.testType !== 'all') {
        filteredCases = filteredCases.filter(testCase => {
          if (exportFormData.value.testType === 'api') {
            return getTypesSet(testCase).has('api');
          } else if (exportFormData.value.testType === 'e2e') {
            return getTypesSet(testCase).has('e2e');
          }
          return true;
        });
      }
      
      const apiCount = filteredCases.filter(testCase => getTypesSet(testCase).has('api')).length;
      const e2eCount = filteredCases.filter(testCase => getTypesSet(testCase).has('e2e')).length;
      
      const groupStats: GroupStat[] = [];
      exportFormData.value.groups.forEach(group => {
        const groupCases = filteredCases.filter(testCase => normalize(getGroupName(testCase)) === normalize(group));
        groupStats.push({
          name: group,
          total: groupCases.length,
          api: groupCases.filter(testCase => getTypesSet(testCase).has('api')).length,
          e2e: groupCases.filter(testCase => getTypesSet(testCase).has('e2e')).length
        });
      });
      
      exportPreviewData.value = {
        total: filteredCases.length,
        apiCount,
        e2eCount,
        groupStats
      };
      
      exportCaseIds.value = filteredCases.map((testCase: TestCase) => testCase.id).filter((id: string | number | undefined | null) => id !== undefined && id !== null) as string[] | number[];
    } finally {
      isUpdatingExportPreview = false;
    }
  };

  // 评测维度相关状态
  const availableDimensions = ref<Dimension[]>([]);
  const dimensionSearchQuery = ref('');
  const selectedDimensions = ref<{ api: Dimension[]; e2e: Dimension[] }>({ api: [], e2e: [] });

  // 使用维度 composable
  const { fetchAllDimensions, fetchDimensionsByAlgorithmType } = useDimensions();

  // 根据算法类型过滤后的可用维度
  const filteredAvailableDimensions = computed(() => {
    if (!localFormData.value.algorithmType || associatedDimensions.value.length === 0) {
      return availableDimensions.value;
    }
    const associatedIds = new Set(associatedDimensions.value.map(d => d.id));
    return availableDimensions.value.filter(dim => associatedIds.has(dim.id));
  });

  // 过滤后的评测维度
  const filteredDimensions = computed(() => {
    if (!dimensionSearchQuery.value) return filteredAvailableDimensions.value;
    const query = dimensionSearchQuery.value.toLowerCase();
    return filteredAvailableDimensions.value.filter(dim => 
      dim.name.toLowerCase().includes(query) || 
      (dim.description && dim.description.toLowerCase().includes(query))
    );
  });

// 模态窗相关状态
const showAudioModal = ref(false);
const showDimensionModal = ref(false);
const showAudioPreviewModal = ref(false);
const showDeviceModal = ref(false); // 设备选择模态窗
const currentAudioType = ref<'dry' | 'noise'>('dry'); // dry, noise
const currentAudioIndex = ref<number | null>(null);
const currentDimensionType = ref<'api' | 'e2e'>('api'); // api, e2e
const currentDimensionIndex = ref<number | null>(null);
const currentPreviewAudioId = ref<string | null>(null);
const currentPreviewAudioType = ref<'dry' | 'noise'>('dry'); // dry, noise
const currentPreviewDeviceId = ref<string | null>(null); // 预览时使用的设备ID
const currentPreviewSpl = ref(65); // 预览时使用的SPL
const currentPreviewOffset = ref(0); // 预览时使用的offset
const currentDeviceAudioIndex = ref<number | null>(null); // 当前编辑的音频配置索引（用于设备选择）
const initialSelectedDevices = ref<string[]>([]); // 初始选中的设备
const showNoiseDeviceModal = ref(false); // 噪声音频设备选择模态窗
const noiseInitialSelectedDevices = ref<string[]>([]); // 噪声音频初始选中的设备
const showBatchDeviceModal = ref(false); // 批量设置设备模态窗
const batchInitialSelectedDevices = ref<string[]>([]); // 批量设置初始选中的设备
const showCrossDeviceModal = ref(false); // 设备交叉分配模态窗
const crossDeviceInitialSelectedDevices = ref<string[]>([]); // 交叉分配初始选中的设备
const showBatchSplModal = ref(false); // 批量设置声压模态窗
const batchSplValue = ref(65); // 批量设置声压值



// 打开音频选择模态窗
const openAudioSelectModal = (audioType: 'dry' | 'noise', index: number | null = null) => {
  currentAudioType.value = audioType;
  currentAudioIndex.value = index;
  showAudioModal.value = true;
  console.log('[TestCaseModal] 打开音频选择模态框:', { audioType, index, showAudioModal: showAudioModal.value });
  // 监听showAudioModal变化
  console.log('[TestCaseModal] showAudioModal变化:', showAudioModal.value);
};

// 打开维度选择模态窗
const openDimensionSelectModal = (dimensionType: 'api' | 'e2e', index: number) => {
  currentDimensionType.value = dimensionType;
  currentDimensionIndex.value = index;
  showDimensionModal.value = true;
  console.log('[TestCaseModal] 打开维度选择模态框:', { dimensionType, index });
};

// 打开设备选择模态窗
const openDeviceSelectModal = (audioIndex: number) => {
  currentDeviceAudioIndex.value = audioIndex;
  const audioConfig = localFormData.value.config.audios[audioIndex];
  initialSelectedDevices.value = audioConfig.playbackDeviceId ? [audioConfig.playbackDeviceId] : [];
  showDeviceModal.value = true;
  console.log('[TestCaseModal] 打开设备选择模态框:', { audioIndex, initialSelectedDevices: initialSelectedDevices.value });
};

// 打开噪声音频设备选择模态窗
const openNoiseDeviceSelectModal = () => {
  noiseInitialSelectedDevices.value = localFormData.value.config.backgroundNoise.deviceIds || [];
  showNoiseDeviceModal.value = true;
  console.log('[TestCaseModal] 打开噪声音频设备选择模态框:', { noiseInitialSelectedDevices: noiseInitialSelectedDevices.value });
};

// 打开批量设置设备模态窗
const openBatchDeviceModal = () => {
  // 获取当前已选的设备作为默认值
  const e2eAudioConfigs = localFormData.value.config.audios.filter((audio: { testType: string; playbackDeviceId?: string }) => audio.testType === 'e2e' && audio.playbackDeviceId);
  if (e2eAudioConfigs.length > 0) {
    batchInitialSelectedDevices.value = [e2eAudioConfigs[0].playbackDeviceId];
  } else {
    batchInitialSelectedDevices.value = [];
  }
  showBatchDeviceModal.value = true;
  console.log('[TestCaseModal] 打开批量设置设备模态框:', { batchInitialSelectedDevices: batchInitialSelectedDevices.value });
};

// 处理批量设备选择结果
const handleBatchDeviceSelect = (selectedDevices: string[]) => {
  if (selectedDevices.length > 0) {
    const deviceId = selectedDevices[0];
    localFormData.value.config.audios.forEach((audio: { testType: string; playbackDeviceId?: string }) => {
      if (audio.testType === 'e2e') {
        audio.playbackDeviceId = deviceId;
      }
    });
  }
  showBatchDeviceModal.value = false;
  console.log('[TestCaseModal] 批量设置设备完成:', selectedDevices);
};

// 打开设备交叉分配模态窗
const openCrossDeviceModal = () => {
  const e2eAudioConfigs = localFormData.value.config.audios.filter((audio: { testType: string; playbackDeviceId?: string }) => audio.testType === 'e2e' && audio.playbackDeviceId);
  if (e2eAudioConfigs.length > 0) {
    const uniqueDevices = [...new Set(e2eAudioConfigs.map((audio: { playbackDeviceId?: string }) => audio.playbackDeviceId).filter(Boolean))];
    crossDeviceInitialSelectedDevices.value = uniqueDevices as string[];
  } else {
    crossDeviceInitialSelectedDevices.value = [];
  }
  showCrossDeviceModal.value = true;
  console.log('[TestCaseModal] 打开设备交叉分配模态框:', { crossDeviceInitialSelectedDevices: crossDeviceInitialSelectedDevices.value });
};

// 处理设备交叉分配
const handleCrossDeviceSelect = (selectedDevices: string[]) => {
  if (selectedDevices.length > 0) {
    const e2eAudioConfigs = localFormData.value.config.audios.filter((audio: { testType: string }) => audio.testType === 'e2e');
    e2eAudioConfigs.forEach((audio: { playbackDeviceId?: string }, index: number) => {
      audio.playbackDeviceId = selectedDevices[index % selectedDevices.length];
    });
  }
  showCrossDeviceModal.value = false;
  console.log('[TestCaseModal] 设备交叉分配完成:', selectedDevices);
};

// 打开批量设置声压模态窗
const openBatchSplModal = () => {
  const e2eAudioConfigs = localFormData.value.config.audios.filter((audio: { testType: string; spl?: number }) => audio.testType === 'e2e' && audio.spl);
  if (e2eAudioConfigs.length > 0) {
    batchSplValue.value = e2eAudioConfigs[0].spl || 65;
  } else {
    batchSplValue.value = 65;
  }
  showBatchSplModal.value = true;
  console.log('[TestCaseModal] 打开批量设置声压模态框:', { batchSplValue: batchSplValue.value });
};

// 处理批量声压设置确认
const handleBatchSplConfirm = () => {
  localFormData.value.config.audios.forEach((audio: { testType: string; spl?: number }) => {
    if (audio.testType === 'e2e') {
      audio.spl = batchSplValue.value;
    }
  });
  showBatchSplModal.value = false;
  console.log('[TestCaseModal] 批量设置声压完成:', batchSplValue.value);
};

// 获取噪声音频设备名称
const getNoiseDeviceNames = (): string => {
  const deviceIds = localFormData.value.config.backgroundNoise.deviceIds || [];
  if (deviceIds.length === 0) return '';
  const names = deviceIds.map(id => getDeviceName(id));
  return names.join(', ');
};

// 根据音频ID获取音频名称
const getAudioName = (audioId: string | number): string => {
  const allAudios = [...dryAudios.value, ...noiseAudios.value];
  const audio = allAudios.find(a => String(a.id) === String(audioId));
  return audio ? audio.name : '未知音频';
};

// 根据音频ID获取音频标签
const getAudioTags = (audioId: string | number): string => {
  const allAudios = [...dryAudios.value, ...noiseAudios.value];
  const audio = allAudios.find(a => String(a.id) === String(audioId));
  if (audio && audio.tags) {
    if (Array.isArray(audio.tags)) {
      return audio.tags.join(', ');
    }
    return String(audio.tags);
  }
  return '';
};

const MAX_AUDIO_TAGS = 8;
const expandedAudioTags = ref<Record<string, boolean>>({});
const showTagSelector = ref(false);
const selectedTagsForInterleave = ref<string[]>([]);
const interleaveOrder = ref<'asc' | 'desc'>('asc');

const toggleTagSelector = () => {
  showTagSelector.value = !showTagSelector.value;
  if (showTagSelector.value) {
    selectedTagsForInterleave.value = [];
  }
};

const toggleTagSelection = (tag: string) => {
  const index = selectedTagsForInterleave.value.indexOf(tag);
  if (index === -1) {
    selectedTagsForInterleave.value.push(tag);
  } else {
    selectedTagsForInterleave.value.splice(index, 1);
  }
};

const showTagDeviceSelector = ref(false);
const tagDeviceMapping = ref<Record<string, string>>({});

const toggleTagDeviceSelector = () => {
  showTagDeviceSelector.value = !showTagDeviceSelector.value;
  if (showTagDeviceSelector.value) {
    const tags = getUniqueTagsFromConfigs();
    const mapping: Record<string, string> = {};
    tags.forEach(tag => {
      mapping[tag] = mapping[tag] || '';
    });
    tagDeviceMapping.value = mapping;
  }
};

const getTagDeviceMapping = computed(() => {
  return Object.entries(tagDeviceMapping.value || {}).filter(([_, deviceId]) => deviceId && deviceId.length > 0);
});

const hasValidTagDeviceMapping = computed(() => {
  return Object.values(tagDeviceMapping.value || {}).some(v => v && v.length > 0);
});

const getDeviceForTag = (tag: string): string => {
  if (!tagDeviceMapping.value) return '';
  return tagDeviceMapping.value[tag] || '';
};

const getTagAudioCount = (tag: string): number => {
  if (!tagDeviceMapping.value || Object.keys(tagDeviceMapping.value).length === 0) {
    return 0;
  }
  if (!localFormData.value?.config?.audios) {
    return 0;
  }
  let count = 0;
  localFormData.value.config.audios.forEach((audioConfig: any) => {
    if (audioConfig.audioId) {
      const tags = getNormalizedTags(getAudioTags(audioConfig.audioId));
      const firstMatchedTag = tags.find((t: string) =>
        tagDeviceMapping.value && tagDeviceMapping.value[t] && tagDeviceMapping.value[t].length > 0
      );
      if (firstMatchedTag === tag) {
        count++;
      }
    }
  });
  return count;
};

const updateTagDeviceMapping = (tag: string, deviceId: string) => {
  if (!tagDeviceMapping.value) return;
  tagDeviceMapping.value[tag] = deviceId;
};

const assignDeviceByTags = () => {
  if (!hasValidTagDeviceMapping.value) {
    return;
  }
  if (!localFormData.value?.config?.audios) {
    return;
  }
  localFormData.value.config.audios.forEach((audioConfig: any) => {
    if (audioConfig.audioId) {
      const tags = getNormalizedTags(getAudioTags(audioConfig.audioId));
      const firstMatchedTag = tags.find((tag: string) =>
        tagDeviceMapping.value && tagDeviceMapping.value[tag] && tagDeviceMapping.value[tag].length > 0
      );
      if (firstMatchedTag) {
        audioConfig.playbackDeviceId = tagDeviceMapping.value[firstMatchedTag];
      }
    }
  });
  showTagDeviceSelector.value = false;
  tagDeviceMapping.value = {};
  console.log('[TestCaseModal] 标签设备分配完成');
};

const toggleAudioTags = (audioId: string | number) => {
  const key = String(audioId);
  expandedAudioTags.value[key] = !expandedAudioTags.value[key];
};

const getNormalizedTags = (tagsStr: string): string[] => {
  if (!tagsStr) return [];
  if (typeof tagsStr === 'string') {
    return tagsStr.split(',').map(t => t.trim()).filter(t => t);
  }
  return [];
};

// 根据设备ID获取设备名称
const getDeviceName = (deviceId: string | number): string => {
  const device = playbackDevices.value.find(d => String(d.id) === String(deviceId));
  if (device) {
    return `${device.name} (通道 ${device.channelIndex})`;
  }
  // 检查是否是扫描设备（格式：name-channel_index）
  const deviceIdStr = String(deviceId);
  const scanDeviceMatch = deviceIdStr.match(/^(.*)-(\d+)$/);
  if (scanDeviceMatch) {
    return `${scanDeviceMatch[1]} (通道 ${scanDeviceMatch[2]}) [扫描]`;
  }
  return '未知设备';
};

// 选择音频后的回调
const handleAudioSelect = (audio: AudioItem) => {
  const audioId = audio.id;
  if (currentAudioType.value === 'dry' && currentAudioIndex.value !== null) {
    localFormData.value.config.audios[currentAudioIndex.value].audioId = String(audioId);
    if (!dryAudios.value.find(a => String(a.id) === String(audioId))) {
      dryAudios.value.push(audio);
    }
  } else if (currentAudioType.value === 'noise') {
    localFormData.value.config.backgroundNoise.audioId = String(audioId);
    if (!noiseAudios.value.find(a => String(a.id) === String(audioId))) {
      noiseAudios.value.push(audio);
    }
  }
  syncAudioTagsToCase();
  showAudioModal.value = false;
};

// 多选音频后的回调 - 添加多个音频配置卡片
const handleMultipleAudioSelect = (audios: AudioItem[]) => {
  const sortedAudios = [...audios].sort((a, b) => {
    const nameA = (a.name || '').toLowerCase();
    const nameB = (b.name || '').toLowerCase();
    return nameA.localeCompare(nameB);
  });
  
  if (currentAudioType.value === 'dry') {
    if (currentAudioIndex.value !== null) {
      const sourceAudio = localFormData.value.config.audios[currentAudioIndex.value];
      localFormData.value.config.audios[currentAudioIndex.value].audioId = String(sortedAudios[0].id);
      if (!dryAudios.value.find(a => String(a.id) === String(sortedAudios[0].id))) {
        dryAudios.value.push(sortedAudios[0]);
      }
      for (let i = 1; i < sortedAudios.length; i++) {
        localFormData.value.config.audios.push({
          audioId: String(sortedAudios[i].id),
          testType: sourceAudio.testType || 'api',
          playbackDeviceId: sourceAudio.playbackDeviceId || '',
          spl: sourceAudio.spl ?? 65,
          playOrder: localFormData.value.config.audios.length
        });
        if (!dryAudios.value.find(a => String(a.id) === String(sortedAudios[i].id))) {
          dryAudios.value.push(sortedAudios[i]);
        }
      }
    } else {
      for (const audio of sortedAudios) {
        localFormData.value.config.audios.push({
          audioId: String(audio.id),
          testType: 'api',
          playbackDeviceId: '',
          spl: 65,
          playOrder: localFormData.value.config.audios.length
        });
        if (!dryAudios.value.find(a => String(a.id) === String(audio.id))) {
          dryAudios.value.push(audio);
        }
      }
    }
  } else if (currentAudioType.value === 'noise') {
    localFormData.value.config.backgroundNoise.audioId = String(sortedAudios[0].id);
    if (!noiseAudios.value.find(a => String(a.id) === String(sortedAudios[0].id))) {
      noiseAudios.value.push(sortedAudios[0]);
    }
  }
  syncAudioTagsToCase();
  showAudioModal.value = false;
};

const handleSelectCurrentPage = () => {
  console.log('[TestCaseModal] handleSelectCurrentPage called');
};

const handleSelectAllPages = () => {
  console.log('[TestCaseModal] handleSelectAllPages called');
};

const handleToggleSelectAll = () => {
  console.log('[TestCaseModal] handleToggleSelectAll called');
};

// 检查维度是否已被选择
const isDimensionSelected = (dimensionName: string, dimensionType: 'api' | 'e2e'): boolean => {
  const dimensions = localFormData.value.config.dimensions[dimensionType];
  return dimensions.some(dim => dim.name === dimensionName);
};

// 切换维度选择状态
const toggleDimensionSelection = (dimension: Dimension, dimensionType: 'api' | 'e2e') => {
  const dimensions = localFormData.value.config.dimensions[dimensionType];
  const index = dimensions.findIndex(dim => dim.name === dimension.name);
  
  if (index > -1) {
    // 移除已选择的维度
    dimensions.splice(index, 1);
  } else {
    // 添加新维度，包含id字段
    dimensions.push({
      id: dimension.id,
      name: dimension.name,
      weight: 50, // 默认权重
      threshold: 80 // 默认阈值
    });
  }
};

// 选择维度后的回调
const handleDimensionSelect = (dimension: Dimension) => {
  if (currentDimensionType.value === 'api' && currentDimensionIndex.value !== null) {
    localFormData.value.config.dimensions.api[currentDimensionIndex.value] = { ...localFormData.value.config.dimensions.api[currentDimensionIndex.value], id: dimension.id, name: dimension.name };
  } else if (currentDimensionType.value === 'e2e' && currentDimensionIndex.value !== null) {
    localFormData.value.config.dimensions.e2e[currentDimensionIndex.value] = { ...localFormData.value.config.dimensions.e2e[currentDimensionIndex.value], id: dimension.id, name: dimension.name };
  }
  showDimensionModal.value = false;
};

// 处理设备选择结果
const handleDeviceSelect = (selectedDevices: string[]) => {
  if (currentDeviceAudioIndex.value !== null && selectedDevices.length > 0) {
    const deviceId = selectedDevices[0];
    localFormData.value.config.audios[currentDeviceAudioIndex.value].playbackDeviceId = deviceId;
  }
  showDeviceModal.value = false;
};

// 处理噪声音频设备选择结果
const handleNoiseDeviceSelect = (selectedDevices: string[]) => {
  localFormData.value.config.backgroundNoise.deviceIds = selectedDevices;
  showNoiseDeviceModal.value = false;
  console.log('[TestCaseModal] 噪声音频设备选择结果:', selectedDevices);
};

// 清除噪声配置
const clearNoiseConfig = () => {
  localFormData.value.config.backgroundNoise.audioId = '';
  localFormData.value.config.backgroundNoise.deviceIds = [];
  localFormData.value.config.backgroundNoise.spl = 0;
};

const convertDimensionIdsToObjects = () => {
  // Convert API dimensions
  const apiDimensions = localFormData.value.config.dimensions.api;
  localFormData.value.config.dimensions.api = apiDimensions.map((dim: Dimension | string) => {
    if (typeof dim === 'string') {
      // It's an ID, find the dimension in availableDimensions
      const dimension = availableDimensions.value.find(d => String(d.id) === dim);
      if (dimension) {
        return {
          id: dimension.id,
          name: dimension.name,
          weight: 50, // Default weight
          threshold: 80 // Default threshold
        };
      }
      return dim;
    }
    return dim;
  });

  // Convert E2E dimensions
  const e2eDimensions = localFormData.value.config.dimensions.e2e;
  localFormData.value.config.dimensions.e2e = e2eDimensions.map((dim: Dimension | string) => {
    if (typeof dim === 'string') {
      // It's an ID, find the dimension in availableDimensions
      const dimension = availableDimensions.value.find(d => String(d.id) === dim);
      if (dimension) {
        return {
          id: dimension.id,
          name: dimension.name,
          weight: 50, // Default weight
          threshold: 80 // Default threshold
        };
      }
      return dim;
    }
    return dim;
  });
};

onMounted(async () => {
  await loadResources();
  await loadTestGroups();
  await loadDimensions();
  
  // Convert dimension IDs to objects
  convertDimensionIdsToObjects();
  
  // 初始化标签输入
  if (localFormData.value.tags) {
    tagsInput.value = localFormData.value.tags.join(', ');
  }
});

// 加载测试用例组
async function loadTestGroups() {
  try {
    const groupsRes = await testcasesApi.getGroups();
    const groups = groupsRes?.items || [];
    console.log('[loadTestGroups] 原始测试组数据:', groups);
    // 尝试多种可能的属性名来获取测试组名称
    testCaseGroups.value = Array.isArray(groups) ? groups.map((group: TestCaseGroupItem) => {
      return group.name || group.group || group.id || String(group);
    }).filter(Boolean) : [];
    console.log('[loadTestGroups] 处理后的测试组名称:', testCaseGroups.value);
  } catch (err) {
    console.error('加载测试用例组失败:', err);
    testCaseGroups.value = [];
  }
}

// 加载评测维度
async function loadDimensions(algorithmType?: string) {
  try {
    let dimensions;
    if (algorithmType) {
      dimensions = await fetchDimensionsByAlgorithmType(algorithmType);
    } else {
      dimensions = await fetchAllDimensions({ forceRefresh: true });
    }
    const uniqueDimensions: Dimension[] = [];
    const dimensionNames = new Set();
    for (const dim of dimensions) {
      if (!dimensionNames.has(dim.name)) {
        dimensionNames.add(dim.name);
        uniqueDimensions.push(dim as Dimension);
      }
    }
    availableDimensions.value = uniqueDimensions;
  } catch (err) {
    console.error('加载评测维度失败:', err);
    availableDimensions.value = [];
  }
}

// 添加标签
const addTags = () => {
  if (!localFormData.value.tags) {
    localFormData.value.tags = [];
  }
  
  const tags = tagsInput.value
    .split(/[，,]/)
    .map(tag => tag.trim())
    .filter(tag => tag && !localFormData.value.tags.includes(tag));
  
  localFormData.value.tags = [...localFormData.value.tags, ...tags];
  tagsInput.value = '';
};

// 删除标签
const removeTag = (index: number) => {
  localFormData.value.tags.splice(index, 1);
};

// 试听音频功能
const previewAudio = async (audioId: string, audioType: 'dry' | 'noise' = 'dry') => {
  if (!audioId) {
    alert('请先选择音频');
    return;
  }
  
  currentPreviewAudioId.value = audioId;
  currentPreviewAudioType.value = audioType;
  
  // 检查当前音频配置的测试类型
  // 对于API测试类型，直接使用AudioPlayerModal播放，不需要设备选择
  // 对于E2E测试类型，需要先选择设备
  const currentAudioConfig = localFormData.value.config.audios.find((config: { audioId: string }) => config.audioId === audioId);
  if (currentAudioConfig && currentAudioConfig.testType === 'api') {
    // API测试音频：直接播放，不需要设备选择
    console.log('API Test audio: Directly playing without device selection');
    // 直接打开音频播放器模态窗，传递音频ID和类型
    try {
      const { getModalManager } = await import('../../../utils/modalManager');
      const { MODAL_TYPES } = await import('../../../shared/types');
      
      const modalManager = getModalManager();
      modalManager.open(MODAL_TYPES.AUDIO_PLAYER, {
        visible: true,
        title: '音频播放',
        audioId: audioId,
        audioType: 'api' as const,
        playbackDevices: playbackDevices.value,
        selectedPlaybackDevices: []
      });
    } catch (err: unknown) {
      console.error('打开音频播放器失败:', err);
      alert('音频试听失败: ' + ((err as Error).message || '未知错误'));
    }
  } else {
    // E2E测试音频：获取已配置的设备ID用于预览
    const currentAudioConfigIndex = localFormData.value.config.audios.findIndex((config: { audioId: string }) => config.audioId === audioId);
    console.log('[TestCaseModal] E2E预览，音频ID:', audioId, '索引:', currentAudioConfigIndex);
    if (currentAudioConfigIndex !== -1) {
      const audioConfig = localFormData.value.config.audios[currentAudioConfigIndex];
      const playbackDeviceId = audioConfig.playbackDeviceId;
      console.log('[TestCaseModal] 已配置的设备ID:', playbackDeviceId);
      currentPreviewDeviceId.value = playbackDeviceId || null;
      currentPreviewSpl.value = audioConfig.spl || 65;
      currentPreviewOffset.value = 0;
    } else {
      currentPreviewDeviceId.value = null;
      currentPreviewSpl.value = 65;
      currentPreviewOffset.value = 0;
    }
    showAudioPreviewModal.value = true;
  }
};

// 预览噪声音频
const previewNoiseAudio = async () => {
  const noiseAudioId = localFormData.value.config.backgroundNoise.audioId;
  if (!noiseAudioId) {
    alert('请先选择噪声音频');
    return;
  }
  
  currentPreviewAudioId.value = noiseAudioId;
  currentPreviewAudioType.value = 'noise';
  
  // 获取已配置的噪声设备ID用于预览
  const noiseDeviceIds = localFormData.value.config.backgroundNoise.deviceIds || [];
  console.log('[TestCaseModal] 噪声预览，已配置的设备IDs:', noiseDeviceIds);
  
  currentPreviewDeviceId.value = noiseDeviceIds.length > 0 ? noiseDeviceIds[0] : null;
  currentPreviewSpl.value = localFormData.value.config.backgroundNoise.spl || 65;
  currentPreviewOffset.value = 0;
  
  showAudioPreviewModal.value = true;
};

// 处理音频试听
const handleAudioPreview = async (previewData: {
  audioId: string;
  playbackDeviceId?: string;
  noisePlaybackDeviceIds?: string[];
  playbackMode?: string;
  spl?: number;
  offset?: number;
}) => {
  console.log('[TestCaseModal] handleAudioPreview received:', previewData);
  try {
    // 打开音频播放器模态窗，传递音频ID和选择的播放设备
    const { getModalManager } = await import('../../../utils/modalManager');
    const { MODAL_TYPES } = await import('../../../shared/types');
    
    const modalManager = getModalManager();
    modalManager.open(MODAL_TYPES.AUDIO_PLAYER, {
      visible: true,
      title: '音频播放',
      audioId: previewData.audioId,
      audioType: currentPreviewAudioType.value,
      isTestCasePreview: false, // TestCaseModal中的预览不使用testcases预览接口
      playbackDevices: playbackDevices.value,
      selectedPlaybackDevices: previewData.playbackDeviceId ? [previewData.playbackDeviceId] : previewData.noisePlaybackDeviceIds || [],
      playbackMode: previewData.playbackMode || 'frontend',
      spl: previewData.spl || 65,
      offset: previewData.offset || 0
    });
    console.log('[TestCaseModal] AudioPlayerModal opened with selectedDevices:', previewData.playbackDeviceId ? [previewData.playbackDeviceId] : []);
  } catch (err: unknown) {
    console.error('打开音频播放器失败:', err);
    alert('音频试听失败: ' + ((err as Error).message || '未知错误'));
  }
};

const emit = defineEmits(['close', 'save']);

const getModalTitle = () => {
  switch (props.mode) {
    case 'case':
      return isEditMode.value ? '编辑测试用例' : '新增测试用例';
    case 'group':
      return isEditMode.value ? '编辑测试用例组' : '创建测试用例组';
    case 'import':
      return '批量导入测试用例';
    case 'export':
      return '批量导出测试用例';
    default:
      return '测试用例管理';
  }
};

const setImportFile = (file: File | null): void => {
  if (!file) {
    importFormData.value.file = null;
    importPreviewData.value = null;
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    alert('文件大小不能超过10MB');
    return;
  }

  const validTypes = ['.json', '.xlsx', '.xls'];
  const fileName = file.name.toLowerCase();
  const isValidType = validTypes.some(type => fileName.endsWith(type));
  if (!isValidType) {
    alert('请选择 .json 或 .xlsx/.xls 格式的文件');
    return;
  }

  importFormData.value.file = file;
  updateImportPreview();
};

const triggerImportFileSelect = () => {
  importFileInputRef.value?.click();
};

const handleImportDragEnter = () => {
  isImportDragging.value = true;
};

const handleImportDragOver = () => {
  isImportDragging.value = true;
};

const handleImportDragLeave = () => {
  isImportDragging.value = false;
};

const handleImportDrop = (event: DragEvent) => {
  isImportDragging.value = false;
  const file = event.dataTransfer?.files?.[0] || null;
  setImportFile(file);
  if (importFileInputRef.value) {
    importFileInputRef.value.value = '';
  }
};

// 处理文件选择
const handleFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement | null;
  const file = input?.files?.[0] || null;
  setImportFile(file);
  if (input) {
    input.value = '';
  }
};

// 更新导入预览数据
const updateImportPreview = async () => {
  if (!importFormData.value.file) {
    importPreviewData.value = null;
    return;
  }
  
  try {
    const formData = new FormData();
    formData.append('file', importFormData.value.file);
    
    const response = await testcasesApi.previewImport(formData);
    const data = (response && typeof response === 'object' && 'data' in (response as any))
      ? (response as any).data
      : response;

    if (!data) {
      importPreviewData.value = null;
      return;
    }

    const testCases = data.testCases || data.testcases || [];
    const previewErrors = Array.isArray(data.errors) ? data.errors : [];
    if (previewErrors.length > 0 && testCases.length === 0) {
      const maxLines = 50;
      const shown = previewErrors.slice(0, maxLines).map(String).join('\n');
      const more = previewErrors.length > maxLines ? `\n...（共${previewErrors.length}条）` : '';
      alert(`获取导入预览失败：${previewErrors.length} 个错误\n${shown}${more}`);
      importPreviewData.value = null;
      return;
    }
    const audioConfigs = data.audioConfigs || data.audio_configs || [];
    const apiDimensions = data.apiDimensions || data.api_dimensions || [];
    const e2eDimensions = data.e2eDimensions || data.e2e_dimensions || [];

    importPreviewData.value = {
      total: data.totalRows || data.total_rows || testCases.length,
      items: testCases.map((tc: Record<string, unknown>) => ({
        name: (tc.NAME || tc.name || '未命名') as string,
        type: (tc.TEST_TYPE || tc.testType || tc.type || 'api') as string,
        group: (tc.GROUP_NAME || tc.groupName || tc.group || '未分类') as string,
        operation: (tc.ID || tc.id) ? 'update' as const : 'insert' as const
      })),
      audioConfigsCount: audioConfigs.length,
      apiDimensionsCount: apiDimensions.length,
      e2eDimensionsCount: e2eDimensions.length,
      tagsCount: (data.tags || []).length,
      groupsCount: (data.groups || []).length,
      sheetNames: Object.keys(data).filter(key =>
        Array.isArray((data as any)[key]) && (data as any)[key].length > 0
      )
    };
  } catch (error: any) {
    console.error('获取导入预览失败:', error);
    const errors = Array.isArray(error?.errors) ? error.errors : [];
    if (errors.length > 0) {
      const maxLines = 50;
      const shown = errors.slice(0, maxLines).map(String).join('\n');
      const more = errors.length > maxLines ? `\n...（共${errors.length}条）` : '';
      alert(`获取导入预览失败：${errors.length} 个错误\n${shown}${more}`);
    } else {
      alert('获取导入预览失败: ' + (error?.message || '未知错误'));
    }
    importPreviewData.value = null;
  }
};

// 下载模板文件
const downloadTemplate = async () => {
  try {
    const response = await testcasesApi.downloadTemplate();
    const blob = response instanceof Blob ? response : new Blob([response]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `测试用例导入模板_${new Date().toLocaleDateString()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error: unknown) {
    console.error('下载模板失败:', error);
    alert('下载模板失败: ' + ((error as Error).message || '未知错误'));
  }
};

// 清除导入文件
const clearImportFile = () => {
  setImportFile(null);
  if (importFileInputRef.value) {
    importFileInputRef.value.value = '';
  }
};

// 处理导出格式变化
const handleFormatChange = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  exportFormData.value.format = target.value;
};

// 处理导入提交
const handleImportSubmit = () => {
  if (!importFormData.value.file) {
    alert('请选择要导入的文件');
    return;
  }
  emit('save', {
    mode: 'import',
    data: importFormData.value
  });
  handleClose();
};

// 处理导出提交
const handleExportSubmit = () => {
  if (exportFormData.value.groups.length === 0) {
    alert('请至少选择一个测试组');
    return;
  }
  const ids = Array.isArray(exportCaseIds.value) ? exportCaseIds.value : [];
  console.log('[Export] 导出的用例IDs:', ids);
  console.log('[Export] 导出格式:', exportFormData.value.format);
  console.log('[Export] 选择的测试组:', exportFormData.value.groups);
  
  if (ids.length === 0) {
    alert('没有可导出的用例');
    return;
  }
  emit('save', {
    mode: 'export',
    data: { ...exportFormData.value, ids }
  });
  handleClose();
};

// 播放设备和音频列表
const playbackDevices = ref<PlaybackDevice[]>([]);
const dryAudios = ref<AudioItem[]>([]);
const noiseAudios = ref<AudioItem[]>([]);

// 拖拽排序相关状态
const draggedAudioIndex = ref<number | null>(null);
const dragOverAudioIndex = ref<number | null>(null);
let autoScrollInterval: ReturnType<typeof setInterval> | null = null;
const SCROLL_THRESHOLD = 80;
const SCROLL_SPEED = 10;

// 加载初始数据
async function loadResources() {
  try {
    const [devicesRes, allAudiosRes] = await Promise.all([
      playbackApi.getAll({ perPage: 1000 }),
      audiosApi.getAll({ perPage: 1000 })
    ]);
    
    playbackDevices.value = Array.isArray(devicesRes?.items) ? devicesRes.items as PlaybackDevice[] : [];
    const audios: AudioItem[] = Array.isArray(allAudiosRes?.items) ? allAudiosRes.items : [];
    
    const configuredAudioIds: (string | number)[] = [];
    
    if (localFormData.value.config.audios) {
      for (const audioConfig of localFormData.value.config.audios) {
        if (audioConfig.audioId && !configuredAudioIds.includes(audioConfig.audioId)) {
          configuredAudioIds.push(audioConfig.audioId);
        }
      }
    }
    
    if (localFormData.value.config.backgroundNoise?.audioId) {
      const noiseId = localFormData.value.config.backgroundNoise.audioId;
      if (!configuredAudioIds.includes(noiseId)) {
        configuredAudioIds.push(noiseId);
      }
    }
    
    let dryAudioList: AudioItem[] = audios.filter((a: AudioItem) => a.audioType === 'dry');
    let noiseAudioList: AudioItem[] = audios.filter((a: AudioItem) => a.audioType === 'noise');
    
    const firstPageIds = new Set(audios.map((a: AudioItem) => a.id));
    const missingAudioIds = configuredAudioIds.filter(id => !firstPageIds.has(id));
    
    if (missingAudioIds.length > 0) {
      console.log('[TestCaseModal] 发现已配置但不在第一页的音频，开始批量获取:', missingAudioIds.length);
      try {
        const missingAudiosRes = await audiosApi.getByIds(missingAudioIds);
        const missingAudios: AudioItem[] = Array.isArray(missingAudiosRes) ? missingAudiosRes : (missingAudiosRes?.data ? missingAudiosRes.data : []);
        
        for (const missingAudio of missingAudios) {
          if (missingAudio.audioType === 'dry') {
            dryAudioList.push(missingAudio);
          } else if (missingAudio.audioType === 'noise') {
            noiseAudioList.push(missingAudio);
          } else {
            dryAudioList.push(missingAudio);
          }
        }
        console.log('[TestCaseModal] 批量获取到', missingAudios.length, '个缺失音频');
      } catch (err) {
        console.error('[TestCaseModal] 批量获取音频失败:', err);
      }
    }
    
    dryAudios.value = dryAudioList;
    noiseAudios.value = noiseAudioList;
  } catch (err) {
    console.error('加载资源失败:', err);
  }
}

// 添加音频配置
const addAudioConfig = () => {
  if (!localFormData.value.config.audios) {
    localFormData.value.config.audios = [];
  }
  localFormData.value.config.audios.push({
    audioId: '',
    testType: 'api',
    playbackDeviceId: '',
    spl: 65,
    playOrder: localFormData.value.config.audios.length
  });
};

// 删除音频配置
const removeAudioConfig = (index: number) => {
  if (localFormData.value.config.audios && localFormData.value.config.audios.length > 0) {
    localFormData.value.config.audios.splice(index, 1);
    localFormData.value.config.audios.forEach((audio: { playOrder: number }, i: number) => {
      audio.playOrder = i;
    });
  }
};

// 拖拽排序 - 开始拖动
const handleAudioDragStart = (index: number, event: DragEvent) => {
  draggedAudioIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(index));
  }
};

// 拖拽排序 - 结束拖动
const handleAudioDragEnd = () => {
  draggedAudioIndex.value = null;
  dragOverAudioIndex.value = null;
  if (autoScrollInterval) {
    clearInterval(autoScrollInterval);
    autoScrollInterval = null;
  }
};

// 拖拽排序 - 拖动经过
const handleAudioDragOver = (index: number, event: DragEvent) => {
  event.preventDefault();
  if (draggedAudioIndex.value !== null && draggedAudioIndex.value !== index) {
    dragOverAudioIndex.value = index;
  }

  const target = event.target as HTMLElement;
  const container = target.closest('.form-section');
  if (!container || !event.clientY) return;

  const rect = container.getBoundingClientRect();
  const mouseY = event.clientY;
  const topThreshold = rect.top + SCROLL_THRESHOLD;
  const bottomThreshold = rect.bottom - SCROLL_THRESHOLD;

  if (autoScrollInterval) {
    clearInterval(autoScrollInterval);
    autoScrollInterval = null;
  }

  if (mouseY < topThreshold) {
    autoScrollInterval = setInterval(() => {
      if (container.scrollTop > 0) {
        container.scrollTop -= SCROLL_SPEED;
      }
    }, 16);
  } else if (mouseY > bottomThreshold) {
    autoScrollInterval = setInterval(() => {
      const maxScroll = container.scrollHeight - container.clientHeight;
      if (container.scrollTop < maxScroll) {
        container.scrollTop += SCROLL_SPEED;
      }
    }, 16);
  }
};

// 拖拽排序 - 放置
const handleAudioDrop = (index: number, event: DragEvent) => {
  event.preventDefault();
  if (draggedAudioIndex.value === null || draggedAudioIndex.value === index) {
    draggedAudioIndex.value = null;
    dragOverAudioIndex.value = null;
    return;
  }

  const audios = localFormData.value.config.audios;
  if (!audios || audios.length <= 1) {
    draggedAudioIndex.value = null;
    dragOverAudioIndex.value = null;
    return;
  }

  const oldExpandedStates: Record<string, boolean> = {};
  audios.forEach((config: any) => {
    if (config.audioId) {
      oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
    }
  });

  const draggedItem = audios[draggedAudioIndex.value];
  audios.splice(draggedAudioIndex.value, 1);
  audios.splice(index, 0, draggedItem);

  audios.forEach((audio: { playOrder: number }, i: number) => {
    audio.playOrder = i;
  });

  draggedAudioIndex.value = null;
  dragOverAudioIndex.value = null;

  nextTick(() => {
    Object.keys(oldExpandedStates).forEach((id: string) => {
      expandedAudioTags.value[id] = oldExpandedStates[id];
    });
  });
};

// 复制音频配置
const copyAudioConfig = (index: number) => {
  if (!localFormData.value.config.audios) {
    localFormData.value.config.audios = [];
  }
  const sourceConfig = localFormData.value.config.audios[index];
  const newConfig = {
    audioId: sourceConfig.audioId || '',
    testType: sourceConfig.testType || 'api',
    playbackDeviceId: sourceConfig.playbackDeviceId || '',
    spl: sourceConfig.spl || 65,
    playOrder: sourceConfig.playOrder + 1
  };
  localFormData.value.config.audios.splice(index + 1, 0, newConfig);
  localFormData.value.config.audios.forEach((audio: { playOrder: number }, i: number) => {
    audio.playOrder = i;
  });
};

// 清空所有音频配置
const clearAllAudioConfigs = () => {
  if (localFormData.value.config.audios && localFormData.value.config.audios.length > 0) {
    if (confirm('确定要清空所有音频配置吗？')) {
      localFormData.value.config.audios = [];
    }
  }
};

// 随机调整播放顺序
const shuffleAudioConfigs = () => {
  if (!localFormData.value.config.audios || localFormData.value.config.audios.length <= 1) {
    return;
  }
  const shuffled = [...localFormData.value.config.audios];
  const oldExpandedStates: Record<string, boolean> = {};
  shuffled.forEach((config: any) => {
    if (config.audioId) {
      oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
    }
  });
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  shuffled.forEach((audio: { playOrder: number }, i: number) => {
    audio.playOrder = i;
  });
  localFormData.value.config.audios = shuffled;
  nextTick(() => {
    Object.keys(oldExpandedStates).forEach((id: string) => {
      expandedAudioTags.value[id] = oldExpandedStates[id];
    });
  });
};

// 按文件名排序
const sortByFileName = (order: 'asc' | 'desc') => {
  if (!localFormData.value.config.audios || localFormData.value.config.audios.length <= 1) {
    return;
  }
  const audioIds = localFormData.value.config.audios.map((config: any) => config.audioId).filter(Boolean);
  const audioNames: Record<string, string> = {};
  audioIds.forEach((id: string) => {
    audioNames[id] = getAudioName(id) || '';
  });
  const sorted = [...localFormData.value.config.audios].sort((a: any, b: any) => {
    const nameA = audioNames[a.audioId] || '';
    const nameB = audioNames[b.audioId] || '';
    if (order === 'asc') {
      return nameA.localeCompare(nameB);
    } else {
      return nameB.localeCompare(nameA);
    }
  });
  const oldExpandedStates: Record<string, boolean> = {};
  sorted.forEach((config: any) => {
    if (config.audioId) {
      oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
    }
  });
  sorted.forEach((audio: { playOrder: number }, i: number) => {
    audio.playOrder = i;
  });
  localFormData.value.config.audios = sorted;
  nextTick(() => {
    Object.keys(oldExpandedStates).forEach((id: string) => {
      expandedAudioTags.value[id] = oldExpandedStates[id];
    });
  });
};

// 获取音频配置中的所有唯一标签
const getUniqueTagsFromConfigs = (): string[] => {
  if (!localFormData.value?.config?.audios || localFormData.value.config.audios.length === 0) {
    return [];
  }
  const tagSet = new Set<string>();
  localFormData.value.config.audios.forEach((config: any) => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId));
      tags.forEach((tag: string) => tagSet.add(tag));
    }
  });
  return Array.from(tagSet);
};

// 按标签交叉排列播放顺序
const interleaveByTags = () => {
  console.log('[interleaveByTags] 开始执行');
  console.log('[interleaveByTags] selectedTagsForInterleave:', selectedTagsForInterleave.value);
  console.log('[interleaveByTags] interleaveOrder:', interleaveOrder.value);
  console.log('[interleaveByTags] localFormData.value.config.audios:', localFormData.value.config.audios);

  if (!localFormData.value.config.audios || localFormData.value.config.audios.length <= 1) {
    console.log('[interleaveByTags] 音频数量不足，返回');
    return;
  }
  const selectedTags = [...selectedTagsForInterleave.value];
  if (selectedTags.length < 2) {
    console.log('[interleaveByTags] 选中的标签少于2个，返回');
    return;
  }
  const order = interleaveOrder.value;
  if (order === 'desc') {
    selectedTags.reverse();
  }
  console.log('[interleaveByTags] 处理后的selectedTags:', selectedTags);

  const matchedConfigs: any[] = [];
  const unmatchedConfigs: any[] = [];
  localFormData.value.config.audios.forEach((config: any, idx: number) => {
    if (config.audioId) {
      const tags = getNormalizedTags(getAudioTags(config.audioId));
      console.log(`[interleaveByTags] 音频${idx} tags:`, tags, 'audioId:', config.audioId);
      const hasAnySelectedTag = selectedTags.some(tag => tags.includes(tag));
      console.log(`[interleaveByTags] 音频${idx} hasAnySelectedTag:`, hasAnySelectedTag);
      if (hasAnySelectedTag) {
        matchedConfigs.push({ ...config });
      } else {
        unmatchedConfigs.push({ ...config });
      }
    } else {
      unmatchedConfigs.push({ ...config });
    }
  });
  console.log('[interleaveByTags] matchedConfigs:', matchedConfigs);
  console.log('[interleaveByTags] unmatchedConfigs:', unmatchedConfigs);

  if (matchedConfigs.length < 2) {
    console.log('[interleaveByTags] 匹配的音频少于2个，返回');
    return;
  }
  const groupedByTag: Record<string, any[]> = {};
  selectedTags.forEach(tag => {
    groupedByTag[tag] = matchedConfigs.filter(config => {
      const tags = getNormalizedTags(getAudioTags(config.audioId));
      return tags.includes(tag);
    });
  });
  console.log('[interleaveByTags] groupedByTag:', groupedByTag);

  const maxGroupSize = Math.max(...Object.values(groupedByTag).map(g => g.length));
  const interleaved: any[] = [];
  const usedIndices = new Set<number>();
  for (let i = 0; i < maxGroupSize; i++) {
    for (const tag of selectedTags) {
      if (i < groupedByTag[tag].length) {
        const config = groupedByTag[tag][i];
        const originalIdx = matchedConfigs.indexOf(config);
        if (!usedIndices.has(originalIdx)) {
          usedIndices.add(originalIdx);
          interleaved.push(config);
        }
      }
    }
  }
  const remainingMatched = matchedConfigs.filter((_, idx) => !usedIndices.has(idx));
  interleaved.push(...remainingMatched);
  interleaved.push(...unmatchedConfigs);
  console.log('[interleaveByTags] 最终interleaved:', interleaved);

  const oldExpandedStates: Record<string, boolean> = {};
  localFormData.value.config.audios.forEach((config: any) => {
    if (config.audioId) {
      oldExpandedStates[String(config.audioId)] = expandedAudioTags.value[String(config.audioId)] || false;
    }
  });
  interleaved.forEach((audio: { playOrder: number }, i: number) => {
    audio.playOrder = i;
  });
  localFormData.value.config.audios = interleaved;
  showTagSelector.value = false;
  selectedTagsForInterleave.value = [];
  interleaveOrder.value = 'asc';
  console.log('[interleaveByTags] 完成');
  nextTick(() => {
    Object.keys(oldExpandedStates).forEach((id: string) => {
      expandedAudioTags.value[id] = oldExpandedStates[id];
    });
  });
};

// 添加API评测维度
const addAPIDimension = () => {
  if (!localFormData.value.config.dimensions) {
    localFormData.value.config.dimensions = { api: [], e2e: [] };
  }
  if (!localFormData.value.config.dimensions.api) {
    localFormData.value.config.dimensions.api = [];
  }
  localFormData.value.config.dimensions.api.push({ name: '', weight: 0, threshold: 0 });
};

// 删除API评测维度
const removeAPIDimension = (index: number) => {
  if (localFormData.value.config.dimensions?.api && localFormData.value.config.dimensions.api.length > 1) {
    localFormData.value.config.dimensions.api.splice(index, 1);
  }
};

// 添加E2E评测维度
const addE2EDimension = () => {
  if (!localFormData.value.config.dimensions) {
    localFormData.value.config.dimensions = { api: [], e2e: [] };
  }
  if (!localFormData.value.config.dimensions.e2e) {
    localFormData.value.config.dimensions.e2e = [];
  }
  localFormData.value.config.dimensions.e2e.push({ name: '', weight: 0, threshold: 0 });
};

// 删除E2E评测维度
const removeE2EDimension = (index: number) => {
  if (localFormData.value.config.dimensions?.e2e && localFormData.value.config.dimensions.e2e.length > 1) {
    localFormData.value.config.dimensions.e2e.splice(index, 1);
  }
};

const handleClose = () => {
  console.log('[TestCaseModal] handleClose called');
  emit('close');
};

// 处理遮罩层点击
const handleMaskClick = (event: MouseEvent) => {
  // 点击遮罩层不关闭，只有点击关闭按钮或按ESC才关闭
  if (event.target === event.currentTarget) {
    return;
  }
};

// 监听键盘事件，处理 ESC 退出
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.visible) {
    handleClose();
  }
};

// 监听visible变化，动态添加/移除键盘事件
watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
  } else {
    window.removeEventListener('keydown', handleKeyDown);
  }
}, { immediate: true });

// 在组件卸载时确保移除键盘事件
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

// 获取提交处理函数
const getSubmitHandler = () => {
  switch (props.mode) {
    case 'import':
      return handleImportSubmit;
    case 'export':
      return handleExportSubmit;
    case 'group':
    case 'case':
    default:
      return handleSave;
  }
};

// 获取提交按钮文本
const getSubmitButtonText = () => {
  switch (props.mode) {
    case 'import':
      return '导入';
    case 'export':
      return '导出';
    case 'group':
    case 'case':
    default:
      return '保存';
  }
};

// 验证表单数据
const validateForm = () => {
  const data = localFormData.value;
  
  if (props.mode === 'group') {
    // 验证测试用例组
    if (!data.name || data.name.trim() === '') {
      alert('请输入测试用例组名称');
      return false;
    }
    return true;
  } else if (props.mode === 'case') {
    // 验证测试用例
    
    // 验证基本信息
    if (!data.name || data.name.trim() === '') {
      alert('请输入测试用例名称');
      return false;
    }
    
    if (!data.group || data.group.trim() === '') {
      alert('请选择所属分组');
      return false;
    }
    
    if (data.group === 'new-group' && (!newGroupName.value || newGroupName.value.trim() === '')) {
      alert('请输入新分组名称');
      return false;
    }
    
    // 验证音频配置
    if (!data.config || !data.config.audios || data.config.audios.length === 0) {
      alert('请添加至少一个音频配置');
      return false;
    }
    
    for (let i = 0; i < data.config.audios.length; i++) {
      const audio = data.config.audios[i];
      if (!audio.audioId) {
        alert(`请选择音频配置 ${i + 1} 的音频文件`);
        return false;
      }
      
      if (!audio.testType) {
        alert(`请选择音频配置 ${i + 1} 的测试类型`);
        return false;
      }
      
      if (audio.testType === 'e2e') {
        if (!audio.playbackDeviceId) {
          alert(`请选择音频配置 ${i + 1} 的播放设备`);
          return false;
        }
        
        if (!audio.spl || audio.spl < 0 || audio.spl > 120) {
          alert(`请输入音频配置 ${i + 1} 的有效声压级`);
          return false;
        }
      }
      
      if (audio.playOrder === undefined || audio.playOrder < 0) {
        alert(`请输入音频配置 ${i + 1} 的有效播放顺序`);
        return false;
      }
    }
    
    // 验证评测维度 - 现在是可选的，不需要强制验证
    
    // 检查是否有 API 音频配置
    const hasAPIAudio = data.config.audios.some((audio: { testType: string }) => audio.testType === 'api');
    // 检查是否有 E2E 音频配置
    const hasE2eAudio = data.config.audios.some((audio: { testType: string }) => audio.testType === 'e2e');
    
    // 验证 API 评测维度（如果有的话）
    if (data.config.dimensions.api) {
      for (let i = 0; i < data.config.dimensions.api.length; i++) {
        const dim = data.config.dimensions.api[i];
        if (!dim.name || dim.name.trim() === '') {
          alert(`请输入 API 评测维度 ${i + 1} 的名称`);
          return false;
        }
        
        if (dim.weight === undefined || dim.weight < 0 || dim.weight > 100) {
          alert(`请输入 API 评测维度 ${i + 1} 的有效权重`);
          return false;
        }
        
        if (dim.threshold === undefined || dim.threshold < 0 || dim.threshold > 100) {
          alert(`请输入 API 评测维度 ${i + 1} 的有效阈值`);
          return false;
        }
      }
    }
    
    // 验证 E2E 评测维度
    if (data.config.dimensions.e2e) {
      for (let i = 0; i < data.config.dimensions.e2e.length; i++) {
        const dim = data.config.dimensions.e2e[i];
        if (!dim.name || dim.name.trim() === '') {
          alert(`请输入端到端评测维度 ${i + 1} 的名称`);
          return false;
        }
        
        if (dim.weight === undefined || dim.weight < 0 || dim.weight > 100) {
          alert(`请输入端到端评测维度 ${i + 1} 的有效权重`);
          return false;
        }
        
        if (dim.threshold === undefined || dim.threshold < 0 || dim.threshold > 100) {
          alert(`请输入端到端评测维度 ${i + 1} 的有效阈值`);
          return false;
        }
      }
    }
    
    return true;
  }
  
  return true;
};

const handleSave = () => {
  // 保存前将输入框中尚未添加的标签添加进去
  if (tagsInput.value && tagsInput.value.trim()) {
    addTags();
  }

  // 验证表单数据
  if (!validateForm()) {
    return;
  }
  
  const saveData = Object.assign({}, localFormData.value);

  // 清理可能存在的旧格式参数，确保不会传递空对象或错误格式
  const keysToDelete = ['algorithm_params', 'algorithmParams', 'reference_params', 'referenceParams'];
  keysToDelete.forEach(key => {
    delete saveData[key];
  });

  // 转换 groupId 为 group_id（snake_case）供后端使用
  if (saveData.groupId) {
    saveData.group_id = saveData.groupId;
  }

  if (localFormData.value.algorithmType && Object.keys(algorithmParams.value).length > 0) {
    saveData.algorithm_params = Object.entries(algorithmParams.value).map(([fieldCode, fieldValue]) => ({
      fieldCode,
      fieldValue
    }));
  }

  if (localFormData.value.algorithmType && Object.keys(referenceParams.value).length > 0) {
    saveData.reference_params = Object.entries(referenceParams.value).map(([fieldCode, fieldValue]) => ({
      fieldCode,
      fieldValue
    }));
  }

  if (localFormData.value.algorithmType) {
    saveData.algorithm_type = localFormData.value.algorithmType;
  }

  if (props.mode === 'case' && saveData.group === 'new-group' && newGroupName.value) {
    saveData.group = newGroupName.value;
  }

  if (props.mode === 'case') {
    const originalGroup = localFormData.value._originalGroup || '';
    console.log('[handleSave] originalGroup:', originalGroup, 'current group:', saveData.group, 'groupId (before delete):', saveData.groupId);
    if (saveData.group === 'new-group' || (saveData.group && saveData.group !== originalGroup)) {
      console.log('[handleSave] 删除 groupId 和 group_id');
      delete saveData.groupId;
      delete saveData.group_id;
    }
    console.log('[handleSave] groupId (after delete):', saveData.groupId);
  }

  emit('save', {
    mode: props.mode,
    isEdit: isEditMode.value,
    id: localFormData.value.id,
    data: saveData
  });
};
</script>

<style scoped>
/* 基础模态窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn 0.3s ease;
}

.file-upload.is-dragging {
  border-color: var(--primary-color) !important;
  background: rgba(22, 119, 255, 0.06);
}

@keyframes slideIn {
  from { transform: translateY(-20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6c757d;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
  transform: rotate(90deg);
}

.modal-body {
  padding: 24px;
}

/* 表单样式 */
.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.required {
  color: #dc3545;
  font-weight: bold;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-control:invalid {
  border-color: #dc3545;
  box-shadow: 0 0 0 0.2rem rgba(220, 53, 69, 0.25);
}

/* 表单部分样式 */
.form-section {
  margin: 24px 0;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

/* 表单子部分样式 */
.form-sub-section {
  margin: 16px 0;
  padding: 16px;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e9ecef;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.form-section h4 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #343a40;
}

.audio-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.audio-config-header h4 {
  margin: 0;
}

.audio-config-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.audio-config-actions .btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 6px 12px;
}

.audio-config-actions .btn i {
  margin-right: 4px;
}

.tag-selector-for-interleave {
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.tag-selector-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.interleave-order-options {
  display: flex;
  align-items: center;
  gap: 8px;
}

.interleave-order-options .order-option {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #495057;
}

.interleave-order-options .order-option input {
  accent-color: #1976d2;
}

.interleave-order-options .order-option span {
  font-size: 12px;
}

.tag-selector-header span {
  font-weight: 500;
  color: #495057;
}

.tag-selector-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-checkbox-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
  border-radius: 16px;
  transition: all 0.2s ease;
}

.tag-checkbox-item:hover {
  background-color: #bbdefb;
}

.tag-checkbox-item.selected {
  background-color: #1976d2;
  color: white;
  border-color: #1976d2;
}

.tag-selector-header .btn i {
  margin-right: 4px;
}

.device-assign-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #cbd5e1;
}

.device-assign-header {
  margin-bottom: 12px;
}

.device-assign-header span {
  font-weight: 500;
  color: #495057;
}

.device-selector-container {
  padding: 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  cursor: pointer;
  text-align: center;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.device-selector-container:hover {
  border-color: #1677ff;
  background: #f0f7ff;
  border-style: solid;
}

.selected-device-info {
  color: #333;
  font-size: 14px;
}

.placeholder {
  color: #999;
  font-size: 14px;
}

.tag-device-mapping-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 16px 0;
}

.tag-device-mapping-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.tag-device-mapping-row .tag-name {
  min-width: 60px;
  font-weight: 500;
  color: #1976d2;
}

.tag-device-mapping-row .arrow {
  color: #666;
  font-size: 14px;
}

.tag-device-mapping-row .device-select {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  cursor: pointer;
}

.tag-device-mapping-row .device-select:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.tag-device-mapping-row .audio-count {
  color: #666;
  font-size: 12px;
  min-width: 70px;
}

.tag-device-preview {
  margin-top: 16px;
  padding: 12px;
  background: #e3f2fd;
  border-radius: 6px;
  font-size: 13px;
}

.tag-device-preview .preview-title {
  font-weight: 500;
  color: #1565c0;
  margin-bottom: 8px;
}

.tag-device-preview .preview-item {
  padding: 4px 0;
  color: #1976d2;
}

.tag-device-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #e9ecef;
}

.tag-device-actions .btn i {
  margin-right: 4px;
}

.tag-interleave-preview {
  margin-top: 16px;
  padding: 12px;
  background: #fff3e0;
  border-radius: 6px;
  font-size: 13px;
}

.tag-interleave-preview .preview-title {
  font-weight: 500;
  color: #e65100;
  margin-bottom: 8px;
}

.interleave-order-preview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.interleave-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #fff;
  border: 1px solid #ffcc80;
  border-radius: 16px;
  color: #e65100;
  font-weight: 500;
}

.interleave-arrow {
  color: #ff9800;
  font-size: 12px;
}

.dimension-filter-hint {
  margin: -8px 0 16px 0;
  padding: 8px 12px;
  background-color: #e3f2fd;
  border-radius: 4px;
  font-size: 13px;
  color: #1565c0;
}

.dimension-filter-hint i {
  margin-right: 6px;
}

.form-section h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 500;
  color: #495057;
}

.form-group-section {
  margin-bottom: 16px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.form-group-section h5 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: #6c757d;
}

.help-text {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #6c757d;
}

/* 干声和维度项样式 */
.dry-audio-item,
.dimension-item {
  background-color: white;
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid #e9ecef;
  transition: all 0.2s;
}

.dry-audio-item:hover,
.dimension-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.dry-audio-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 500;
  color: #495057;
}

.audio-header-actions {
  display: flex;
  gap: 8px;
}

.dry-audio-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drag-handle {
  cursor: grab;
  padding: 4px 8px;
  color: #6c757d;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
}

.drag-handle:hover {
  background-color: #e9ecef;
  color: #495057;
}

.drag-handle:active {
  cursor: grabbing;
}

.dry-audio-item.is-dragging {
  opacity: 0.5;
  background-color: #f8f9fa;
}

.dry-audio-item.drag-over {
  border-top: 3px solid #007bff;
  margin-top: -2px;
}

/* 操作按钮组 */
.actions {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

/* 标签样式 */
.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  background-color: #e3f2fd;
  color: #1976d2;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #bbdefb;
}

.tag-input-wrapper {
  position: relative;
}

.auto-generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
}

.auto-generate-btn:hover {
  background-color: #e9ecef;
}

.tag-suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #ced4da;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  max-height: 200px;
  overflow-y: auto;
  z-index: 1000;
  margin-top: 4px;
}

.tag-suggestion-item {
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.tag-suggestion-item:hover {
  background-color: #e3f2fd;
}

.existing-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.existing-tags-label {
  font-size: 12px;
  color: #6c757d;
}

.existing-tag {
  cursor: pointer;
}

.existing-tag:hover {
  background-color: #bbdefb;
  border-color: #1976d2;
}

.existing-tag.already-added {
  opacity: 0.5;
  cursor: default;
}

.more-tags {
  font-size: 12px;
  color: #6c757d;
  padding: 4px 8px;
  cursor: pointer;
}

.more-tags:hover {
  color: #1976d2;
}

.tag-remove {
  background: none;
  border: none;
  color: #1976d2;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.tag-remove:hover {
  background-color: #bbdefb;
  color: #d32f2f;
}

/* 搜索框样式 */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  height: 40px;
  margin: 0;
  padding: 0;
  flex-shrink: 1;
  width: 100%;
  min-width: 200px;
  margin-bottom: 0;
}

.search-icon {
  position: absolute;
  left: 12px;
  color: #6c757d;
  font-size: 14px;
  z-index: 1;
}

.search-input {
  padding-left: 36px;
  padding-right: 60px;
  width: 100%;
  height: 40px;
  box-sizing: border-box;
  border: 1px solid #ced4da;
  border-radius: 6px;
  background-color: #ffffff;
  font-size: 14px;
  margin: 0;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.search-input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

/* 视图切换按钮样式 */
.view-toggle-buttons {
  position: absolute;
  right: 12px;
  display: flex;
  gap: 4px;
  z-index: 1;
}

.btn-xs {
  padding: 4px 8px;
  font-size: 12px;
  height: 28px;
  min-width: 32px;
  background-color: #f8f9fa;
  color: #6c757d;
  border: 1px solid #ced4da;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-xs:hover {
  background-color: #e9ecef;
  color: #495057;
}

.btn-xs.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

/* 音频和维度选择器容器样式 */
.audio-selector-container,
.dimension-selector-container {
  display: flex;
  align-items: center;
  background-color: #f8f9fa;
  border: 1px solid #ced4da;
  border-radius: 6px;
  padding: 8px 12px;
  gap: 12px;
  min-height: 40px;
  box-sizing: border-box;
  transition: all 0.2s ease;
}

.audio-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.audio-tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.audio-tag-label {
  font-size: 12px;
  color: #6c757d;
  margin-right: 4px;
}

.audio-tags-full-row {
  width: 100%;
  flex-basis: 100%;
  margin-top: 8px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.audio-tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  flex: 1;
}

.audio-tags-container .tag-item {
  padding: 3px 8px;
  font-size: 11px;
  cursor: default;
  background-color: transparent;
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
  border-radius: var(--border-radius-full);
  white-space: normal;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-all;
  max-width: 100%;
}

.audio-tags-container .tag-item:hover {
  background-color: var(--primary-light);
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: none;
  box-shadow: none;
}

.audio-tags-container .tag-more {
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  background-color: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
  transition: all 0.2s ease;
}

.audio-tags-container .tag-more:hover {
  background-color: var(--primary-light);
  color: var(--primary-color);
  border-color: var(--primary-color);
  border-style: solid;
}

.audio-tags-container .tag-collapse {
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
  background-color: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px dashed var(--border-color);
  border-radius: var(--border-radius-full);
  white-space: nowrap;
  transition: all 0.2s ease;
}

.audio-tags-container .tag-collapse:hover {
  background-color: var(--warning-light);
  color: var(--warning-color);
  border-color: var(--warning-color);
  border-style: solid;
}

.audio-selector-container:hover,
.dimension-selector-container:hover {
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.1);
}

.selected-audio-info,
.selected-dimension-info {
  flex: 1;
  font-weight: 500;
  color: #495057;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.placeholder {
  flex: 1;
  color: #6c757d;
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* 音频和维度列表容器样式 */
.audio-list-container,
.dimension-list-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ced4da;
  border-radius: 6px;
  padding: 12px;
  background-color: #ffffff;
}

.audio-item,
.dimension-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  margin-bottom: 8px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.audio-item:hover,
.dimension-item:hover {
  background-color: #e3f2fd;
  border-color: #bbdefb;
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.1);
}

.audio-info,
.dimension-info {
  flex: 1;
  overflow: hidden;
}

.audio-name,
.dimension-name {
  font-weight: 600;
  color: #495057;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-meta,
.dimension-description {
  font-size: 12px;
  color: #6c757d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 文件夹样式 */
.audio-folder {
  margin-bottom: 16px;
}

.folder-title {
  font-size: 14px;
  font-weight: 600;
  color: #495057;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #007bff;
}

/* 维度云样式 */
.dimension-cloud-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 20px;
  padding: 16px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.dimension-tag {
  display: inline-block;
  padding: 8px 16px;
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #bbdefb;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  user-select: none;
}

.dimension-tag:hover {
  background-color: #bbdefb;
  border-color: #1976d2;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.2);
}

.dimension-tag.selected {
  background-color: #1976d2;
  color: white;
  border-color: #1976d2;
}

.dimension-tag.selected:hover {
  background-color: #1565c0;
  border-color: #1565c0;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
}

/* 已选择维度配置样式 */
.selected-dimensions-config {
  margin-top: 20px;
  padding: 16px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
}

.selected-dimensions-config h6 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: #495057;
}

.selected-dimension-config-item {
  margin-bottom: 16px;
  padding: 16px;
  background-color: white;
  border: 1px solid #dee2e6;
  border-radius: 4px;
}

.selected-dimension-config-item:last-child {
  margin-bottom: 0;
}

.dimension-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e9ecef;
}

.dimension-config-name {
  font-weight: 600;
  color: #495057;
  font-size: 14px;
}

.dimension-config-fields {
  margin-top: 12px;
}

.dimension-config-fields .form-row {
  gap: 16px;
}

.dimension-config-fields .form-group {
  min-width: 150px;
  flex: 1;
}

/* 按钮样式 */
.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  box-sizing: border-box;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.btn-primary {
  background-color: #007bff;
  color: white;
}

.btn-primary:hover {
  background-color: #0056b3;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-danger {
  background-color: #dc3545;
  color: white;
}

.btn-danger:hover {
  background-color: #c82333;
}

.btn-warning {
  background-color: #fd7e14;
  color: white;
}

.btn-warning:hover {
  background-color: #e8650a;
}

/* 模态窗底部 */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e9ecef;
  background-color: #f8f9fa;
}

.modal-footer button {
  min-width: 100px;
}

/* 空状态样式 */
.empty-state {
  background-color: #e9ecef;
  padding: 24px;
  text-align: center;
  border-radius: 6px;
  margin-bottom: 16px;
  color: #6c757d;
  font-style: italic;
}

/* 导入导出样式 */
.file-upload {
  border: 2px dashed #ced4da;
  border-radius: 6px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background-color: #f8f9fa;
}

.file-upload:hover {
  border-color: #007bff;
  background-color: #e3f2fd;
}

.file-info {
  background-color: white;
  padding: 8px 12px;
  border-radius: 4px;
  border: 1px solid #e9ecef;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.preview-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stat-item {
  background-color: white;
  padding: 8px 16px;
  border-radius: 4px;
  border: 1px solid #e9ecef;
  font-size: 14px;
  font-weight: 500;
  color: #495057;
}

.preview-table-container {
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e9ecef;
  overflow: hidden;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.table th,
.table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #e9ecef;
}

.table th {
  background-color: #f8f9fa;
  font-weight: 600;
  color: #343a40;
  border-bottom: 2px solid #e9ecef;
}

.table tr:hover {
  background-color: #f8f9fa;
}

.status-existing {
  background-color: #fff3cd;
  color: #856404;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-new {
  background-color: #d4edda;
  color: #155724;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge-api {
  background-color: #cce5ff;
  color: #004085;
}

.badge-e2e {
  background-color: #d4edda;
  color: #155724;
}

.preview-more {
  padding: 12px 16px;
  background-color: #f8f9fa;
  text-align: center;
  color: #6c757d;
  font-style: italic;
  font-size: 13px;
}

.form-check {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  padding: 8px 0;
}

.form-check-input {
  cursor: pointer;
  transform: scale(1.1);
}

.form-check-label {
  margin: 0;
  cursor: pointer;
  font-weight: 400;
}

.text-danger {
  color: #dc3545;
  font-size: 13px;
  font-weight: 500;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
    gap: 12px;
  }
  
  .preview-stats {
    flex-direction: column;
    gap: 12px;
  }
  
  .modal-footer {
    flex-direction: column;
  }
  
  .modal-footer button {
    width: 100%;
  }
  
  .tags-container {
    margin-top: 8px;
  }
}
</style>
