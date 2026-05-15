import { contextBridge, ipcRenderer, webUtils } from 'electron';
import { APIRequestOptions } from './src/shared/types';

contextBridge.exposeInMainWorld('webUtils', {
  getPathForFile: (file: File) => webUtils.getPathForFile(file)
});

contextBridge.exposeInMainWorld('electronAPI', {
  apiRequest: (options: APIRequestOptions) => ipcRenderer.invoke('api-request', options),
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  selectFile: (options?: { filters?: any[] }) => ipcRenderer.invoke('select-file', options),
  showOpenDialog: (options: any) => ipcRenderer.invoke('show-open-dialog', options),
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  on: (channel: string, func: (...args: any[]) => void) => {
    ipcRenderer.on(channel, (_event, ...args) => func(...args));
  },
  removeAllListeners: (channel: string) => {
    ipcRenderer.removeAllListeners(channel);
  }
});
