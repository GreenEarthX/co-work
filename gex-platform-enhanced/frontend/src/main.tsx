// Screen: App bootstrap (no screen)
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { UserRoleProvider } from './contexts/UserRoleContext'
import { discardExpiredSession } from './lib/authToken'
import { installFetchAuthBridge } from './lib/fetchAuthBridge'

// UserRoleProvider initialises from storage, so a session that expired while
// the tab was closed must be gone before the first render — otherwise the
// signed-in routes render and every API call 401s (HANDOFF §8.11).
discardExpiredSession()
installFetchAuthBridge()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <UserRoleProvider>
      <App />
    </UserRoleProvider>
  </React.StrictMode>,
)
