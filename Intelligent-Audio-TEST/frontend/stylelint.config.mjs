/**
 * Stylelint 配置（INT-767 CSS-0 基座）
 * 规则照 INT-757 方案 §2.4；存量告警先 warning，随 CSS-1~3 逐域降 0。
 * 关键守护：custom-property-no-missing-var-function —— 抓值里裸写自定义属性（未包 var()）。
 * 注：方案稿的 custom-property-no-missing-var（旧名）在 stylelint 16+ 已更名为
 *     custom-property-no-missing-var-function 且语义变为「裸自定义属性」检查；
 *     「用了没定义」变量改用交付脚本 grep 校验（验收标准 3 双保险）。
 * 适配说明（相对方案稿）：
 *   - custom-property-pattern 按 stylelint 17 语义匹配"裸名"（不含 -- 前缀）
 *   - import-notation / order / vendor-prefix 关停：Vite+Tailwind 管道用裸字符串 @import，
 *     存量文件属性顺序与厂商前缀属 CSS-1~3 逐域收敛范围
 */
export default {
  extends: ['stylelint-config-standard', 'stylelint-config-recess-order'],
  overrides: [
    {
      // 令牌 / 预设 / 兼容别名文件豁免：hex/rgba 是设计值本体，颜色写法（长短 hex、现代/别名
      // rgb 记法、alpha 百分比）保持原 Vue 现值零漂移，不做规范化
      files: ['src/assets/styles/theme*.css', 'src/assets/styles/variables.css'],
      rules: {
        'color-no-hex': null,
        'color-hex-length': null,
        'color-function-alias-notation': null,
        'color-function-notation': null,
        'alpha-value-notation': null,
        'declaration-no-important': null,
      },
    },
  ],
  rules: {
    // 业务 CSS 禁 hex（令牌文件豁免）
    'color-no-hex': [true, { severity: 'warning' }],
    // 禁 !important（令牌文件豁免）
    'declaration-no-important': [true, { severity: 'warning' }],
    // 变量命名（stylelint 17：匹配不含 -- 前缀的裸名）
    'custom-property-pattern': '^[a-z][a-zA-Z0-9-]*$',
    // 值里裸自定义属性（未包 var()）即报
    'custom-property-no-missing-var-function': true,
    // 禁跨文件重复类（本卡范围内公共组件收归后 0 新增）
    'no-duplicate-selectors': [true, { severity: 'warning' }],
    // 存量选择器太深，先关
    'no-descending-specificity': null,
    'selector-max-compound-selectors': [5, { severity: 'warning' }],
    // ── Vite/Tailwind 管道与存量适配 ──
    // @import 'xxx.css' 裸字符串是 Vite CSS 管道标准写法（newAPI 亦同）
    'import-notation': null,
    // 存量文件属性顺序不统一，随域收敛时按 recess-order 排
    'order/properties-order': null,
    // 存量需厂商前缀（-webkit-appearance 等），随域收敛时视浏览器支持清掉
    'property-no-vendor-prefix': null,
    // Tailwind 4 at-rule（@source/@theme/@custom-variant/@utility/@apply 等）
    'at-rule-no-unknown': [true, {
      ignoreAtRules: ['source', 'custom-variant', 'theme', 'utility', 'apply', 'reference', 'config', 'variant'],
    }],
    // 字体栈品牌名大小写（BlinkMacSystemFont/Roboto 等）
    'value-keyword-case': null,
    // 令牌分组间的空行是排版惯例，不禁
    'custom-property-empty-line-before': null,
    // 存量文件注释紧贴规则（/* 6. ... */ 等），随域收敛时规范化
    'comment-empty-line-before': null,
    // Tailwind @utility 内 & 作用域（stylelint 17 规则不识 @utility）
    'nesting-selector-no-missing-scoping-root': null,
  },
}
