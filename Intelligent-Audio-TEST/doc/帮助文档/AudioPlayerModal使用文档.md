# AudioPlayerModal 组件使用文档

## 1. 组件概述

AudioPlayerModal 是一个用于音频播放的模态组件，支持 API 测试和 E2E 测试两种场景，提供了音频预览、播放控制和设备选择等功能。

## 2. 组件位置

`src/components/common/AudioPlayerModal.vue`

## 3. 核心功能

- 音频流式播放支持
- API 测试音频直接播放
- E2E 测试音频设备选择播放
- 播放控制（播放/暂停/停止）
- 进度条拖动定位
- 多设备播放支持
- 错误处理和用户反馈

## 4. 调用位置和场景

### 4.1 TestCaseListContainer.vue

**位置**：`src/components/common/test-case/TestCaseListContainer.vue:170`

**场景**：测试用例列表中的音频预览

**使用方式**：
```vue
<AudioPlayerModal
  :visible="showAudioPlayerModal"
  :audio-id="currentAudioId"
  :audio-type="currentAudioType"
  :selected-devices="selectedPlaybackDevices"
  :selected-playback-devices="selectedPlaybackDevices"
  :is-test-case-preview="true"
  :playback-devices="playbackDevices"
  @close="showAudioPlayerModal = false"
/>
```

### 4.2 TestCaseModal.vue

**位置**：`src/components/common/test-case/TestCaseModal.vue:1086`

**场景**：测试用例编辑时的音频预览

**使用方式**：
```javascript
modalManager.open(MODAL_TYPES.AUDIO_PLAYER, {
  visible: true,
  title: '音频播放',
  audioId: audioId,
  audioType: 'api', // API测试音频类型
  playbackDevices: playbackDevices.value,
  selectedPlaybackDevices: [] // API测试不需要选择设备
});
```

### 4.3 AudioImport.vue

**位置**：`src/views/AudioImport.vue:205`

**场景**：音频导入时的预览播放

**使用方式**：
```vue
<AudioPlayerModal
  :visible="showAudioPlayerModal"
  :audio-id="currentAudioId"
  :audio-type="currentAudioType"
  :selected-devices="[]"
  @close="showAudioPlayerModal = false"
/>
```

### 4.4 AudioListComponent.vue

**位置**：`src/components/common/AudioListComponent.vue:487`

**场景**：音频列表中的单个音频预览

**使用方式**：
```vue
<AudioPlayerModal
  :visible="showAudioPlayerModal"
  :audio-id="currentAudioId"
  :audio-type="currentAudioType"
  :selected-devices="[]"
  @close="showAudioPlayerModal = false"
/>
```

### 4.5 SpecificCaseComparisonComponent.vue

**位置**：`src/components/report/SpecificCaseComparisonComponent.vue:285`

**场景**：测试报告中的音频对比预览

**使用方式**：
```vue
<AudioPlayerModal
  :visible="showAudioPlayerModal"
  :audio-id="currentAudioId"
  :audio-type="currentAudioType"
  :selected-devices="selectedPlaybackDevices"
  :is-test-case-preview="true"
  :playback-devices="playbackDevices"
  @close="showAudioPlayerModal = false"
/>
```

## 5. 主要参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| visible | Boolean | 是 | false | 模态框显示状态 |
| audioId | String/Number | 是 | null | 音频ID |
| audioType | String | 否 | 'dry' | 音频类型（'dry'/'noise'/'api'） |
| selectedDevices | Array | 否 | [] | 已选择的播放设备列表 |
| selectedPlaybackDevices | Array | 否 | [] | 已选择的回放设备列表 |
| isTestCasePreview | Boolean | 否 | false | 是否为测试用例预览 |
| modalId | String | 否 | '' | 模态框ID |
| playbackDevices | Array | 否 | [] | 可用的播放设备列表 |

## 6. 事件说明

| 事件名 | 说明 | 参数 |
| --- | --- | --- |
| close | 关闭模态框 | - |
| play | 开始播放 | - |
| pause | 暂停播放 | - |
| stop | 停止播放 | - |
| confirm | 确认操作 | - |
| cancel | 取消操作 | - |
| save | 保存操作 | - |

## 7. 使用场景分析

### 7.1 用例CRUD模态窗内场景

#### 7.1.1 API测试音频预览
- **场景描述**：在测试用例创建/编辑模态窗内预览API测试音频
- **触发条件**：在 TestCaseModal.vue 中，当音频配置的 `testType === 'api'` 时
- **调用方式**：设置 `audioType='api'`
- **播放机制**：直接在前端浏览器播放，不需要调用后端预览接口
- **音频流URL**：`${apiBaseUrl}/audios/${audioId}/stream`
- **核心代码位置**：TestCaseModal.vue:1086
- **接口调用**：无需调用后端预览接口，直接请求音频流
- **payload**：无

#### 7.1.2 E2E测试音频预览
- 用户打开音频预览模态窗
- 首先看到 播放模式选择 （必选）
- 前端扬声器播放 ：音频将通过浏览器前端直接播放，无需选择设备
- 后端扬声器播放 ：音频将通过选择的设备在后端播放
- 只有选择了 后端扬声器播放 时，才会显示 播放设备选择 区域
- 根据选择的设备类型（干声/噪声），显示对应的设备选择控件

- **场景描述**：在测试用例创建/编辑模态窗内预览E2E测试音频
- **触发条件**：在 TestCaseModal.vue 中，当音频配置的 `testType === 'e2e'` 时
- **调用方式**：设置 `audioType='dry'` 或 `audioType='noise'`
- **设备选择**：通过 AudioPreviewModal 组件选择播放设备
- **播放机制**：选择设备后调用后端音频预览接口
- **核心代码位置**：TestCaseModal.vue:1101
- **接口调用**：`POST /audios/${audioId}/preview`
- **payload**：
  ```json
  {
    "deviceUniqueIds": ["设备唯一ID1", "设备唯一ID2"],
    "playbackDeviceId": "设备ID",
    "playbackDeviceIds": ["设备ID1", "设备ID2"],
    "spl": 65.0,
    "offset": 0
  }
  ```
#### 7.1.3 E2E测试噪声音频预览
- **场景描述**：在测试用例创建/编辑模态窗内预览E2E测试噪声音频
- **触发条件**：在 TestCaseModal.vue 中，当音频配置的 `testType === 'e2e'` 时
- **调用方式**：设置 `audioType='dry'` 或 `audioType='noise'`
- **设备选择**：通过 AudioPreviewModal 组件选择播放设备
- **播放机制**：选择设备后调用后端音频预览接口
- **核心代码位置**：TestCaseModal.vue:1101
- **接口调用**：`POST /audios/${audioId}/preview`
- **payload**：
  ```json
  {
    "deviceUniqueIds": ["设备唯一ID1", "设备唯一ID2"],
    "playbackDeviceId": "设备ID",
    "playbackDeviceIds": ["设备ID1", "设备ID2"],
    "spl": 65.0,
    "offset": 0
  }
  ```

### 7.2 用例预览场景

#### 7.2.1 API测试用例预览
- **场景描述**：在测试用例预览功能中播放API测试用例音频
- **调用方式**：设置 `isTestCasePreview=true` 和 `audioType='api'`
- **播放机制**：直接在前端浏览器播放，不需要调用后端用例预览接口
- **音频流URL**：`${apiBaseUrl}/audios/${audioId}/stream`
- **使用位置**：TestCaseListContainer.vue、测试报告页面
- **特点**：直接播放音频文件流，独立于后端预览服务
- **接口调用**：无需调用后端用例预览接口，直接请求音频流
- **payload**：无

#### 7.2.2 E2E测试用例预览
- **场景描述**：在测试用例预览功能中播放E2E测试用例音频
- **播放机制**：调用后端测试用例预览接口
- **API接口**：`POST /testcases/${testCaseId}/preview`
- **设备处理**：可预设播放设备或动态选择
- **使用位置**：TestCaseListContainer.vue、TestExecutionComponent.vue
- **特点**：通过后端服务控制实际硬件设备播放
- **接口调用**：`POST /testcases/${testCaseId}/preview`
- **payload**：
  ```json
  {
    "offset": 0,
    "preview_type": "e2e"
  }
  ```

### 7.3 普通音频预览场景
- 用户打开音频预览模态窗
- 首先看到 播放模式选择 （必选）
- 前端扬声器播放 ：音频将通过浏览器前端直接播放，无需选择设备
- 后端扬声器播放 ：音频将通过选择的设备在后端播放
- 只有选择了 后端扬声器播放 时，才会显示 播放设备选择 区域
- 根据选择的设备类型（干声/噪声），显示对应的设备选择控件
- **场景描述**：直接播放本地或上传的音频文件
- **调用方式**：设置 `audioType='dry'` 或 `audioType='noise'` 或 `audioType='prompt'`
- **播放机制**：调用后端音频预览接口，通过外部设备播放
- **使用位置**：AudioImport.vue、AudioListComponent.vue
- **特点**：用于音频管理功能中的文件预览
- **接口调用**：`POST /audios/${audioId}/preview`
- **payload**：
  ```json
  {
    "deviceUniqueIds": ["设备唯一ID1", "设备唯一ID2"],
    "offset": 0
  }
  ```
- **请求类型**：POST请求，需要传递设备信息
- **设备处理**：可选择播放设备或使用默认设备

### 7.4 停止预览接口

所有场景下的音频预览都可以通过以下接口停止：

#### 7.4.1 停止音频预览
- **接口调用**：`POST /audios/${audioId}/stop-preview`
- **payload**：无

#### 7.4.2 停止测试用例预览
- **接口调用**：`POST /testcases/${testCaseId}/stop_preview`
- **payload**：无

## 8. 最佳实践

1. **音频ID传递**：确保传递的 `audioId` 是有效的音频数据库ID，而非测试用例ID或其他ID
2. **音频类型设置**：根据实际情况正确设置 `audioType`，避免播放失败
3. **设备选择**：E2E测试场景下，确保正确获取和传递播放设备列表
4. **错误处理**：添加适当的错误处理机制，对无效音频ID或播放失败进行友好提示
5. **模态框管理**：使用统一的模态框管理工具（modalManager）进行组件调用

## 9. 常见问题及解决方案

### 9.1 音频流URL错误

**问题**：API测试场景下，音频流URL拼接错误，导致404
**解决方案**：确保 `audioId` 是有效的音频ID，而非测试用例ID

### 9.2 设备选择失败

**问题**：E2E测试场景下，设备选择后无法播放
**解决方案**：检查设备ID传递是否正确，确保设备已正确配置

### 9.3 跨场景使用问题

**问题**：在API测试场景下传递了E2E测试参数
**解决方案**：根据测试类型，正确设置组件参数，避免参数混淆

## 10. 代码优化建议

1. **统一参数验证**：在组件内部添加参数验证，对无效参数进行提示
2. **标准化调用方式**：建议所有调用都通过 modalManager 进行，便于统一管理
3. **增强错误处理**：添加更详细的错误日志和用户提示
4. **优化音频加载体验**：添加加载状态和缓冲提示
5. **支持更多音频格式**：增强对不同音频格式的支持

## 11. 总结

AudioPlayerModal 是一个功能强大的音频播放组件，支持多种测试场景和使用方式。在使用过程中，需要注意正确传递参数，根据测试类型选择合适的调用方式，确保音频播放功能正常运行。通过统一的模态框管理和标准化的调用方式，可以提高组件的可维护性和易用性。