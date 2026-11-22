import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import type { Filters } from './models'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, { ...init, credentials: 'same-origin' })
  if (response.status === 204) return undefined as T
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    if (response.status === 401 && init?.method !== 'POST') window.dispatchEvent(new Event('logbook-logout'))
    throw new ApiError(response.status, typeof body?.detail === 'string' ? body.detail : '请求失败，请检查输入或稍后重试。')
  }
  return response.json()
}

export function post(value: object): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  }
}

export function query(filters: Filters, extra: Record<string, string> = {}) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries({ ...filters, ...extra })) {
    if (value) params.set(name, String(value))
  }
  const encoded = params.toString()
  return encoded ? '?' + encoded : ''
}

export function useResource<T>(url: Ref<string | null>, revision: Ref<number>) {
  const data = shallowRef<T | null>(null)
  const pending = ref(false)
  const error = ref('')
  const attempt = ref(0)

  watch([url, revision, attempt], async ([path], _, onCleanup) => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    error.value = ''
    data.value = null
    pending.value = Boolean(path)
    if (!path) return

    try {
      const response = await api<T>(path, { signal: controller.signal })
      if (!controller.signal.aborted) data.value = response
    } catch (reason) {
      if (!controller.signal.aborted) error.value = message(reason)
    } finally {
      if (!controller.signal.aborted) pending.value = false
    }
  }, { immediate: true })

  return { data, pending, error, refresh: () => { attempt.value++ } }
}

export function rolePath(role: Ref<{ id: string } | null>, suffix: () => string) {
  return computed(() => role.value ? '/roles/' + role.value.id + suffix() : null)
}

export function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : '暂时无法连接，请稍后重试。'
}
