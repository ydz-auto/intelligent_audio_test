import { LOG_CONFIG, type LogLevel } from './config';

const originalConsole = {
  debug: console.debug,
  info: console.info,
  log: console.log,
  warn: console.warn,
  error: console.error
};

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warning: 2,
  error: 3
};

function shouldLog(level: LogLevel): boolean {
  if (!LOG_CONFIG.enabled) return false;
  if (LOG_CONFIG.disableInProduction && import.meta.env.PROD) return false;
  return LOG_LEVELS[level] >= LOG_LEVELS[LOG_CONFIG.level];
}

function formatMessage(level: string, message: string): string {
  const timestamp = LOG_CONFIG.showTimestamp ? `[${new Date().toISOString()}] ` : '';
  return `${timestamp}[${level.padEnd(5)}] ${message}`;
}

function createProxy(method: 'debug' | 'info' | 'log' | 'warn' | 'error', level: LogLevel) {
  return function (...args: unknown[]) {
    if (shouldLog(level)) {
      if (!Array.isArray(args) || args.length === 0) {
        originalConsole[method].apply(console, args);
        return;
      }
      const message = typeof args[0] === 'string' ? args[0] : '';
      const formatted = message ? [formatMessage(level.toUpperCase(), message), ...args.slice(1)] : args;
      originalConsole[method].apply(console, formatted);
    }
  };
}

console.debug = createProxy('debug', 'debug');
console.info = createProxy('info', 'info');
console.log = createProxy('log', 'debug');
console.warn = createProxy('warn', 'warning');
console.error = createProxy('error', 'error');

export const logger = {
  debug(message: string, ...args: unknown[]): void {
    console.debug(message, ...args);
  },

  info(message: string, ...args: unknown[]): void {
    console.info(message, ...args);
  },

  warning(message: string, ...args: unknown[]): void {
    console.warn(message, ...args);
  },

  error(message: string, ...args: unknown[]): void {
    console.error(message, ...args);
  },

  setLevel(level: LogLevel): void {
    LOG_CONFIG.level = level;
  },

  disable(): void {
    LOG_CONFIG.enabled = false;
  },

  enable(): void {
    LOG_CONFIG.enabled = true;
  },

  restore(): void {
    console.debug = originalConsole.debug;
    console.info = originalConsole.info;
    console.log = originalConsole.log;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
  }
};

export default logger;
