import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const primaryEndpoint = 'https://one-trading-private-simon.zeabur.app'
const backupEndpoint = 'https://one-trading-backup.siqiho.workers.dev'
const offlineHtml = readFileSync(resolve(process.cwd(), 'public/offline.html'), 'utf8')
const capacitorConfig = readFileSync(resolve(process.cwd(), 'capacitor.config.ts'), 'utf8')

describe('Android offline fallback page', () => {
  it('offers exactly the fixed primary and backup HTTPS endpoints', () => {
    const endpoints = [...offlineHtml.matchAll(/data-endpoint="([^"]+)"/g)].map(
      (match) => match[1],
    )

    expect(endpoints).toEqual([primaryEndpoint, backupEndpoint])
    expect(new Set(endpoints).size).toBe(2)
    expect(endpoints.every((endpoint) => endpoint.startsWith('https://'))).toBe(true)
  })

  it('switches only after a button click and never retries automatically', () => {
    expect(offlineHtml).toContain('button.addEventListener(\'click\'')
    expect(offlineHtml).toContain('allowedEndpoints.has(endpoint)')
    expect(offlineHtml).toContain('window.location.replace(endpoint)')
    expect(offlineHtml).not.toContain('location.reload')
    expect(offlineHtml).not.toMatch(/setTimeout|setInterval|fetch\s*\(/)
  })

  it('keeps Zeabur as the startup URL and allowlists only the Worker fallback', () => {
    expect(capacitorConfig).toContain(`url: '${primaryEndpoint}'`)
    expect(capacitorConfig).toContain(
      "allowNavigation: ['one-trading-backup.siqiho.workers.dev']",
    )
  })
})
