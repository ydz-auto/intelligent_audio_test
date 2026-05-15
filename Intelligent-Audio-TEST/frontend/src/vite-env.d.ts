/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface Window {
  electronAPI: {
    apiRequest: (args: {
      method: string;
      url: string;
      data?: any;
      params?: any;
      headers?: Record<string, string>;
      isMultipart?: boolean;
      options?: {
        responseType?: 'json' | 'blob' | 'arraybuffer' | 'text';
        timeout?: number;
      };
    }) => Promise<any>;
    onTaskProgress?: (callback: (event: any, data: any) => void) => void;
    onLogMessage?: (callback: (event: any, data: any) => void) => void;
    [key: string]: any;
  };
  webUtils?: {
    getPathForFile: (file: File) => string;
  };
}
