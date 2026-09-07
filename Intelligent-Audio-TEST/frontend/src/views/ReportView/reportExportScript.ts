/**
 * ReportView —— 导出 HTML 报告的内嵌交互脚本
 * 职责：为静态导出的 report.html 生成自包含 JS（区块折叠、用例卡片展开、
 * 分页、搜索过滤、标签筛选、复制用例 ID），在 file:// 协议下无外部依赖运行
 */

/**
 * 导出 HTML 的交互 JS 脚本
 */
export const getExportJs = (): string => {
  return `(function() {
  'use strict';

  // ========== 1. 区块折叠/展开 ==========
  document.querySelectorAll('.section-header').forEach(function(header) {
    header.addEventListener('click', function() {
      var content = header.nextElementSibling;
      if (!content) return;
      var btn = header.querySelector('.collapse-btn');
      var isCollapsed = content.style.display === 'none';
      content.style.display = isCollapsed ? '' : 'none';
      if (btn) btn.classList.toggle('collapsed', !isCollapsed);
      var icon = btn ? btn.querySelector('i') : null;
      if (icon) {
        if (isCollapsed) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
        else { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      }
    });
  });

  // ========== 2. 用例卡片展开/折叠 ==========
  document.querySelectorAll('.case-header').forEach(function(header) {
    header.addEventListener('click', function(e) {
      if (e.target.closest('.case-id-badge')) return;
      var card = header.closest('.case-card');
      if (!card) return;
      var details = card.querySelector('.case-details');
      if (!details) return;
      var icon = header.querySelector('.expand-icon i');
      if (details.style.display === 'none') {
        details.style.display = '';
        if (icon) { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      } else {
        details.style.display = 'none';
        if (icon) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
      }
    });
  });

  // ========== 3. 维度卡片折叠/展开 ==========
  document.querySelectorAll('.metric-collapse-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var container = btn.closest('.metric-comparison-card') || btn.closest('.metric-container');
      if (!container) return;
      var content = container.querySelector('.metric-container-content');
      if (!content) return;
      var isCollapsed = content.style.display === 'none';
      content.style.display = isCollapsed ? '' : 'none';
      btn.classList.toggle('collapsed', !isCollapsed);
      var icon = btn.querySelector('i');
      if (icon) {
        if (isCollapsed) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
        else { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
      }
    });
  });

  // ========== 4. 显示类型切换 ==========
  document.querySelectorAll('.display-type-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var container = btn.closest('.metric-comparison-card') || btn.closest('.metric-container');
      if (!container) return;
      container.querySelectorAll('.display-type-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var type = btn.getAttribute('data-type') || btn.textContent.trim().toLowerCase();
      var tableEl = container.querySelector('.table-container');
      var chartEl = container.querySelector('.chart-container');
      if (type === 'table') {
        if (tableEl) tableEl.style.display = '';
        if (chartEl) chartEl.style.display = 'none';
      } else {
        if (tableEl) tableEl.style.display = 'none';
        if (chartEl) {
          chartEl.style.display = '';
          var canvas = chartEl.querySelector('canvas');
          if (canvas) {
            chartEl.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8;"><i class="fas fa-chart-bar" style="font-size:48px;"></i><p style="margin-top:12px;">图表在导出的 HTML 中不可用，请切换到表格模式查看数据</p></div>';
          }
        }
      }
    });
  });

  // ========== 5. 用例搜索过滤（与分页联动） ==========
  // allCaseCards 等分页变量在下方第9节声明，此处提前声明以供 applyFilters 使用
  var allCaseCards = document.querySelectorAll('.case-card');
  var totalCases = allCaseCards.length;
  var pageSize = 10;
  var currentPage = 1;
  var totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
  var paginationContainer = document.querySelector('.specific-case-pagination');
  var caseSearchInput = document.querySelector('.filter-input[placeholder*="用例名称"]') || document.querySelector('.filter-input[placeholder*="关键词"]');
  function applyFilters() {
    var query = caseSearchInput ? caseSearchInput.value.toLowerCase().trim() : '';
    var activeCategories = Array.from(document.querySelectorAll('.tag-filter-item.active')).map(function(t) { return t.textContent.trim(); });
    var activeTags = Array.from(document.querySelectorAll('.tag-filter-item-orange.active')).map(function(t) { return t.textContent.trim(); });
    var visibleCount = 0;
    allCaseCards.forEach(function(card) {
      var nameEl = card.querySelector('.case-name');
      var name = nameEl ? nameEl.textContent.toLowerCase() : '';
      var catEl = card.querySelector('.case-category');
      var cat = catEl ? catEl.textContent.trim() : '';
      var tagEls = card.querySelectorAll('.tag');
      var tags = Array.from(tagEls).map(function(t) { return t.textContent.trim(); });
      var nameMatch = !query || name.includes(query);
      var catMatch = activeCategories.length === 0 || activeCategories.includes(cat);
      var tagMatch = activeTags.length === 0 || activeTags.some(function(t) { return tags.includes(t); });
      if (nameMatch && catMatch && tagMatch) {
        card.setAttribute('data-filtered-out', 'false');
        visibleCount++;
      } else {
        card.setAttribute('data-filtered-out', 'true');
      }
    });
    // 重新计算分页（基于可见用例数）
    totalCases = visibleCount;
    totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
    currentPage = 1;
    updateCasePagination();
  }
  if (caseSearchInput) {
    caseSearchInput.addEventListener('input', function() {
      applyFilters();
    });
  }

  // ========== 6. 标签/分组/维度筛选切换 ==========
  document.querySelectorAll('.tag-filter-item, .tag-filter-item-orange, .metric-filter-item').forEach(function(tag) {
    tag.addEventListener('click', function(e) {
      e.stopPropagation();
      tag.classList.toggle('active');
    });
  });

  // ========== 7. 重置/应用筛选（与分页联动） ==========
  document.querySelectorAll('.btn-secondary, .filter-buttons .btn').forEach(function(btn) {
    if (btn.textContent.includes('重置')) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.filter-input').forEach(function(input) { input.value = ''; });
        document.querySelectorAll('.tag-filter-item.active, .tag-filter-item-orange.active, .metric-filter-item.active').forEach(function(t) { t.classList.remove('active'); });
        applyFilters();
      });
    }
    if (btn.textContent.includes('应用') || btn.textContent.includes('筛选')) {
      btn.addEventListener('click', function() {
        applyFilters();
      });
    }
  });

  // ========== 8. 复制用例 ID ==========
  document.querySelectorAll('.case-id-badge').forEach(function(badge) {
    badge.addEventListener('click', async function(e) {
      e.stopPropagation();
      var text = badge.textContent.replace(/.*用例ID:\\s*/, '').trim();
      var ok = await copyToClipboard(text);
      if (ok) {
        badge.style.color = '#16a34a';
        setTimeout(function() { badge.style.color = ''; }, 1500);
      }
    });
  });

  // ========== 9. 用例分页 ==========
  function updateCasePagination() {
    var start = (currentPage - 1) * pageSize;
    var end = start + pageSize;
    allCaseCards.forEach(function(card, idx) {
      // 如果被搜索/筛选隐藏了，不覆盖 display:none
      var isFilteredOut = card.getAttribute('data-filtered-out') === 'true';
      if (isFilteredOut) {
        card.style.display = 'none';
      } else {
        card.style.display = (idx >= start && idx < end) ? '' : 'none';
      }
    });
    // 更新分页信息
    var infoEl = paginationContainer ? paginationContainer.querySelector('.pagination-info') : null;
    if (infoEl) {
      infoEl.textContent = '显示第 ' + currentPage + ' 页，共 ' + totalPages + ' 页，总计 ' + totalCases + ' 条记录';
    }
    // 更新按钮 active 状态
    if (paginationContainer) {
      paginationContainer.querySelectorAll('.pagination-btn').forEach(function(btn) {
        btn.classList.remove('active');
        var text = btn.textContent.trim();
        if (text == String(currentPage)) btn.classList.add('active');
      });
      // 上一页/下一页 disabled 状态
      var prevBtn = paginationContainer.querySelector('.pagination-btn:first-child');
      var nextBtns = paginationContainer.querySelectorAll('.pagination-btn');
      var nextBtn = nextBtns[nextBtns.length - 1];
      if (prevBtn) prevBtn.disabled = (currentPage <= 1);
      if (nextBtn) nextBtn.disabled = (currentPage >= totalPages);
    }
  }

  if (paginationContainer) {
    paginationContainer.querySelectorAll('.pagination-btn').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        var text = btn.textContent.trim();
        if (text === '< 上一页' || text.indexOf('上一页') >= 0) {
          if (currentPage > 1) currentPage--;
        } else if (text === '下一页 >' || text.indexOf('下一页') >= 0) {
          if (currentPage < totalPages) currentPage++;
        } else if (text === '跳转') {
          var input = paginationContainer.querySelector('.pagination-input');
          if (input) {
            var p = parseInt(input.value);
            if (!isNaN(p) && p >= 1 && p <= totalPages) currentPage = p;
          }
        } else {
          var pNum = parseInt(text);
          if (!isNaN(pNum)) currentPage = pNum;
        }
        updateCasePagination();
      });
    });
    // 回车跳转
    var jumpInput = paginationContainer.querySelector('.pagination-input');
    if (jumpInput) {
      jumpInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          var p = parseInt(jumpInput.value);
          if (!isNaN(p) && p >= 1 && p <= totalPages) {
            currentPage = p;
            updateCasePagination();
          }
        }
      });
    }
    // 每页条数切换
    var sizeSelect = paginationContainer.querySelector('.page-size-select select');
    if (sizeSelect) {
      sizeSelect.addEventListener('change', function() {
        pageSize = parseInt(sizeSelect.value);
        totalPages = Math.max(1, Math.ceil(totalCases / pageSize));
        currentPage = 1;
        updateCasePagination();
      });
    }
    // 初始化
    updateCasePagination();
  }

  console.log('报告导出 HTML 交互脚本已加载');
})();`
}
