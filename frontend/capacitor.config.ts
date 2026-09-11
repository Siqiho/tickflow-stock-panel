import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.simon.onetrading',
  appName: 'one-trading',
  webDir: 'dist',
  loggingBehavior: 'none',
  appendUserAgent: ' one-trading-android/0.1.69',
  backgroundColor: '#0A0A0B',
  android: {
    allowMixedContent: false,
    backgroundColor: '#0A0A0B',
    webContentsDebuggingEnabled: false,
  },
  server: {
    url: 'https://one-trading-private-simon.zeabur.app',
    allowNavigation: ['one-trading-backup.siqiho.workers.dev'],
    cleartext: false,
    errorPath: 'offline.html',
  },
}

export default config
