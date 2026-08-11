import {
  playbackCurrentPage,
  playbackPageSize,
  playbackTotalPages,
  testCurrentPage,
  testPageSize,
  testTotalPages,
  apiCurrentPage,
  apiPageSize,
  apiTotalPages
} from './deviceState';

export const handlePlaybackPageChange = (page: number) => {
  if (page >= 1 && page <= playbackTotalPages.value) {
    playbackCurrentPage.value = page;
  }
};

export const handlePlaybackPageSizeChange = (size: number) => {
  playbackPageSize.value = size;
  playbackCurrentPage.value = 1;
};

export const handlePlaybackPrevPage = () => {
  if (playbackCurrentPage.value > 1) {
    playbackCurrentPage.value--;
  }
};

export const handlePlaybackNextPage = () => {
  if (playbackCurrentPage.value < playbackTotalPages.value) {
    playbackCurrentPage.value++;
  }
};

export const handleTestPageChange = (page: number) => {
  if (page >= 1 && page <= testTotalPages.value) {
    testCurrentPage.value = page;
  }
};

export const handleTestPageSizeChange = (size: number) => {
  testPageSize.value = size;
  testCurrentPage.value = 1;
};

export const handleTestPrevPage = () => {
  if (testCurrentPage.value > 1) {
    testCurrentPage.value--;
  }
};

export const handleTestNextPage = () => {
  if (testCurrentPage.value < testTotalPages.value) {
    testCurrentPage.value++;
  }
};

export const handleAPIPageChange = (page: number) => {
  if (page >= 1 && page <= apiTotalPages.value) {
    apiCurrentPage.value = page;
  }
};

export const handleAPIPageSizeChange = (size: number) => {
  apiPageSize.value = size;
  apiCurrentPage.value = 1;
};

export const handleAPIPrevPage = () => {
  if (apiCurrentPage.value > 1) {
    apiCurrentPage.value--;
  }
};

export const handleAPINextPage = () => {
  if (apiCurrentPage.value < apiTotalPages.value) {
    apiCurrentPage.value++;
  }
};
