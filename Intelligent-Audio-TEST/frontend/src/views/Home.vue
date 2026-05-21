<template>
  <div class="home-page">
    <section class="hero-section">
      <div class="hero-content">
        <div class="hero-icon">
          <i class="fas fa-microphone-alt"></i>
        </div>
        <h1 class="hero-title">智能语音测试系统</h1>
        <p class="hero-subtitle">Intelligent Voice Testing System</p>
        <p class="hero-description">
          专业的端到端测试与API测试解决方案，支持多维度语音评估，
          提供完整的测试任务管理、报告分析功能。
        </p>

      </div>
    </section>

    <section class="quick-stats">
           
      <router-link to="/TestCaseManager" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-clipboard-list"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.testCasesTotal }}</h3>
          <p class="stat-label">测试用例</p>
          <p class="stat-sub">{{ animatedStats.testCasesGroups }} 个分组</p>
        </div>
      </router-link>
       <router-link to="/Tasks" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-tasks"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.tasksTotal }}</h3>
          <p class="stat-label">测试任务</p>
          <p class="stat-sub">{{ animatedStats.tasksCompleted }} 已完成</p>
        </div>
      </router-link>
            <router-link to="/Evaluation" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-star"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.dimensionsTotal }}</h3>
          <p class="stat-label">评估维度</p>
          <p class="stat-sub">{{ animatedStats.dimensionsEndpoints }} 个端点</p>
        </div>
      </router-link>
            <router-link to="/AudioImport" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-music"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.audioFilesTotal }}</h3>
          <p class="stat-label">音频文件</p>
          <p class="stat-sub">{{ animatedStats.audioFilesDry }} 个干音</p>
        </div>
      </router-link>

      <router-link to="/Device" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-headphones"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.devicesOnline }}</h3>
          <p class="stat-label">在线设备</p>
          <p class="stat-sub">{{ animatedStats.devicesOffline }} 离线</p>
        </div>
      </router-link>

      <router-link to="/APITest" class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-server"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ animatedStats.apisTotal }}</h3>
          <p class="stat-label">API服务</p>
          <p class="stat-sub">{{ animatedStats.apisOnline }} 在线</p>
        </div>
      </router-link>

    </section>

    <section class="workflow-section">
                  <h2 class="section-title">开始测试</h2>
      <p class="section-subtitle">选择测试类型开始语音测试</p>
  <div class="progress-nav">
        <div class="progress-step active">
          <div class="progress-step-number">1</div>
          <div class="progress-step-content">
            <div class="progress-step-label">选择算法</div>
            <div class="progress-step-desc">配置测试算法参数</div>
          </div>
        </div>
        <div class="progress-line"></div>
        <div class="progress-step active">
          <div class="progress-step-number active">2</div>
          <div class="progress-step-content">
            <div class="progress-step-label">选择用例</div>
            <div class="progress-step-desc">创建或选择测试用例</div>
          </div>
        </div>
        <div class="progress-line"></div>
        <div class="progress-step active">
          <div class="progress-step-number">3</div>
          <div class="progress-step-content">
            <div class="progress-step-label">选择设备</div>
            <div class="progress-step-desc">配置测试设备参数</div>
          </div>
        </div>
        <div class="progress-line"></div>
        <div class="progress-step active">
          <div class="progress-step-number active">4</div>
          <div class="progress-step-content">
            <div class="progress-step-label">执行测试</div>
            <div class="progress-step-desc">运行语音测试流程</div>
          </div>
        </div>
        <div class="progress-line"></div>
        <div class="progress-step active">
          <div class="progress-step-number">5</div>
          <div class="progress-step-content">
            <div class="progress-step-label">查看结果</div>
            <div class="progress-step-desc">分析测试评估报告</div>
          </div>
        </div>
      </div>
      <div class="test-type-cards">
        <router-link to="/E2ETest" class="test-type-card e2e">
          <div class="test-type-icon">
            <i class="fas fa-project-diagram"></i>
          </div>
          <div class="test-type-content">
            <h3 class="test-type-title">端到端测试</h3>
            <p class="test-type-description">
              在真实设备上执行端到端语音测试，支持多设备并行测试，
              实时监控测试进度和结果。
            </p>
            <ul class="test-type-list">
              <li>多设备并行测试</li>
              <li>实时进度监控</li>
              <li>自动化测试流程</li>
            </ul>
          </div>
          <div class="test-type-action-btn">
            <span>开始测试</span>
            <i class="fas fa-arrow-right"></i>
          </div>
        </router-link>

        <router-link to="/APITest" class="test-type-card api">
          <div class="test-type-icon">
            <i class="fas fa-exchange-alt"></i>
          </div>
          <div class="test-type-content">
            <h3 class="test-type-title">API测试</h3>
            <p class="test-type-description">
              测试语音识别和翻译API等的性能和准确率，
              支持批量测试和结果对比分析。
            </p>
            <ul class="test-type-list">
              <li>API性能测试</li>
              <li>批量测试执行</li>
              <li>结果对比分析</li>
            </ul>
          </div>
          <div class="test-type-action-btn">
            <span>开始测试</span>
            <i class="fas fa-arrow-right"></i>
          </div>
        </router-link>
      </div>

    
    </section>

 

    <section class="detail-section">
      <h2 class="section-title">端到端测试系统</h2>
      <p class="section-subtitle">在真实设备上执行完整的语音测试流程，模拟真实用户使用场景</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large">
            <i class="fas fa-mobile-alt"></i>
          </div>
          <h3 class="detail-title">真实设备测试</h3>
          <p class="detail-description">
            在真实Android/鸿蒙设备上执行端到端语音测试，模拟真实用户使用场景。
            支持多设备并行测试，同时在多台设备上运行相同的测试用例，
            快速对比不同设备的表现差异。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-layer-group"></i>
              <span>多设备并行测试</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-tachometer-alt"></i>
              <span>实时进度监控</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-history"></i>
              <span>完整执行记录</span>
            </div>
          </div>
        </div>

        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon">
              <i class="fas fa-list-ol"></i>
            </div>
            <h4>五步测试流程</h4>
            <p>选择算法 → 选择用例 → 选择设备 → 执行测试 → 查看报告</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon">
              <i class="fas fa-tags"></i>
            </div>
            <h4>用例分类管理</h4>
            <p>唤醒词、命令识别、语音识别、多轮对话测试</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon">
              <i class="fas fa-chart-bar"></i>
            </div>
            <h4>可视化报告</h4>
            <p>准确率对比、正态分布、趋势分析图表</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon">
              <i class="fas fa-exclamation-triangle"></i>
            </div>
            <h4>异常处理</h4>
            <p>支持重试和跳过失败用例</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/E2ETest" class="detail-cta-btn cta-e2e">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        
        <a href="https://github.com" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section alt-bg">
      <h2 class="section-title">API测试系统</h2>
      <p class="section-subtitle">测试语音识别和翻译API的性能与准确率，支持批量测试和结果对比</p>
      <div class="detail-cards reverse">
        <div class="detail-main-card">
          <div class="detail-icon-large api">
            <i class="fas fa-exchange-alt"></i>
          </div>
          <h3 class="detail-title">API性能测试</h3>
          <p class="detail-description">
            测试第三方语音识别和翻译API的性能和准确率。
            支持批量测试执行，自动记录响应时间、并发数和成功率。
            提供详细的结果对比分析，帮助优化API使用策略。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-bolt"></i>
              <span>性能基准测试</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-balance-scale"></i>
              <span>结果对比分析</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-heartbeat"></i>
              <span>健康状态监控</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon api">
              <i class="fas fa-server"></i>
            </div>
            <h4>多API支持</h4>
            <p>支持对接多个语音识别和翻译服务</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon api">
              <i class="fas fa-users"></i>
            </div>
            <h4>并发控制</h4>
            <p>自定义并发数和请求间隔</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon api">
              <i class="fas fa-stopwatch"></i>
            </div>
            <h4>响应时间分析</h4>
            <p>实时统计平均响应时间和超时率</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon api">
              <i class="fas fa-file-export"></i>
            </div>
            <h4>报告导出</h4>
            <p>支持CSV和PDF格式导出</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/APITest" class="detail-cta-btn cta-api">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section">
      <h2 class="section-title">音频导入功能</h2>
      <p class="section-subtitle">多种音频导入方式，支持批量操作和自动生成测试用例</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large audio">
            <i class="fas fa-music"></i>
          </div>
          <h3 class="detail-title">灵活音频管理</h3>
          <p class="detail-description">
            支持多种音频导入方式，包括本地上传、文件夹批量导入。
            导入时可选择自动生成测试用例，支持设置测试类型、播放设备和声压级。
            提供音频预览、格式转换和元数据编辑功能。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-cloud-upload-alt"></i>
              <span>多途径导入</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-magic"></i>
              <span>自动生成用例</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-sliders-h"></i>
              <span>声压级配置</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon audio">
              <i class="fas fa-file-audio"></i>
            </div>
            <h4>多格式支持</h4>
            <p>MP3、WAV、FLAC、AAC等常见格式</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon audio">
              <i class="fas fa-filter"></i>
            </div>
            <h4>智能筛选</h4>
            <p>按格式、采样率、标签、时长筛选</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon audio">
              <i class="fas fa-wave-square"></i>
            </div>
            <h4>格式转换</h4>
            <p>支持采样率和声道转换</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon audio">
              <i class="fas fa-info-circle"></i>
            </div>
            <h4>元数据管理</h4>
            <p>编辑ASR文本、标签、分类信息</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/AudioImport" class="detail-cta-btn cta-audio">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section alt-bg">
      <h2 class="section-title">用例管理</h2>
      <p class="section-subtitle">统一管理端到端测试用例和API测试用例，支持分类、标签和批量操作</p>
      <div class="detail-cards reverse">
        <div class="detail-main-card">
          <div class="detail-icon-large cases">
            <i class="fas fa-tasks"></i>
          </div>
          <h3 class="detail-title">用例集中管理</h3>
          <p class="detail-description">
            统一管理端到端测试用例和API测试用例，支持按测试类型分组管理。
            提供用例标签系统，方便分类和筛选。支持批量导入导出、复制和移动操作，
            提高用例管理效率。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-folder"></i>
              <span>分类管理</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-tags"></i>
              <span>标签系统</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-copy"></i>
              <span>批量操作</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon cases">
              <i class="fas fa-list"></i>
            </div>
            <h4>用例类型</h4>
            <p>唤醒词、命令识别、语音识别、多轮对话</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon cases">
              <i class="fas fa-file-import"></i>
            </div>
            <h4>批量导入</h4>
            <p>支持从文件和文件夹批量导入</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon cases">
              <i class="fas fa-file-export"></i>
            </div>
            <h4>导出功能</h4>
            <p>支持导出为Excel格式</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon cases">
              <i class="fas fa-search"></i>
            </div>
            <h4>快速搜索</h4>
            <p>支持关键词和标签筛选</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/TestCaseManager" class="detail-cta-btn cta-cases">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section">
      <h2 class="section-title">任务管理</h2>
      <p class="section-subtitle">查看和管理测试任务执行记录，支持历史查询、结果回溯和任务合并</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large tasks">
            <i class="fas fa-history"></i>
          </div>
          <h3 class="detail-title">任务历史追踪</h3>
          <p class="detail-description">
            查看和管理所有测试任务的执行记录，支持按时间、状态、类型筛选。
            提供任务详情查看，包括执行进度、结果统计和关联信息。
            支持历史任务结果回溯、报告重新生成，以及多任务合并对比分析。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-filter"></i>
              <span>多维筛选</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-chart-pie"></i>
              <span>结果统计</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-object-group"></i>
              <span>任务合并</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon tasks">
              <i class="fas fa-clock"></i>
            </div>
            <h4>时间筛选</h4>
            <p>按日期范围快速筛选任务</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon tasks">
              <i class="fas fa-check-circle"></i>
            </div>
            <h4>状态筛选</h4>
            <p>全部、成功、失败、进行中</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon tasks">
              <i class="fas fa-copy"></i>
            </div>
            <h4>任务合并</h4>
            <p>多任务结果合并与对比分析</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon tasks">
              <i class="fas fa-redo"></i>
            </div>
            <h4>结果回溯</h4>
            <p>查看历史报告和详细结果</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/Tasks" class="detail-cta-btn cta-tasks">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>
  <section class="detail-section">
      <h2 class="section-title">报告管理</h2>
      <p class="section-subtitle">多维度测试报告查看、对比分析和导出功能</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large reports">
            <i class="fas fa-chart-pie"></i>
          </div>
          <h3 class="detail-title">全方位报告分析</h3>
          <p class="detail-description">
            提供完整的测试报告管理功能，支持多维度数据查看和对比分析。
            可按任务、时间、类型筛选历史报告，支持单任务详细报告和跨任务对比报告。
            报告数据支持多种图表展示和格式导出。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-file-alt"></i>
              <span>详细报告查看</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-balance-scale"></i>
              <span>跨任务对比</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-file-export"></i>
              <span>多格式导出</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon reports">
              <i class="fas fa-history"></i>
            </div>
            <h4>历史报告</h4>
            <p>按时间、任务类型筛选历史测试报告</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon reports">
              <i class="fas fa-chart-bar"></i>
            </div>
            <h4>数据可视化</h4>
            <p>准确率曲线、正态分布、对比图表</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon reports">
              <i class="fas fa-columns"></i>
            </div>
            <h4>对比分析</h4>
            <p>多任务、多维度结果对比展示</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/history-reports" class="detail-cta-btn cta-reports">
          <span>查看报告</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section alt-bg">
      <h2 class="section-title">评估系统</h2>
      <p class="section-subtitle">多维度语音评估，支持自定义评估规则和API集成</p>
      <div class="detail-cards reverse">
        <div class="detail-main-card">
          <div class="detail-icon-large evaluation">
            <i class="fas fa-star"></i>
          </div>
          <h3 class="detail-title">智能评估引擎</h3>
          <p class="detail-description">
            提供多维度语音质量评估，包括准确率、召回率、F1分数等核心指标。
            支持自定义评估规则和第三方评估API集成，满足不同场景的评估需求。
            实时计算评估分数，快速定位语音识别问题。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-calculator"></i>
              <span>多指标计算</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-cogs"></i>
              <span>自定义规则</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-plug"></i>
              <span>API扩展</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon evaluation">
              <i class="fas fa-check-circle"></i>
            </div>
            <h4>ASR准确率</h4>
            <p>字错率、词错率、句错率等评估</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon evaluation">
              <i class="fas fa-language"></i>
            </div>
            <h4>翻译质量</h4>
            <p>COMET 等评分支持</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon evaluation">
              <i class="fas fa-balance-scale"></i>
            </div>
            <h4>准确率与召回</h4>
            <p>Precision、Recall、F1 分数</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon evaluation">
              <i class="fas fa-wind"></i>
            </div>
            <h4>流畅度评估</h4>
            <p>气泡率、停顿率分析</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/Evaluation" class="detail-cta-btn cta-evaluation">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section">
      <h2 class="section-title">设备管理</h2>
      <p class="section-subtitle">统一管理测试设备和播放设备，支持状态监控和分组配置</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large device">
            <i class="fas fa-mobile-alt"></i>
          </div>
          <h3 class="detail-title">设备集中管理</h3>
          <p class="detail-description">
            支持管理Android/鸿蒙真机设备和播放设备。
            实时监控设备在线状态，自动检测设备连接情况。
            支持设备分组管理，方便批量选择和测试执行。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-wifi"></i>
              <span>状态监控</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-layer-group"></i>
              <span>设备分组</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-headphones"></i>
              <span>播放配置</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon device">
              <i class="fab fa-android"></i>
            </div>
            <h4>Android设备</h4>
            <p>ADB连接，自动识别设备信息</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon device">
              <i class="fab fa-apple"></i>
            </div>
            <h4>鸿蒙设备</h4>
            <p>HDC连接，自动识别设备信息</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon device">
              <i class="fas fa-volume-up"></i>
            </div>
            <h4>播放设备</h4>
            <p>声卡通道选择，采样率配置</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon device">
              <i class="fas fa-info-circle"></i>
            </div>
            <h4>设备信息</h4>
            <p>系统版本、APP版本自动获取</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/Device" class="detail-cta-btn cta-device">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section alt-bg">
      <h2 class="section-title">声压级映射</h2>
      <p class="section-subtitle">精确配置音频增益与声压级关系，确保测试环境一致性</p>
      <div class="detail-cards reverse">
        <div class="detail-main-card">
          <div class="detail-icon-large spl">
            <i class="fas fa-sliders-h"></i>
          </div>
          <h3 class="detail-title">声压级校准</h3>
          <p class="detail-description">
            配置音频文件的数字增益与实际声压级的对应关系。
            支持多个声压级节点的线性插值，确保不同音量下的测试准确性。
            可导入校准数据，实现自动化声压级管理。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-chart-line"></i>
              <span>增益曲线配置</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-database"></i>
              <span>校准数据导入</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-broadcast-tower"></i>
              <span>实时声压计算</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon spl">
              <i class="fas fa-volume-up"></i>
            </div>
            <h4>增益配置</h4>
            <p>数字增益到声压的精确映射</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon spl">
              <i class="fas fa-ruler-combined"></i>
            </div>
            <h4>多节点校准</h4>
            <p>支持多个声压级节点插值</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon spl">
              <i class="fas fa-file-import"></i>
            </div>
            <h4>数据导入</h4>
            <p>支持校准数据批量导入</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon spl">
              <i class="fas fa-calculator"></i>
            </div>
            <h4>精度控制</h4>
            <p>小数位数和容差设置</p>
          </div>
        </div>
      </div>
      <div class="detail-cta-section">
        <router-link to="/SPLMapping" class="detail-cta-btn cta-spl">
          <span>立即体验</span>
          <i class="fas fa-arrow-right"></i>
        </router-link>
        <a href="#" target="_blank" class="detail-help-link-inline">
          <i class="fas fa-book"></i>
          <span>使用文档</span>
        </a>
      </div>
    </section>

    <section class="detail-section">
      <h2 class="section-title">并发与异步</h2>
      <p class="section-subtitle">高效的任务调度机制，支持多任务并行处理</p>
      <div class="detail-cards">
        <div class="detail-main-card">
          <div class="detail-icon-large async">
            <i class="fas fa-tachometer-alt"></i>
          </div>
          <h3 class="detail-title">高效任务调度</h3>
          <p class="detail-description">
            基于异步IO的任务调度系统，支持多任务并行执行。
            智能负载均衡自动分配任务，避免资源争用。
            WebSocket实时推送测试进度，任务状态秒级更新。
          </p>
          <div class="detail-features">
            <div class="detail-feature">
              <i class="fas fa-bolt"></i>
              <span>异步执行</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-balance-scale"></i>
              <span>负载均衡</span>
            </div>
            <div class="detail-feature">
              <i class="fas fa-sync"></i>
              <span>实时推送</span>
            </div>
          </div>
        </div>
        <div class="detail-side-cards">
          <div class="detail-side-card">
            <div class="detail-side-icon async">
              <i class="fas fa-rocket"></i>
            </div>
            <h4>快速响应</h4>
            <p>异步IO设计，任务提交即返回</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon async">
              <i class="fas fa-users-cog"></i>
            </div>
            <h4>并发控制</h4>
            <p>可配置的最大并发数和队列长度</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon async">
              <i class="fas fa-server"></i>
            </div>
            <h4>资源隔离</h4>
            <p>单任务资源限制，防止系统过载</p>
          </div>
          <div class="detail-side-card">
            <div class="detail-side-icon async">
              <i class="fas fa-history"></i>
            </div>
            <h4>断点续传</h4>
            <p>支持暂停、恢复和任务重试</p>
          </div>
        </div>
      </div>
    </section>

  
    <section class="features-section">
      <h2 class="section-title">核心功能</h2>
      <p class="section-subtitle">提供完整的语音测试解决方案</p>
      <div class="features-grid">

        <router-link to="/E2ETest" class="feature-card e2e">
          <div class="feature-icon">
            <i class="fas fa-mobile-alt"></i>
          </div>
          <h3 class="feature-title">端到端测试</h3>
          <p class="feature-description">
            在真实设备上执行端到端语音测试，
            支持多设备并行测试和实时进度监控。
          </p>
          <ul class="feature-list">
            <li>多设备并行测试</li>
            <li>五步测试流程</li>
            <li>可视化报告</li>
          </ul>
          <span class="feature-link">开始测试 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/APITest" class="feature-card api">
          <div class="feature-icon">
            <i class="fas fa-exchange-alt"></i>
          </div>
          <h3 class="feature-title">API测试</h3>
          <p class="feature-description">
            测试语音识别和翻译API的性能与准确率，
            支持批量测试和结果对比分析。
          </p>
          <ul class="feature-list">
            <li>API性能测试</li>
            <li>并发控制</li>
            <li>健康状态监控</li>
          </ul>
          <span class="feature-link">开始测试 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/AudioImport" class="feature-card audio">
          <div class="feature-icon">
            <i class="fas fa-music"></i>
          </div>
          <h3 class="feature-title">音频管理</h3>
          <p class="feature-description">
            统一管理测试所需的音频文件，
            支持批量导入、标签分类和音频预览，可导入音频自动生成测试用例。
          </p>
          <ul class="feature-list">
            <li>批量音频导入</li>
            <li>导入生成用例</li>
            <li>音频预览播放</li>
          </ul>
          <span class="feature-link">管理音频 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/TestCaseManager" class="feature-card cases">
          <div class="feature-icon">
            <i class="fas fa-tasks"></i>
          </div>
          <h3 class="feature-title">用例管理</h3>
          <p class="feature-description">
            统一管理端到端测试用例和API测试用例，
            支持用例分类、标签管理和批量操作。
          </p>
          <ul class="feature-list">
            <li>用例分类管理</li>
            <li>标签系统</li>
            <li>批量导入导出</li>
          </ul>
          <span class="feature-link">管理用例 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/tasks" class="feature-card tasks">
          <div class="feature-icon">
            <i class="fas fa-history"></i>
          </div>
          <h3 class="feature-title">任务记录</h3>
          <p class="feature-description">
            查看和管理所有测试任务的执行记录，
            支持历史任务查询和结果回溯。
          </p>
          <ul class="feature-list">
            <li>任务历史记录</li>
            <li>结果查询分析</li>
            <li>报告导出</li>
          </ul>
          <span class="feature-link">查看任务 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/Evaluation" class="feature-card evaluation">
          <div class="feature-icon">
            <i class="fas fa-star"></i>
          </div>
          <h3 class="feature-title">评估维度</h3>
          <p class="feature-description">
            配置和管理语音测试的评估维度，
            支持多种评估指标和自定义评估规则。
          </p>
          <ul class="feature-list">
            <li>多维度评估</li>
            <li>自定义指标</li>
            <li>评估API管理</li>
          </ul>
          <span class="feature-link">配置维度 <i class="fas fa-arrow-right"></i></span>
        </router-link>

        <router-link to="/Device" class="feature-card device">
          <div class="feature-icon">
            <i class="fas fa-mobile-alt"></i>
          </div>
          <h3 class="feature-title">设备管理</h3>
          <p class="feature-description">
            管理测试设备和播放设备，
            支持设备状态监控和设备分组。
          </p>
          <ul class="feature-list">
            <li>设备状态监控</li>
            <li>播放设备配置</li>
            <li>设备分组管理</li>
          </ul>
          <span class="feature-link">管理设备 <i class="fas fa-arrow-right"></i></span>
        </router-link>


        <router-link to="/SPLMapping" class="feature-card spl">
          <div class="feature-icon">
            <i class="fas fa-sliders-h"></i>
          </div>
          <h3 class="feature-title">声压级映射</h3>
          <p class="feature-description">
            配置音频数字增益与实际声压的关系，
            确保测试环境的声压级准确性。
          </p>
          <ul class="feature-list">
            <li>增益配置</li>
            <li>声压校准</li>
            <li>精度控制</li>
          </ul>
          <span class="feature-link">配置映射 <i class="fas fa-arrow-right"></i></span>
        </router-link>
      </div>
    </section>
    <section class="info-section">
      <div class="info-card">
        <div class="info-header">
          <i class="fas fa-info-circle"></i>
          <h3>系统信息</h3>
        </div>
        <div class="info-content">
          <div class="info-row">
            <span class="info-label">系统版本</span>
            <span class="info-value">1.0.0</span>
          </div>
          <div class="info-row">
            <span class="info-label">前端框架</span>
            <span class="info-value">Vue 3 + Electron</span>
          </div>
          <div class="info-row">
            <span class="info-label">后端框架</span>
            <span class="info-value">Flask + PostgreSql</span>
          </div>
          <div class="info-row">
            <span class="info-label">Python版本</span>
            <span class="info-value">3.12</span>
          </div>
        </div>
      </div>
      <div class="info-card">
        <div class="info-header">

          <i class="fas fa-book"></i>
          <h3>使用帮助</h3>

        </div>
        <div class="info-content">
          <p class="help-text">
            首次使用请先配置评估维度和播放设备，然后导入测试音频。
            您可以查看左侧导航栏中的各项功能进行操作。
          </p>

          <div class="help-links">
              <a href="https://github.com" target="_blank" rel="noopener noreferrer" class="help-link">
              <i class="fas fa-external-link-alt"></i>使用帮助文档
              </a>
            <router-link to="/Device" class="help-link">
              <i class="fas fa-headphones"></i>
              配置播放设备
            </router-link>
            <router-link to="/Evaluation" class="help-link">
              <i class="fas fa-star"></i>
              配置评估维度
            </router-link>
            <router-link to="/AudioImport" class="help-link">
              <i class="fas fa-music"></i>
              导入测试音频
            </router-link>

          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { statsApi } from '../utils/api'

const stats = ref({
  testCases: { total: 0, groups: 0 },
  tasks: { total: 0, completed: 0, running: 0, failed: 0 },
  devices: { online: 0, offline: 0, total: 0 },
  audioFiles: { total: 0, dry: 0, noise: 0, prompt: 0, duration: { total: 0, dry: 0, noise: 0, prompt: 0 } },
  apis: { online: 0, offline: 0, total: 0 },
  dimensions: { total: 0, withEndpoints: 0, endpoints: 0 }
})

const animatedStats = ref({
  testCasesTotal: 0,
  testCasesGroups: 0,
  tasksTotal: 0,
  tasksCompleted: 0,
  devicesOnline: 0,
  devicesOffline: 0,
  audioFilesTotal: 0,
  audioFilesDry: 0,
  audioFilesDuration: 0,
  apisOnline: 0,
  apisTotal: 0,
  dimensionsTotal: 0,
  dimensionsEndpoints: 0
})

function animateNumber(targetValue, duration = 1200, onUpdate) {
  const startValue = 0
  const startTime = performance.now()
  
  function update(currentTime) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)
    const easeOutQuart = 1 - Math.pow(1 - progress, 4)
    const currentValue = Math.round(startValue + (targetValue - startValue) * easeOutQuart)
    
    if (onUpdate) {
      onUpdate(currentValue)
    }
    
    if (progress < 1) {
      requestAnimationFrame(update)
    }
  }
  
  requestAnimationFrame(update)
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0秒'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.round(seconds % 60)

  if (hours > 0) {
    return `${hours}小时${minutes}分`
  } else if (minutes > 0) {
    return `${minutes}分${secs}秒`
  } else {
    return `${secs}秒`
  }
}

onMounted(async () => {
  try {
    const statsData = await statsApi.getStatsDetails()
    const getCaseInsensitive = (obj, key) => {
      if (!obj) return undefined
      return obj[key] || obj[key.toLowerCase()] || obj[key.charAt(0).toUpperCase() + key.slice(1).toLowerCase()]
    }
    const newStats = {
      testCases: getCaseInsensitive(statsData, 'testCases') || { total: 0, groups: 0 },
      tasks: statsData.tasks || { total: 0, completed: 0, running: 0, failed: 0 },
      devices: statsData.devices || { online: 0, offline: 0, total: 0 },
      audioFiles: getCaseInsensitive(statsData, 'audioFiles') || { total: 0, dry: 0, noise: 0, prompt: 0, duration: { total: 0, dry: 0, noise: 0, prompt: 0 } },
      apis: statsData.apis || { online: 0, offline: 0, total: 0 },
      dimensions: statsData.dimensions || { total: 0, withendpoints: 0, endpoints: 0 }
    }
    
    stats.value = newStats
    
    animateNumber(newStats.testCases.total, 1200, val => animatedStats.value.testCasesTotal = val)
    animateNumber(newStats.testCases.groups || 0, 1200, val => animatedStats.value.testCasesGroups = val)
    animateNumber(newStats.tasks.total, 1200, val => animatedStats.value.tasksTotal = val)
    animateNumber(newStats.tasks.completed || 0, 1200, val => animatedStats.value.tasksCompleted = val)
    animateNumber(newStats.devices.online, 1200, val => animatedStats.value.devicesOnline = val)
    animateNumber(newStats.devices.offline, 1200, val => animatedStats.value.devicesOffline = val)
    animateNumber(newStats.audioFiles.total, 1200, val => animatedStats.value.audioFilesTotal = val)
    animateNumber(newStats.audioFiles.dry || 0, 1200, val => animatedStats.value.audioFilesDry = val)
    animateNumber(newStats.audioFiles.duration?.total || 0, 1200, val => animatedStats.value.audioFilesDuration = val)
    animateNumber(newStats.apis.online, 1200, val => animatedStats.value.apisOnline = val)
    animateNumber(newStats.apis.total, 1200, val => animatedStats.value.apisTotal = val)
    animateNumber(newStats.dimensions.total || 0, 1200, val => animatedStats.value.dimensionsTotal = val)
    animateNumber(newStats.dimensions.endpoints || 0, 1200, val => animatedStats.value.dimensionsEndpoints = val)
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }
  
  // Initialize scroll animations
  initScrollAnimations()
})

function initScrollAnimations() {
  const observerOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.1
  }
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate')
      } else {
        entry.target.classList.remove('animate')
      }
    })
  }, observerOptions)
  
  // Observe all sections
  const sections = document.querySelectorAll('.hero-section, .quick-stats, .workflow-section, .detail-section, .features-section, .info-section')
  sections.forEach(section => {
    section.classList.add('scroll-animate')
    observer.observe(section)
  })
  
  // Also observe individual cards for more granular animations
  const cards = document.querySelectorAll('.feature-card, .detail-main-card, .detail-side-card, .stat-card, .test-type-card')
  cards.forEach(card => {
    card.classList.add('scroll-animate')
    observer.observe(card)
  })
}
</script>

<style scoped>
.home-page {
  min-height: 100%;
  background: white;
  scroll-behavior: smooth;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) white;
  transition: scroll-position 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Custom scrollbar for WebKit browsers */
.home-page::-webkit-scrollbar {
  width: 6px;
}

.home-page::-webkit-scrollbar-track {
  background: white;
  border-radius: 3px;
}

.home-page::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
  transition: background 0.3s ease;
}

.home-page::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* Smooth transitions for all animated elements */
.section-title,
.section-subtitle,
.feature-card,
.detail-main-card,
.detail-side-card,
.stat-card,
.test-type-card {
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Scroll-based animations */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Scroll-triggered animations */
.scroll-animate {
  opacity: 0;
  transform: translateY(30px);
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

.scroll-animate.animate {
  opacity: 1;
  transform: translateY(0);
}

.hero-section {
  position: relative;
  margin: calc(-1 * var(--spacing-xl));
  margin-bottom: 0;
  padding: 100px calc(var(--spacing-xl) + 24px);
  text-align: center;
  background: linear-gradient(180deg, #FFF8F0 0%, #FFFFFF 100%);
  color: var(--text-primary);
  width: calc(100% + 2 * var(--spacing-xl));
  max-width: none;
}

.hero-content {
  position: relative;
  z-index: 2;
  max-width: 700px;
  margin: 0 auto;
}

.hero-icon {
  width: 90px;
  height: 90px;
  margin: 0 auto 28px;
  background: var(--primary-light);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 42px;
  color: var(--primary-color);
}

.hero-title {
  font-size: 42px;
  font-weight: 700;
  margin: 0 0 48px;
  color: var(--text-primary);
}

.hero-subtitle {
  font-size: 16px;
  margin: 0 0 20px;
  opacity: 0.8;
  font-weight: 400;
  color: var(--text-secondary);
  letter-spacing: 2px;
  text-transform: uppercase;
}

.hero-description {
  font-size: 16px;
  line-height: 1.8;
  margin: 0;
  opacity: 0.9;
  color: var(--text-secondary);
}

.quick-stats {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 24px;
  padding: 3rem calc((100% - 61.25rem) / 2);
  background: white;
  width: calc(100% + 2 * var(--spacing-xl));
  box-sizing: border-box;
  margin-left: calc(-1 * var(--spacing-xl));
  margin-right: calc(-1 * var(--spacing-xl));
}

@media (min-width: 2560px) {
  .quick-stats {
    padding: 3rem calc((100% - 80rem) / 2);
  }
}

.quick-stats .stat-card {
  background-color: white;
  border: none;
  border-radius: var(--border-radius-lg);
  box-shadow: none;
  padding: 24px;
  transition: all var(--transition-normal);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  text-decoration: none;
  color: inherit;
}

.quick-stats .stat-card:hover {
  transform: translateY(-4px);
  box-shadow: none;
}

.quick-stats .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  margin-bottom: 12px;
}

.quick-stats .stat-card:nth-child(1) .stat-icon {
  background-color: rgba(22, 119, 255, 0.1);
  color: #1677FF;
}

.quick-stats .stat-card:nth-child(2) .stat-icon {
  background-color: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.quick-stats .stat-card:nth-child(3) .stat-icon {
  background-color: rgba(114, 46, 209, 0.1);
  color: #722ED1;
}

.quick-stats .stat-card:nth-child(4) .stat-icon {
  background-color: rgba(47, 194, 191, 0.1);
  color: #2FC2BF;
}

.quick-stats .stat-card:nth-child(5) .stat-icon {
  background-color: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.quick-stats .stat-number {
  font-size: 32px;
  font-weight: 700;
  margin: 0;
  line-height: 1;
}

.quick-stats .stat-card:nth-child(1) .stat-number {
  color: #1677FF;
}

.quick-stats .stat-card:nth-child(2) .stat-number {
  color: #52C41A;
}

.quick-stats .stat-card:nth-child(3) .stat-number {
  color: #722ED1;
}

.quick-stats .stat-card:nth-child(4) .stat-number {
  color: #2FC2BF;
}

.quick-stats .stat-card:nth-child(5) .stat-number {
  color: #FAAD14;
}

.quick-stats .stat-card:nth-child(6) .stat-icon {
  background-color: rgba(255, 51, 102, 0.1);
  color: #FF3366;
}

.quick-stats .stat-card:nth-child(6) .stat-number {
  color: #FF3366;
}

.quick-stats .stat-label {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.quick-stats .stat-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 4px 0 0 0;
}

.features-section {
  padding: 3rem calc((100% - 61.25rem) / 2);
}

@media (min-width: 2560px) {
  .features-section {
    padding: 3rem calc((100% - 80rem) / 2);
  }
}

.features-section .section-title {
  display: block;
  text-align: center;
}

.features-section .section-subtitle {
  text-align: center;
}

.section-title {
  text-align: center;
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 16px;
  display: block;
}

.section-subtitle {
  text-align: center;
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0 0 48px;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.feature-card {
  position: relative;
  background: white;
  border-radius: 16px;
  padding: 32px;
  text-decoration: none;
  color: inherit;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
  overflow: hidden;
}

.feature-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--primary-gradient);
  transform: scaleX(0);
  transition: transform 0.3s ease;
}

.feature-card:hover {
  transform: translateY(-8px);
  box-shadow: var(--shadow-lg);
}

.feature-card:hover::before {
  transform: scaleX(1);
}

.feature-icon {
  width: 64px;
  height: 64px;
  background: var(--primary-light);
  color: var(--primary-color);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  margin-bottom: 20px;
  transition: all 0.3s ease;
}

.feature-card:hover .feature-icon {
  background: var(--primary-color);
  color: white;
  transform: scale(1.1);
}

.feature-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.feature-description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 16px;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0 0 20px;
}

.feature-list li {
  position: relative;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.feature-list li::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: var(--success-color);
  font-weight: bold;
}

.feature-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
  font-weight: 600;
  font-size: 14px;
  transition: gap 0.3s ease;
}

.feature-card:hover .feature-link {
  gap: 12px;
}

.feature-card.e2e .feature-icon { background: rgba(22, 119, 255, 0.1); color: #1677FF; }
.feature-card.e2e:hover .feature-icon { background: #1677FF; color: white; }
.feature-card.e2e::before { background: linear-gradient(135deg, #1677FF 0%, #0958D9 100%); }

.feature-card.api .feature-icon { background: rgba(82, 196, 26, 0.1); color: #52C41A; }
.feature-card.api:hover .feature-icon { background: #52C41A; color: white; }
.feature-card.api::before { background: linear-gradient(135deg, #52C41A 0%, #389E0D 100%); }

.feature-card.cases .feature-icon { background: rgba(255, 106, 0, 0.1); color: var(--primary-color); }
.feature-card.cases:hover .feature-icon { background: var(--primary-color); color: white; }
.feature-card.cases::before { background: var(--primary-gradient); }

.feature-card.tasks .feature-icon { background: rgba(24, 144, 255, 0.1); color: #1890FF; }
.feature-card.tasks:hover .feature-icon { background: #1890FF; color: white; }
.feature-card.tasks::before { background: linear-gradient(135deg, #1890FF 0%, #096DD9 100%); }

.feature-card.evaluation .feature-icon { background: rgba(250, 173, 20, 0.1); color: #FAAD14; }
.feature-card.evaluation:hover .feature-icon { background: #FAAD14; color: white; }
.feature-card.evaluation::before { background: linear-gradient(135deg, #FAAD14 0%, #D48806 100%); }

.feature-card.device .feature-icon { background: rgba(114, 46, 209, 0.1); color: #722ED1; }
.feature-card.device:hover .feature-icon { background: #722ED1; color: white; }
.feature-card.device::before { background: linear-gradient(135deg, #722ED1 0%, #531DAB 100%); }

.feature-card.audio .feature-icon { background: rgba(47, 194, 191, 0.1); color: #2FC2BF; }
.feature-card.audio:hover .feature-icon { background: #2FC2BF; color: white; }
.feature-card.audio::before { background: linear-gradient(135deg, #2FC2BF 0%, #13C2C2 100%); }

.feature-card.spl .feature-icon { background: rgba(245, 34, 45, 0.1); color: #F5222D; }
.feature-card.spl:hover .feature-icon { background: #F5222D; color: white; }
.feature-card.spl::before { background: linear-gradient(135deg, #F5222D 0%, #CF1322 100%); }

.feature-card.reports { display: none; }
.feature-card.merge { display: none; }

.workflow-section {
    padding: 3rem calc((100% - 61.25rem) / 2);
  background: white;
}

@media (min-width: 2560px) {
  .workflow-section {
    padding: 3rem calc((100% - 80rem) / 2);
  }
}

.workflow-section .section-title {
  text-align: center;
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  display: block;
}

.workflow-section .section-subtitle {
  text-align: center;
  font-size: 16px;
  color: var(--text-secondary);
  margin: 0 0 24px;
}

.workflow-section .progress-nav {
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
  padding: 20px 16px;
  margin: 48px;
}

.progress-step-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.progress-step-desc {
  font-size: 14px;
  color: var(--text-secondary);
  transition: all 0.3s ease;
}

.progress-step.active .progress-step-desc {
  color: var(--text-secondary);
}

.test-type-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-top: 48px;
}

.test-type-card {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 28px;
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.test-type-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  transform: scaleX(0);
  transition: transform 0.3s ease;
}

.test-type-card.e2e::before {
  background: linear-gradient(135deg, #1677FF 0%, #0958D9 100%);
}

.test-type-card.api::before {
  background: linear-gradient(135deg, #52C41A 0%, #389E0D 100%);
}

.test-type-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-8px);
}

.test-type-card:hover::before {
  transform: scaleX(1);
}

.test-type-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.test-type-card.e2e .test-type-icon {
  background: rgba(22, 119, 255, 0.1);
  color: #1677FF;
}

.test-type-card.api .test-type-icon {
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.test-type-card.e2e:hover .test-type-icon {
  background: linear-gradient(135deg, #1677FF 0%, #0958D9 100%);
  color: white;
  transform: scale(1.1);
}

.test-type-card.api:hover .test-type-icon {
  background: linear-gradient(135deg, #52C41A 0%, #389E0D 100%);
  color: white;
  transform: scale(1.1);
}

.test-type-content {
  flex: 1;
}

.test-type-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.test-type-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 16px;
  line-height: 1.6;
}

.test-type-list {
  list-style: none;
  padding: 0;
  margin: 0 0 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.test-type-list li {
  font-size: 13px;
  padding: 4px 12px;
  background: var(--background-secondary);
  border-radius: 10px;
  color: var(--text-secondary);
}

.test-type-action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: var(--background-secondary);
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  transition: all 0.3s ease;
}

.test-type-card:hover .test-type-action-btn {
  background: var(--primary-light);
  color: var(--primary-color);
}

.test-type-action-btn i {
  font-size: 12px;
  transition: transform 0.3s ease;
}

.test-type-card:hover .test-type-action-btn i {
  transform: translateX(4px);
}

.info-section {
  display: flex;
  gap: 24px;
    padding: 3rem calc((100% - 61.25rem) / 2) 80px;
}

@media (min-width: 2560px) {
  .info-section {
    padding: 3rem calc((100% - 80rem) / 2) 80px;
  }
}

.detail-section {
    padding: 3rem calc((100% - 61.25rem) / 2);
  background: white;
}

@media (min-width: 2560px) {
  .detail-section {
    padding: 3rem calc((100% - 80rem) / 2);
  }
}

.detail-section.alt-bg .detail-main-card,
.detail-section.alt-bg .detail-side-card {
  background: var(--background-secondary);
  border-color: transparent;
}

.detail-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 40px;
  margin-top: 40px;
}

.detail-cards.reverse {
  direction: rtl;
}

.detail-cards.reverse > * {
  direction: ltr;
}

.detail-main-card {
  display: flex;
  flex-direction: column;
  padding: 40px;
  background: white;
  border-radius: 20px;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
  text-decoration: none;
  color: inherit;
}

.detail-main-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
}

.detail-icon-large {
  width: 80px;
  height: 80px;
  background: rgba(22, 119, 255, 0.1);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  color: #1677FF;
  margin-bottom: 24px;
}

.detail-icon-large.api {
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.detail-icon-large.audio {
  background: rgba(47, 194, 191, 0.1);
  color: #2FC2BF;
}

.detail-icon-large.cases {
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
}

.detail-icon-large.tasks {
  background: rgba(24, 144, 255, 0.1);
  color: #1890FF;
}

.detail-icon-large.evaluation {
  background: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.detail-icon-large.device {
  background: rgba(114, 46, 209, 0.1);
  color: #722ED1;
}

.detail-icon-large.spl {
  background: rgba(245, 34, 45, 0.1);
  color: #F5222D;
}

.detail-icon-large.async {
  background: rgba(19, 194, 194, 0.1);
  color: #13C2C2;
}

.detail-icon-large.reports {
  background: rgba(47, 84, 235, 0.1);
  color: #2F54EB;
}

.detail-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.detail-description {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0 0 24px;
}

.detail-features {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: auto;
}

.detail-feature {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 10px;
  font-size: 14px;
  color: var(--text-primary);
  transition: all 0.3s ease;
}

.detail-feature:hover {
  background: var(--primary-light);
  color: var(--primary-color);
  transform: translateX(4px);
}

.detail-feature i {
  font-size: 16px;
  color: var(--primary-color);
}

.detail-side-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-content: start;
}

.detail-side-card {
  padding: 24px;
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.detail-cta-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0px;
  padding: 20px 0;
  margin-top: 8px;
}

.detail-cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 32px;
  background: transparent;
  border-radius: 24px;
  font-size: 18px;
  font-weight: 500;
  text-decoration: none;
  transition: all 0.3s ease;
}

.detail-cta-btn i {
  font-size: 14px;
  transition: transform 0.3s ease;
}

.detail-cta-btn:hover i {
  transform: translateX(4px);
}

.detail-cta-btn.cta-e2e {
  color: #1677FF;
}

.detail-cta-btn.cta-e2e:hover {
  background: #1677FF;
  color: white;
}

.detail-cta-btn.cta-api {
  color: #52C41A;
}

.detail-cta-btn.cta-api:hover {
  background: #52C41A;
  color: white;
}

.detail-cta-btn.cta-audio {
  color: #2FC2BF;
}

.detail-cta-btn.cta-audio:hover {
  background: #2FC2BF;
  color: white;
}

.detail-cta-btn.cta-cases {
  color: #FF6A00;
}

.detail-cta-btn.cta-cases:hover {
  background: #FF6A00;
  color: white;
}

.detail-cta-btn.cta-tasks {
  color: #1890FF;
}

.detail-cta-btn.cta-tasks:hover {
  background: #1890FF;
  color: white;
}

.detail-cta-btn.cta-evaluation {
  color: #FAAD14;
}

.detail-cta-btn.cta-evaluation:hover {
  background: #FAAD14;
  color: white;
}

.detail-cta-btn.cta-device {
  color: #722ED1;
}

.detail-cta-btn.cta-device:hover {
  background: #722ED1;
  color: white;
}

.detail-cta-btn.cta-spl {
  color: #F5222D;
}

.detail-cta-btn.cta-spl:hover {
  background: #F5222D;
  color: white;
}

.detail-cta-btn.cta-reports {
  color: #2F54EB;
}

.detail-cta-btn.cta-reports:hover {
  background: #2F54EB;
  color: white;
}

.detail-help-link-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  color: var(--text-tertiary);
  font-size: 13px;
  text-decoration: none;
  transition: all 0.3s ease;
}

.detail-help-link-inline:hover {
  color: var(--primary-color);
}

.detail-help-link-inline i {
  font-size: 12px;
}

.detail-help-links {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.detail-help-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--background-secondary);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.3s ease;
}

.detail-help-link:hover {
  background: var(--primary-light);
  color: var(--primary-color);
  transform: translateX(4px);
}

.detail-help-link i {
  font-size: 12px;
}

.detail-side-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.detail-side-icon {
  width: 48px;
  height: 48px;
  background: rgba(22, 119, 255, 0.1);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #1677FF;
  margin-bottom: 16px;
}

.detail-side-icon.api {
  background: rgba(82, 196, 26, 0.1);
  color: #52C41A;
}

.detail-side-icon.audio {
  background: rgba(47, 194, 191, 0.1);
  color: #2FC2BF;
}

.detail-side-icon.cases {
  background: rgba(255, 106, 0, 0.1);
  color: #FF6A00;
}

.detail-side-icon.tasks {
  background: rgba(24, 144, 255, 0.1);
  color: #1890FF;
}

.detail-side-icon.evaluation {
  background: rgba(250, 173, 20, 0.1);
  color: #FAAD14;
}

.detail-side-icon.device {
  background: rgba(114, 46, 209, 0.1);
  color: #722ED1;
}

.detail-side-icon.spl {
  background: rgba(245, 34, 45, 0.1);
  color: #F5222D;
}

.detail-side-icon.async {
  background: rgba(19, 194, 194, 0.1);
  color: #13C2C2;
}

.detail-side-icon.reports {
  background: rgba(47, 84, 235, 0.1);
  color: #2F54EB;
}

.detail-side-card h4 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.detail-side-card p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

@media (max-width: 1024px) {
  .quick-stats {
    grid-template-columns: repeat(3, 1fr);
  }

  .detail-cards {
    grid-template-columns: 1fr;
  }

  .detail-cards.reverse {
    direction: ltr;
  }

  .detail-side-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .quick-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .detail-section {
    padding: 48px 24px;
  }

  .detail-main-card {
    padding: 28px;
  }

  .detail-title {
    font-size: 24px;
  }

  .detail-side-cards {
    grid-template-columns: 1fr;
  }
}

.info-card {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 32px;
  border: 1px solid var(--border-color);
}

.info-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.info-header i {
  font-size: 24px;
  color: var(--primary-color);
}

.info-header h3 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px dashed var(--border-color);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  color: var(--text-secondary);
}

.info-value {
  font-weight: 600;
  color: var(--text-primary);
}

.help-text {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 20px;
}

.help-links {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.help-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 8px;
  color: var(--text-primary);
  text-decoration: none;
  transition: all 0.3s ease;
}

.help-link:hover {
  background: var(--primary-light);
  color: var(--primary-color);
  transform: translateX(4px);
}

.help-link i {
  width: 20px;
  color: var(--primary-color);
}

@media (max-width: 1024px) {
  .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .hero-title {
    font-size: 32px;
  }

  .hero-description {
    font-size: 16px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: center;
  }

  .quick-stats {
    flex-wrap: wrap;
    gap: 16px;
  }

  .stat-item {
    width: calc(50% - 8px);
    justify-content: center;
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .workflow-steps {
    flex-direction: column;
    align-items: center;
    gap: 24px;
  }

  .workflow-connector {
    width: 2px;
    height: 40px;
    margin: 0;
  }

  .info-section {
    flex-direction: column;
  }
}
</style>
