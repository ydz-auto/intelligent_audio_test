import { ref, computed } from 'vue';

export type TagMode = 'or' | 'and';

export interface TagFilterState {
  selectedTags: string[];
  tagModes: Record<string, TagMode>;
}

export function useTagFilter() {
  const selectedTags = ref<string[]>([]);
  const tagModes = ref<Map<string, TagMode>>(new Map());

  const isTagSelected = (tag: string): boolean => {
    return selectedTags.value.includes(tag);
  };

  const getTagMode = (tag: string): TagMode | null => {
    return tagModes.value.get(tag) || null;
  };

  const handleTagClick = (tagName: string): TagFilterState => {
    const currentMode = tagModes.value.get(tagName);
    let newSelectedTags = [...selectedTags.value];
    let newTagModes = new Map(tagModes.value);

    if (!currentMode) {
      newSelectedTags.push(tagName);
      newTagModes.set(tagName, 'and');
    } else if (currentMode === 'and') {
      newTagModes.set(tagName, 'or');
    } else if (currentMode === 'or') {
      const index = newSelectedTags.indexOf(tagName);
      if (index > -1) {
        newSelectedTags.splice(index, 1);
        newTagModes.delete(tagName);
      }
    }

    selectedTags.value = newSelectedTags;
    tagModes.value = newTagModes;

    return {
      selectedTags: newSelectedTags,
      tagModes: Object.fromEntries(newTagModes)
    };
  };

  const setTagMode = (tagName: string, mode: TagMode): TagFilterState => {
    if (!selectedTags.value.includes(tagName)) {
      return {
        selectedTags: [...selectedTags.value],
        tagModes: Object.fromEntries(tagModes.value)
      };
    }

    const newTagModes = new Map(tagModes.value);
    newTagModes.set(tagName, mode);
    tagModes.value = newTagModes;

    return {
      selectedTags: [...selectedTags.value],
      tagModes: Object.fromEntries(newTagModes)
    };
  };

  const removeTag = (tagName: string): TagFilterState => {
    const newSelectedTags = selectedTags.value.filter(t => t !== tagName);
    const newTagModes = new Map(tagModes.value);
    newTagModes.delete(tagName);

    selectedTags.value = newSelectedTags;
    tagModes.value = newTagModes;

    return {
      selectedTags: newSelectedTags,
      tagModes: Object.fromEntries(newTagModes)
    };
  };

  const addTag = (tagName: string, mode: TagMode = 'and'): TagFilterState => {
    if (selectedTags.value.includes(tagName)) {
      return {
        selectedTags: [...selectedTags.value],
        tagModes: Object.fromEntries(tagModes.value)
      };
    }

    const newSelectedTags = [...selectedTags.value, tagName];
    const newTagModes = new Map(tagModes.value);
    newTagModes.set(tagName, mode);

    selectedTags.value = newSelectedTags;
    tagModes.value = newTagModes;

    return {
      selectedTags: newSelectedTags,
      tagModes: Object.fromEntries(newTagModes)
    };
  };

  const toggleTag = (tagName: string, mode?: TagMode): TagFilterState => {
    const index = selectedTags.value.indexOf(tagName);
    if (index === -1) {
      return addTag(tagName, mode || 'and');
    } else {
      return removeTag(tagName);
    }
  };

  const clearTags = (): TagFilterState => {
    selectedTags.value = [];
    tagModes.value = new Map();

    return {
      selectedTags: [],
      tagModes: {}
    };
  };

  const setTagsFromProps = (tags: string[], modes: Record<string, TagMode>) => {
    selectedTags.value = tags || [];
    tagModes.value = new Map(Object.entries(modes || {}));
  };

  const tagModesObject = computed(() => {
    return Object.fromEntries(tagModes.value);
  });

  return {
    selectedTags,
    tagModes,
    tagModesObject,
    isTagSelected,
    getTagMode,
    handleTagClick,
    setTagMode,
    removeTag,
    addTag,
    toggleTag,
    clearTags,
    setTagsFromProps
  };
}