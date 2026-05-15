import { io, Socket } from 'socket.io-client';
import { API_CONFIG } from './config';

export interface SocketHandler {
  callback: (data: any) => void;
  originalCallback: (data: any) => void;
  namespace: string;
}

class SocketService {
  private sockets: Record<string, Socket> = {};
  public isConnected: boolean = false;
  private eventHandlers: Record<string, SocketHandler[]> = {};
  private logLevel: 'debug' | 'info' | 'warn' | 'error' = 'debug';

  constructor() {}

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, data: any = null) {
    const levels = ['debug', 'info', 'warn', 'error'] as const;
    if (levels.indexOf(level) >= levels.indexOf(this.logLevel)) {
      const timestamp = new Date().toLocaleTimeString();
      const logMessage = `[${timestamp}] [${level.toUpperCase()}] [SocketService] ${message}`;
      
      if (data) {
        console[level](logMessage, data);
      } else {
        console[level](logMessage);
      }
    }
  }

  public connect(): Socket {
    this.log('debug', '尝试连接到Socket服务器...');
    if (!this.sockets['/']) {
      this.log('debug', '创建默认命名空间Socket连接');
      this.sockets['/'] = io(API_CONFIG.wsBaseUrl, {
        transports: ['polling', 'websocket'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20000,
        autoConnect: true
      });

      this.sockets['/'].on('connect', () => {
        this.log('info', 'Socket已连接到默认命名空间');
        this.isConnected = true;
      });

      this.sockets['/'].on('disconnect', () => {
        this.log('info', 'Socket与默认命名空间断开连接');
        this.isConnected = false;
      });

      this.sockets['/'].on('connect_error', (error) => {
        this.log('error', 'Socket连接错误', error);
        this.isConnected = false;
      });

      this.sockets['/'].on('reconnect_attempt', (attemptNumber) => {
        this.log('info', `Socket重连尝试 #${attemptNumber}`);
      });

      this.sockets['/'].on('reconnect', (attemptNumber) => {
        this.log('info', `Socket重连成功，尝试次数: ${attemptNumber}`);
        this.isConnected = true;
      });

      this.sockets['/'].on('reconnect_failed', () => {
        this.log('error', 'Socket重连失败');
        this.isConnected = false;
      });
    }

    return this.sockets['/'];
  }

  public disconnect() {
    this.log('info', '断开所有Socket连接');
    Object.values(this.sockets).forEach(socket => {
      socket.disconnect();
    });
    this.sockets = {};
    this.isConnected = false;
    this.eventHandlers = {};
  }

  public getNamespaceSocket(namespace: string = '/'): Socket {
    if (namespace === '/') {
      if (!this.sockets['/']) {
        this.connect();
      }
      return this.sockets['/'];
    }
    
    if (!this.sockets[namespace]) {
      this.log('debug', `创建命名空间 ${namespace} 的Socket连接`);
      this.sockets[namespace] = io(`${API_CONFIG.wsBaseUrl}${namespace}`, {
        transports: ['polling', 'websocket'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20000,
        autoConnect: true
      });
      
      this.sockets[namespace].on('connect', () => {
        this.log('info', `Socket已连接到命名空间: ${namespace}`);
        this.isConnected = true;
      });
      
      this.sockets[namespace].on('disconnect', () => {
        this.log('info', `Socket与命名空间 ${namespace} 断开连接`);
        const allDisconnected = Object.values(this.sockets).every(s => !s.connected);
        if (allDisconnected) {
          this.isConnected = false;
        }
      });
      
      this.sockets[namespace].on('connect_error', (error) => {
        this.log('error', `命名空间 ${namespace} Socket连接错误`, error);
      });
    }
    
    return this.sockets[namespace];
  }

  public on(event: string, callback: (data: any) => void, namespace: string = '/'): () => void {
    this.log('debug', `监听事件: ${event}，命名空间: ${namespace}`);
    const socket = this.getNamespaceSocket(namespace);

    const wrappedCallback = (data: any) => {
      this.log('debug', `收到事件: ${event}，命名空间: ${namespace}`, data);
      callback(data);
    };

    socket.on(event, wrappedCallback);

    const key = `${namespace}:${event}`;
    if (!this.eventHandlers[key]) {
      this.eventHandlers[key] = [];
    }
    this.eventHandlers[key].push({ callback: wrappedCallback, originalCallback: callback, namespace });

    return () => this.off(event, callback, namespace);
  }

  public off(event: string, callback: (data: any) => void, namespace: string = '/') {
    this.log('debug', `移除事件监听: ${event}，命名空间: ${namespace}`);
    if (!this.sockets[namespace]) return;

    const key = `${namespace}:${event}`;
    if (this.eventHandlers[key]) {
      const handlers = this.eventHandlers[key];
      for (let i = 0; i < handlers.length; i++) {
        if (handlers[i].originalCallback === callback && handlers[i].namespace === namespace) {
          this.sockets[namespace].off(event, handlers[i].callback);
          handlers.splice(i, 1);
          break;
        }
      }
    }
  }

  public offAll() {
    this.log('info', '移除所有事件监听');
    Object.keys(this.eventHandlers).forEach(key => {
      const handlers = this.eventHandlers[key];
      const event = key.split(':')[1];
      handlers.forEach(handler => {
        const { callback, namespace } = handler;
        if (this.sockets[namespace]) {
          this.sockets[namespace].off(event, callback);
        }
      });
    });

    this.eventHandlers = {};
  }

  public emit(event: string, data: any, namespace: string = '/'): boolean {
    this.log('debug', `发送事件: ${event}，命名空间: ${namespace}`, data);
    if (!this.sockets[namespace]) {
      this.log('error', `命名空间 ${namespace} 未连接，无法发送事件: ${event}`);
      return false;
    }

    this.sockets[namespace].emit(event, data);
    return true;
  }
}

const socketService = new SocketService();
export default socketService;
