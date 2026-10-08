# 智能语音测试系统设计系统

## 1. 设计哲学

### 视觉标识：轻量级科技 + 商业专业
- 完美平衡前沿科技美学与企业专业感
- 简洁线条、有目的的间距和精致色彩调色板，传达创新与可靠性
- 每个视觉元素都服务于功能目的，同时保持视觉吸引力

### 技术集成专业知识
- 深入理解Electron的独特特性，包括窗口管理、原生OS集成和性能考虑
- 设计时充分考虑HTML可视化能力、Tailwind CSS响应式模式，以及前端View层、前端Controller逻辑和Flask+PostgreSql后端服务之间的数据流

## 2. 颜色架构

### 主调色板
- **温暖橙色 (#FF6A00)**：主导交互元素 - 按钮、图标、关键标题和数据焦点。营造活力，吸引对关键操作和信息的关注
- **科技蓝色 (#1677FF)**：支持模块差异化 - 侧边栏导航、功能类别标签、次要交互。创建视觉层次结构，不与主要元素竞争

### 中性基础
- **文本层次结构**：使用 #333333 作为主要内容，#777777 作为次要信息
- **背景**：采用 #F5F5F5 和白色，最大限度减少视觉干扰，保持对内容的关注

### 特殊处理
- 关键模块（PostgreSql延迟指示器、Flask接口状态）接收微妙渐变（从 #FF6A00/5 到 #FF6A00/10 或从 #1677FF/5 到 #1677FF/10），增加深度而不会使简洁美学过于复杂

### 颜色变量
```css
:root {
    /* 主色调 */
    --primary-color: #FF6A00;
    --primary-light: rgba(255, 106, 0, 0.1);
    --primary-dark: #E65C00;
    --primary-gradient: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-dark) 100%);
    
    /* 辅助色 */
    --secondary-color: #1677FF;
    --secondary-light: rgba(22, 119, 255, 0.1);
    --secondary-dark: #0958D9;
    --secondary-gradient: linear-gradient(135deg, var(--secondary-color) 0%, var(--secondary-dark) 100%);
    
    /* 功能色 */
    --success-color: #52C41A;
    --success-light: rgba(82, 196, 26, 0.1);
    --warning-color: #FFA940;
    --warning-light: rgba(255, 169, 64, 0.1);
    --danger-color: #F5222D;
    --danger-light: rgba(245, 34, 45, 0.1);
    --info-color: #1890FF;
    
    /* 中性色 */
    --text-primary: #333333;
    --text-secondary: #777777;
    --text-tertiary: #AAAAAA;
    --text-light: #999999;
    --text-disabled: #CCCCCC;
    --dark-color: #262626;
    --gray-color: #737373;
    --gray-light-color: #F0F0F0;
    --light-color: #FAFAFA;
    --white-color: #FFFFFF;
    
    /* 背景色 */
    --background-primary: #FFFFFF;
    --background-secondary: #F5F5F5;
    --background-tertiary: #F0F0F0;
    
    --border-color: var(--gray-light-color);
}
```

## 3. 排版与布局系统

### 网格框架
- 核心内容区域使用居中容器，具有响应式网格列（基于复杂性的2列或3列）
- 模块间距遵循二级元素的 gap-6，一级模块的 gap-8，确保一致的节奏

### 排版层次结构
- **H1**：text-4xl font-bold - 页面标题
- **H2**：text-3xl font-bold - 部分标题
- **H3**：text-xl font-semibold - 模块标题
- **正文**：text-lg - 内容
- **次要文本**：#777777 + text-base - 注释和元数据

### 字体变量
```css
:root {
    --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    --font-size-xs: 12px;
    --font-size-sm: 14px;
    --font-size-md: 16px;
    --font-size-lg: 18px;
    --font-size-xl: 20px;
    --font-size-xxl: 24px;
    --font-size-xxxl: 32px;
    
    --font-weight-normal: 400;
    --font-weight-medium: 500;
    --font-weight-semibold: 600;
    --font-weight-bold: 700;
}
```

### 间距策略
- 模块之间的垂直内边距：py-16
- 模块内的间距：mb-8
- 大量空白空间可防止认知过载并为专业演示创造呼吸空间

## 4. 视觉元素与组件

### 图标系统
- Font Awesome线性图标保持一致性 - 用于数据查询的搜索，用于删除的垃圾桶
- 架构图采用最小线条工作和色块，避免装饰性复杂性
- **对齐**：SVG图标在圆形容器中必须严格居中（水平和垂直），严禁偏移

### 卡片设计
- 核心模块（业务数据卡片、功能入口点）使用白色背景，圆角为-xl，阴影为-md
- 悬停状态实现translateY(-5px)提升和shadow-lg扩展，提供清晰的交互反馈

### 卡片变量
```css
:root {
    --card-radius: 16px;
    --card-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    --card-shadow-hover: 0 12px 32px rgba(255, 106, 0, 0.16);
    --card-padding: 24px;
    --card-margin: 16px;
    --card-transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 按钮设计
- 主要按钮使用主色调 (#FF6A00)，次要按钮使用中性色
- 按钮高度：40px
- 边框圆角：8px
- 悬停效果：轻微阴影和缩放

```css
:root {
    --button-height: 40px;
    --button-border-radius: 8px;
    --button-padding: 0 20px;
    --button-transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 输入组件
- 输入框高度：40px
- 边框圆角：8px
- 边框颜色：#E5E5E5
- 聚焦时边框颜色：#FF6A00

```css
:root {
    --input-height: 40px;
    --input-border-radius: 8px;
    --input-border-color: #E5E5E5;
    --input-focus-border-color: #FF6A00;
}
```

## 5. 交互设计

### 导航与滚动
**侧边导航**：使用`aside.main-sidebar`实现侧边导航菜单，固定宽度240px，包含菜单项列表
**菜单项**：每个菜单项包含图标和文本，激活状态有明显的视觉指示
**内容区域**：主内容区域使用`main.main-content`，占据剩余空间

### 响应式适配
**断点策略**：
- **移动端**：< 768px - 单列布局，侧边栏折叠
- **平板/小屏**：768px - 1279px - 双列网格，紧凑布局
- **标准桌面**：1280px - 1439px - 4列统计卡片，2列图表
- **高清桌面**：1440px - 1919px - 增强间距，优化阅读体验
- **超高清/2K**：≥ 1920px - 最大化内容展示，3列图表，动态缩放组件

**布局响应式**：
- 页面使用`container-fluid`实现全宽布局
- 智能网格系统(CSS Grid/Flexbox)自动调整列数
- 在不同分辨率下（全屏、半屏、四分屏）保持功能完整性
- 关键内容区域在2K屏幕上自动扩展，避免过宽的行长

**组件响应式**：
- 卡片、表格等组件根据容器宽度自动调整内容密度
- 字体大小在高清屏幕上自动适配（使用rem/em单位）
- 复杂组件（如图表）支持动态重绘以适应容器变化

### 交互反馈
**按钮状态**：
  - 正常状态：主按钮使用主色调，次按钮使用边框样式
  - 悬停状态：按钮背景色加深，提供明显的视觉反馈
  - 点击状态：按钮轻微压缩，模拟物理按钮的按压效果
  - 禁用状态：降低不透明度，禁止交互

**卡片交互**：卡片悬停时阴影加深，轻微上浮，提供层次感

**加载状态**：
  - 数据加载时显示适当的加载指示器
  - 骨架屏用于内容占位，使用`#F5F5F5`背景色

**操作反馈**：
  - 成功操作：显示成功提示或状态变化
  - 错误操作：显示错误信息
  - 确认操作：对于重要操作，使用确认弹窗防止误操作

## 6. 数据可视化

### 图表库
项目使用Chart.js作为主要的图表库，用于创建各种数据可视化组件。

### 图表类型

#### 环形图
- **用途**：显示数据分布和比例关系，如任务类型分布
- **样式**：
  - 颜色：使用主色调和辅助色调的组合
  - 中心区域：透明或浅色背景
  - 图例：清晰的标签和颜色指示
- **示例**：任务类型分布环形图

#### 折线图
- **用途**：展示时间序列数据和趋势，如任务完成趋势
- **样式**：
  - 线条：主色调，适当的宽度和透明度
  - 填充：轻微的渐变填充
  - X轴：时间标签，适当的间隔
  - Y轴：数值刻度，清晰的标签
- **示例**：任务完成趋势折线图

### 图表容器
- 使用带有`card`类的容器包裹图表
- 容器具有适当的内边距和阴影
- 图表区域使用`chart-container`类，设置合适的高度

### 设计原则
- **色彩协调**：使用主色调`#FF6A00`和辅助色调`#1677FF`
- **最小化装饰**：减少不必要的坐标轴和图例，突出数据清晰度
- **响应式**：图表自动调整大小以适应容器
- **交互**：支持悬停提示，显示详细数据信息

## 7. 布局规范

### 页面结构
1. **页面容器**：使用`container-fluid`实现全宽布局，确保在不同屏幕尺寸下的一致性
2. **侧边栏导航**：
   - 固定宽度240px
   - 使用`aside.main-sidebar`实现
   - 包含菜单项和子菜单，每个菜单项使用`nav__item`类
   - 菜单项包含图标和文本，激活状态使用`active`类
3. **主内容区域**：
   - 使用`main.main-content`实现，占据剩余空间
   - 包含页面标题和内容卡片
   - 使用适当的内边距和间距
4. **头部区域**：
   - 固定高度64px
   - 包含应用标题和用户信息

### 布局变量
```css
:root {
    --sidebar-width: 240px;
    --header-height: 64px;
    --footer-height: 60px;
    --page-margin: 24px;
    --content-min-width: 1024px;
    
    /* 间距 */
    --spacing-xs: 4px;
    --spacing-sm: 8px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
    --spacing-xl: 32px;
    --spacing-xxl: 48px;
    --spacing-xxxl: 64px;
    
    /* 边框与圆角 */
    --border-width: 1px;
    --border-radius-sm: 4px;
    --border-radius-md: 8px;
    --border-radius-lg: 12px;
    --border-radius-xl: 16px;
    --border-radius-xxl: 24px;
    --border-radius-full: 9999px;
    
    /* 阴影 */
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.08);
    --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.1);
    --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.12);
    --shadow-xl: 0 16px 48px rgba(0, 0, 0, 0.16);
    
    /* 过渡 */
    --transition-fast: 0.2s ease;
    --transition-normal: 0.3s ease;
    --transition-slow: 0.5s ease;
    --card-transition: all 0.3s ease;
    
    /* Z-index */
    --z-index-dropdown: 1000;
    --z-index-modal: 2000;
    --z-index-tooltip: 3000;
}
```

## 8. 组件设计规范

### 卡片组件
- **结构**：使用BEM命名规范，包含`card__head`、`card__body`和`card__foot`部分
- **头部**：包含标题(`card__title`)和可选的操作按钮区(`card__action`)
- **主体**：包含主要内容，可以是文本、列表或其他组件
- **底部**：包含操作按钮
- **样式**：白色背景，圆角16px，阴影`var(--shadow-md)`
- **交互**：悬停时提升阴影并轻微上浮

### 表格组件
- **交互行为**：
  - **排序**：点击表头可对列进行升序/降序排序（操作列除外）
  - **列宽调整**：拖动表头右侧边缘可调整列宽
  - **内容截断**：长文本自动显示省略号(...)，需设定最小宽度保证至少显示5个字符，可换行，悬停时立刻显示完整内容(Tooltip)
  - **列头显示**：列头内容过长时应自动换行显示完整内容，而不是使用省略号
  - **操作列**：始终完整显示，空间不足时自动换行，不使用省略号
  - **响应式适配**：根据屏幕尺寸限定显示列数，优先展示核心列，次要列自动隐藏
  - **详情查看**：点击行记录时弹出详情窗，完整显示该记录的所有字段信息（含被隐藏列）
- **结构**：标准HTML表格结构，包含`<thead>`和`<tbody>`，自动应用`.data-table`类
- **表头**：
  - 默认支持排序（显示排序图标）
  - 支持拖动调整宽度
  - 文本禁止选中，指针显示为手型
- **行**：统一的高度和间距，悬停时高亮背景
- **单元格**：
  - 默认：`white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`
  - 操作列：`white-space: normal; overflow: visible;`
- **操作列**：包含编辑、删除等操作按钮，每行一个或横向排列，不允许截断

### 模态框组件
- **结构**：包含遮罩层(`modal-overlay`)和内容层(`modal`)
- **内容层**：包含头部(`modal-header`)、主体(`modal-body`)和底部(`modal-footer`)
- **头部**：包含标题(`modal-title`)和关闭按钮(`modal-close`)
- **底部**：包含操作按钮，如确认、取消
- **样式**：白色背景，圆角16px，阴影`var(--shadow-lg)`
- **位置**：必须在整个页面严格居中（水平和垂直），严禁左对齐或右对齐
- **交互**：
  - 点击遮罩层或关闭按钮可关闭模态框
  - **互斥性**：同一时间只能显示一个弹窗。当新弹窗触发时，必须自动关闭已存在的弹窗

### 编辑窗组件
- **结构**：类似模态框，包含遮罩层(`modal-overlay`)和编辑窗(`edit-window`)
- **位置**：必须在整个页面严格居中（水平和垂直），严禁左对齐；确保在各种屏幕尺寸下的视觉平衡
- **互斥性**：遵循单一弹窗原则，打开新编辑窗时自动关闭其他模态框或编辑窗
- **内容层**：包含头部(`edit-window-header`)、内容区(`edit-window-content`)和底部(`edit-window-footer`)
- **内容区**：包含表单(`edit-form`)，表单使用网格布局(`form-row`和`form-group`)
- **表单元素**：包含输入框、下拉选择框、文本域等
- **样式**：白色背景，圆角16px，阴影`var(--shadow-lg)`

### 按钮组件
- **类型**：主要按钮(`primary`)、次要按钮(`secondary`)、危险按钮(`danger`)、成功按钮(`success`)、文本按钮(`text`)、轮廓按钮(`outline`)
- **大小**：小型(`sm`)、标准(`md`)、大型(`lg`)
- **状态**：支持禁用状态(`disabled`)、动态文本更新
- **样式**：统一的高度(40px)和圆角(8px)，包含图标支持(`font-awesome`)
- **交互**：悬停时有视觉反馈，点击时有轻微的压缩效果

### 进度导航组件 (Progress Navigation)
- **用途**：用于多步骤流程的导航，如API测试流程
- **结构**：包含步骤项(`progress-step`)和连接线(`progress-line`)
- **状态**：激活状态(`active`)显示高亮颜色
- **样式**：步骤包含序号圆圈和标签文本
- **代码示例**：
```html
<div class="progress-nav">
    <div class="progress-step active">
        <div class="progress-step-number">1</div>
        <div class="progress-step-label">选择测试用例</div>
    </div>
    <div class="progress-line active"></div>
    <div class="progress-step">
        <div class="progress-step-number">2</div>
        <div class="progress-step-label">选择被测API</div>
    </div>
</div>
```

### 标签统计卡片组件 (Tag Statistics Card)
- **用途**：展示特定标签的统计信息
- **结构**：包含头部(`tag-card-header`)、指标详情(`tag-stat-details`)
- **头部**：包含图标(`tag-icon`)、名称(`tag-name`)和计数(`tag-case-count`)
- **指标**：包含标签(`metric-label`)、数值(`metric-value`)和进度条(`metric-bar`)
- **交互**：悬停时上浮并加深阴影

### 任务进度组件 (Task Progress)
- **用途**：展示任务完成进度的详细分布
- **结构**：包含头部(`progress-header`)和进度条(`progress-bar-large`)
- **样式**：进度条高度12px，圆角两端
- **颜色**：不同类型使用不同颜色（主色、辅助色等）

### 标签组件
- **类型**：任务标签(`tag-task`)、音频标签(`tag-audio`)、用例标签(`tag-case`)
- **样式**：圆角9999px，轻微的背景色和边框
- **交互**：悬停时有视觉反馈

### 统计卡片组件
- **结构**：包含头部(`stat-header`)、数值(`stat-value`)和底部(`stat-footer`)
- **头部**：包含图标(`stat-icon`)和标签(`stat-label`)
- **底部**：包含变化趋势(`stat-change`)
- **样式**：白色背景，圆角16px，阴影`var(--shadow-md)`

### 表单组件
- **结构**：使用`form-row`和`form-group`组织表单元素
- **输入元素**：统一的高度(40px)和圆角(8px)
- **标签**：清晰的字体和颜色
- **验证**：支持实时反馈和错误信息显示

## 9. 代码规范

### CSS规范
- 使用CSS变量管理所有可配置值
- 采用BEM命名规范
- 模块化组织CSS文件
- 优先使用Flexbox和Grid布局

### HTML规范
- 语义化HTML标签
- 清晰的嵌套结构
- 适当的ARIA属性
- 响应式元标签

### JavaScript规范
- 模块化组织代码
- 使用ES6+特性
- 清晰的函数命名和注释
- 错误处理和边界情况考虑

## 10. 性能考虑

### 加载状态
- **实现**：使用骨架屏和加载指示器，确保在数据获取期间保持布局稳定性
- **骨架屏样式**：使用`#F5F5F5`背景色和适当的圆角
- **指示器位置**：在数据加载的区域显示加载指示器

### 内存管理
- **高效设计**：避免不必要的复杂动画或视觉效果
- **组件复用**：尽可能复用组件，减少DOM元素数量
- **资源优化**：优化图像和其他资源，减少内存占用
- **事件清理**：确保在组件销毁时清理事件监听器，避免内存泄漏

## 11. 跨平台一致性

### 平台特定考虑
- **Windows**：使用Windows风格的按钮和控件
- **macOS**：使用macOS风格的标题栏和控件
- **Linux**：确保与常见Linux桌面环境的兼容性

### 字体渲染
- 使用系统默认字体或指定的跨平台字体
- 确保文本在不同平台上的可读性和一致性

### 颜色管理
- 使用CSS变量定义颜色，确保在不同平台上的一致性
- 考虑不同平台的颜色配置和主题设置

## 12. Electron架构规范

### 进程分离
- **主进程 (Main Process)**：负责后端逻辑、数据库操作(PostgreSql)、原生API调用
- **渲染进程 (Renderer Process)**：仅负责UI展示和用户交互，不包含直接的业务逻辑
- **通信原则**：UI层通过预定义的IPC通道请求数据，避免在渲染进程中执行耗时操作

### IPC通信模式
- **异步非阻塞**：所有数据库和文件操作必须通过`ipcRenderer.invoke`进行异步调用
- **上下文隔离**：使用`contextBridge`暴露安全的API给渲染进程，禁止直接访问Node.js环境
- **错误处理**：后端错误必须通过IPC通道优雅地传递给前端，由前端统一处理显示

### 窗口管理
- **多窗口支持**：支持主窗口、独立播放窗口、日志监控窗口等多窗口协作
- **状态持久化**：应用关闭时保存窗口位置和大小，下次启动时恢复
- **原生集成**：自定义标题栏，集成系统托盘菜单，支持原生系统通知

## 13. MVC交互设计

### 架构分层
- **模型层 (Model)**
  - 定义：数据结构与后端通信的抽象
  - 实现：`RequestComponent` 封装所有 IPC 通信
  - 职责：处理 CRUD 操作，格式化请求数据，标准化错误响应
- **视图层 (View)**
  - 定义：用户界面展示
  - 实现：HTML 模板 + CSS 样式 + 纯 UI 组件 (`CardComponent`, `ModalComponent`)
  - 职责：仅负责展示数据和捕获用户操作，不包含业务逻辑
- **控制器层 (Controller)**
  - 定义：业务逻辑与流程控制
  - 实现：页面级 JS 脚本 (如 `dashboard.js`)
  - 职责：
    1. 监听视图层事件
    2. 执行输入验证
    3. 调用模型层接口
    4. 根据返回数据更新视图状态

### 数据流向
1. **用户操作**：用户点击按钮或输入数据
2. **验证**：控制器验证输入数据的合法性
3. **请求**：控制器调用 `RequestComponent` 发起异步请求
4. **IPC通信**：渲染进程通过 `ipcRenderer.invoke` 发送消息给主进程
5. **后端处理**：主进程调用 Flask API 或直接操作 PostgreSql 数据库
6. **响应**：结果经由 IPC 返回至渲染进程
7. **更新**：控制器接收数据并调用 UI 组件更新界面

## 14. 交付标准

### 文档格式
- **Markdown规范**：提供完整的视觉指南、交互流程图和页面布局规范
- **技术图表**：包含Mermaid架构图，展示MVC层交互、数据流模式和组件关系
- **原型描述**：提供高保真页面原型规范，包含精确的颜色值、间距要求和交互行为

### 实施准备
- **代码就绪规范**：所有设计直接转换为Tailwind CSS类和HTML结构
- **跨平台一致性**：确保设计在Windows、macOS和Linux Electron环境中保持视觉完整性，同时尊重平台特定约定
- **性能优化**：所有设计都考虑了Electron的性能限制，避免不必要的复杂视觉效果

---

本设计系统为智能语音测试系统提供了全面的视觉和交互指导，确保所有UI元素都符合统一的设计标准，同时保持轻量级、现代和专业的外观和感觉。