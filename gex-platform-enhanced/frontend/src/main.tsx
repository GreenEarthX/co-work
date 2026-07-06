// Screen: App bootstrap (no screen)
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { UserRoleProvider } from './contexts/UserRoleContext'

const AUTH_SESSION_KEY = 'gex_auth_session'
const USER_ROLE_KEY = 'gex_user_role'

type StoredAuthSession = {
  token?: string
  email?: string
}

type StoredRole = {
  company_name?: string
  company_type?: string
  business_function?: string
  service_type?: string | null
  capabilities?: string[]
}

declare global {
  interface Window {
    __gexFetchAuthInstalled__?: boolean
  }
}

function readStorageJson<T>(key: string): T | null {
  const value = window.localStorage.getItem(key)
  if (!value) return null

  try {
    return JSON.parse(value) as T
  } catch {
    return null
  }
}

function toCompanySlug(value?: string): string {
  if (!value) return 'demo-company'
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function shouldDecorateRequest(input: RequestInfo | URL): boolean {
  const rawUrl =
    typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url

  const url = new URL(rawUrl, window.location.origin)
  const isPlatformApiPath = url.pathname.startsWith('/api/')
  const isLocalPlatformApi =
    url.hostname === 'localhost' &&
    url.port === '8000' &&
    url.pathname.startsWith('/api/')

  return isPlatformApiPath || isLocalPlatformApi
}

function installFetchAuthBridge() {
  if (window.__gexFetchAuthInstalled__) return
  window.__gexFetchAuthInstalled__ = true

  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!shouldDecorateRequest(input)) {
      return nativeFetch(input, init)
    }

    const session = readStorageJson<StoredAuthSession>(AUTH_SESSION_KEY)
    const role = readStorageJson<StoredRole>(USER_ROLE_KEY)
    const headers = new Headers(input instanceof Request ? input.headers : undefined)

    if (init?.headers) {
      new Headers(init.headers).forEach((value, key) => headers.set(key, value))
    }

    if (session?.token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${session.token}`)
    }
    if (session?.email && !headers.has('x-demo-user')) {
      headers.set('x-demo-user', session.email)
    }
    if (role?.company_name && !headers.has('x-demo-company')) {
      headers.set('x-demo-company', toCompanySlug(role.company_name))
    }
    if (role?.company_type && !headers.has('x-demo-company-type')) {
      headers.set('x-demo-company-type', role.company_type)
    }
    if (role?.business_function && !headers.has('x-demo-function')) {
      headers.set('x-demo-function', role.business_function)
    }
    if (role?.service_type && !headers.has('x-demo-service-type')) {
      headers.set('x-demo-service-type', role.service_type)
    }
    if (role?.capabilities?.length && !headers.has('x-demo-capabilities')) {
      headers.set('x-demo-capabilities', role.capabilities.join(','))
    }

    if (input instanceof Request) {
      return nativeFetch(new Request(input, { ...init, headers }))
    }

    return nativeFetch(input, { ...init, headers })
  }
}

installFetchAuthBridge()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <UserRoleProvider>
      <App />
    </UserRoleProvider>
  </React.StrictMode>,
)
