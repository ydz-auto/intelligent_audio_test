<template>
  <div class="analysis-editor-container">
    <div class="section-header">
      <h3 class="section-title">分析结论</h3>
      <div class="editor-actions">
        <span class="status" :class="`status-${status}`">{{ statusLabel }}</span>
        <button 
          class="btn" 
          :class="isEditing ? 'btn-primary' : 'btn-secondary'"
          @click="toggleEdit"
        >
          <i :class="isEditing ? 'fas fa-save' : 'fas fa-edit'" ></i> 
          {{ isEditing ? '保存' : '编辑' }}
        </button>
        <button 
          class="btn btn-secondary" 
          v-if="isEditing"
          @click="cancelEdit"
        >
          <i class="fas fa-times"></i> 取消
        </button>
      </div>
    </div>
    
    <div class="editor-content">
      <div class="analysis-text-wrapper">
        <div 
          class="analysis-text"
          :contenteditable="isEditing"
          :spellcheck="false"
          @input="handleContentChange"
          v-html="sanitizedContent"
        ></div>
        <div class="editor-placeholder" v-if="!content && !isEditing">
          <i class="fas fa-comment-dots"></i>
          <p>暂无分析结论，点击编辑按钮添加分析内容</p>
        </div>
      </div>
      
      <div class="analysis-tags" v-if="showTags">
        <h4 class="tags-title">结论标签</h4>
        <div class="tags-container">
          <span 
            v-for="tag in availableTags" 
            :key="tag"
            class="tag-item"
            :class="{ 'tag-selected': selectedTags.includes(tag) }"
            @click="toggleTag(tag)"
          >
            {{ tag }}
          </span>
        </div>
        <div class="add-tag-container" v-if="isEditing">
          <input 
            type="text" 
            placeholder="添加新标签..."
            v-model="newTag"
            @keyup.enter="addTag"
          />
          <button class="btn btn-primary" @click="addTag">
            <i class="fas fa-plus"></i> 添加
          </button>
        </div>
      </div>
    </div>
    
    <div class="editor-footer" v-if="isEditing">
      <div class="editor-tools">
        <button class="tool-btn" @click="insertFormat('bold')" title="加粗">
          <i class="fas fa-bold"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('italic')" title="斜体">
          <i class="fas fa-italic"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('underline')" title="下划线">
          <i class="fas fa-underline"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('strikeThrough')" title="删除线">
          <i class="fas fa-strikethrough"></i>
        </button>
        <span class="tool-divider"></span>
        <button class="tool-btn" @click="insertFormat('insertUnorderedList')" title="无序列表">
          <i class="fas fa-list-ul"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('insertOrderedList')" title="有序列表">
          <i class="fas fa-list-ol"></i>
        </button>
        <span class="tool-divider"></span>
        <button class="tool-btn" @click="insertFormat('justifyLeft')" title="左对齐">
          <i class="fas fa-align-left"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('justifyCenter')" title="居中对齐">
          <i class="fas fa-align-center"></i>
        </button>
        <button class="tool-btn" @click="insertFormat('justifyRight')" title="右对齐">
          <i class="fas fa-align-right"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { sanitizeForVHtml } from '../../utils/sanitize'

export default {
  name: 'AnalysisEditorComponent',
  props: {
    content: {
      type: String, default: ''
    },
    status: {
      type: String, default: ReportStatus.DRAFT
    },
    tags: {
      type: Array, default: () => []
    },
    availableTags: {
      type: Array, default: () => ['性能优化', '功能改进', '稳定性问题', '兼容性问题', '建议改进']
    },
    showTags: {
      type: Boolean, default: true
    }
  },
  emits: ['save', 'update:content', 'update:tags'],
  data() {
    return {
      isEditing: false,
      originalContent: '',
      originalTags: [],
      selectedTags: [...this.tags],
      newTag: ''
    };
  },
  computed: {
    statusLabel() {
      const statusMap = {
        [ReportStatus.DRAFT]: '草稿', 'saved': '已保存', [ReportStatus.PUBLISHED]: '已发布', 'updating': '更新中'
      };
      return statusMap[this.status] || this.status;
    },
    sanitizedContent() {
      return sanitizeForVHtml(this.content);
    }
  },
  methods: {
    toggleEdit() {
      if (this.isEditing) {
        this.saveEdit();
      } else {
        this.startEdit();
      }
    },
    startEdit() {
      this.isEditing = true;
      this.originalContent = this.content;
      this.originalTags = [...this.selectedTags];
    },
    saveEdit() {
      this.isEditing = false;
      this.$emit('save', {
        content: this.content,
        tags: this.selectedTags
      });
    },
    cancelEdit() {
      this.isEditing = false;
      this.$emit('update:content', this.originalContent);
      this.selectedTags = [...this.originalTags];
    },
    handleContentChange(event) {
      const content = event.target.innerHTML;
      this.$emit('update:content', content);
    },
    insertFormat(command) {
      document.execCommand(command, false, null);
    },
    toggleTag(tag) {
      if (this.selectedTags.includes(tag)) {
        this.selectedTags = this.selectedTags.filter(t => t !== tag);
      } else {
        this.selectedTags.push(tag);
      }
      this.$emit('update:tags', this.selectedTags);
    },
    addTag() {
      if (this.newTag && !this.availableTags.includes(this.newTag)) {
        this.availableTags.push(this.newTag);
        this.selectedTags.push(this.newTag);
        this.$emit('update:tags', this.selectedTags);
        this.newTag = '';
      }
    }
  }
};
</script>

<style scoped>
.analysis-editor-container {
  background: var(--color-white);
  border-radius: 12px;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-black) 8%, transparent);
  padding: 0;
  margin-bottom: 24px;
  width: 100%;
}

.section-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 12px 0;
  width: 100%;
  box-sizing: border-box;
}

.section-title {
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status {
  padding: 6px 12px;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
}

.status-draft {
  background: var(--warning-light);
  color: var(--warning);
}

.status-saved {
  background: var(--success-light);
  color: var(--success);
}

.status-published {
  background: var(--secondary-light);
  color: var(--secondary);
}

.status-updating {
  background: var(--destructive-light);
  color: var(--destructive);
}

.status-pending {
  background: var(--muted);
  color: var(--color-gray-500);
}

.editor-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0;
}

.analysis-text-wrapper {
  position: relative;
  border: 1px solid var(--color-slate-200);
  border-radius: 8px;
  min-height: 150px;
  background: var(--color-neutral-50);
}

.analysis-text {
  padding: 20px;
  min-height: 150px;
  outline: none;
  line-height: 1.6;
  color: var(--foreground);
  background: var(--color-white);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.analysis-text[contenteditable="true"] {
  background: var(--color-white);
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}

.analysis-text:focus {
  outline: none;
}

.analysis-text h1, .analysis-text h2, .analysis-text h3, .analysis-text h4 {
  margin: 16px 0 8px 0;
  color: var(--foreground);
}

.analysis-text h1 { font-size: 24px; }
.analysis-text h2 { font-size: 20px; }
.analysis-text h3 { font-size: 18px; }
.analysis-text h4 { font-size: 16px; }

.analysis-text p { margin: 8px 0; }
.analysis-text ul, .analysis-text ol { margin: 12px 0; padding-left: 24px; }
.analysis-text li { margin: 4px 0; }

.editor-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: var(--color-gray-400);
  text-align: center;
  padding: 20px;
  pointer-events: none;
}

.editor-placeholder i {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.editor-placeholder p {
  margin: 0;
  font-size: 14px;
}

.editor-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-slate-200);
}

.editor-tools {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.tool-btn {
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tool-btn:hover {
  background: var(--secondary-light);
  border-color: var(--secondary);
  color: var(--secondary);
}

.tool-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}

.analysis-tags {
  margin-top: 24px;
}

.tags-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  margin: 0 0 12px 0;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.tag-item {
  padding: 6px 14px;
  border-radius: 16px;
  background: var(--muted);
  color: var(--color-gray-500);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.tag-item:hover {
  background: var(--secondary-light);
  color: var(--secondary);
  border-color: var(--secondary);
}

.tag-selected {
  background: var(--secondary);
  color: white;
}

.add-tag-container {
  display: flex;
  gap: 8px;
  align-items: center;
}

.add-tag-container input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  max-width: 200px;
}

.add-tag-container input:focus {
  outline: none;
  border-color: var(--secondary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--secondary) 10%, transparent);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  font-family: inherit;
}

.btn-primary {
  background: linear-gradient(90deg, var(--primary), var(--secondary));
  color: white;
}

.btn-primary:hover {
  opacity: 0.9;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--color-black) 15%, transparent);
}

.btn-secondary {
  background: white;
  color: var(--color-gray-500);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--muted);
  border-color: var(--secondary);
}
</style>