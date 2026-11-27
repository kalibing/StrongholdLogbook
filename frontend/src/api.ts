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
    throw new ApiError(response.status, errorText(response.status, body))
  }
  return response.json()
}

/** 把非 2xx 的响应翻成一句人话：后端没起来、来源被拦、还是参数不合法。 */
function errorText(status: number, body: any): string {
  if (typeof body?.detail === 'string' && body.detail.trim()) return body.detail
  if (status >= 500) return '后端暂时不可用，请稍后重试。'
  if (status === 403) return '请求来源被拒绝，请用站点地址打开页面后重试。'
  if (status === 429) return '请求太频繁，请稍后再试。'
  if (status === 422) return '输入格式不正确，请检查后重试。'
  return '请求没有成功，请检查输入或稍后重试。'
}

export function post(value: object): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  }
}

/** 带 JSON 请求体的非 POST 请求（PATCH / PUT / DELETE）。 */
export function send(method: 'PATCH' | 'PUT' | 'DELETE', value?: object): RequestInit {
  return value === undefined
    ? { method }
    : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }
}

export function query(filters: Filters, extra: Record<string, string> = {}) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries({ ...filters, ...extra })) {
    if (value) params.set(name, String(value))
  }
  const encoded = params.toString()
  return encoded ? '?' + encoded : ''
}

export function useResource<T>(url: Ref<string | null>, revision: Ref<number>, keepPrevious = false) {
  const data = shallowRef<T | null>(null)
  const pending = ref(false)
  const error = ref('')
  const resolvedUrl = ref<string | null>(null)
  const attempt = ref(0)

  watch([url, revision, attempt], async ([path], _, onCleanup) => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    error.value = ''
    if (!path || !keepPrevious) {
      data.value = null
      resolvedUrl.value = null
    }
    pending.value = Boolean(path)
    if (!path) return

    try {
      const response = await api<T>(path, { signal: controller.signal })
      if (!controller.signal.aborted) {
        data.value = response
        resolvedUrl.value = path
      }
    } catch (reason) {
      if (!controller.signal.aborted) error.value = message(reason)
    } finally {
      if (!controller.signal.aborted) pending.value = false
    }
  }, { immediate: true })

  return { data, pending, error, resolvedUrl, refresh: () => { attempt.value++ } }
}

export function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : '暂时无法连接，请稍后重试。'
}
