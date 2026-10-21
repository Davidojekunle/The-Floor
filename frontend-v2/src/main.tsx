import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
// Fonts ship with the app (no Google Fonts request): faster first paint and a strict content security policy.
import '@fontsource-variable/bricolage-grotesque/opsz.css'
import '@fontsource-variable/hanken-grotesk/index.css'
import '@fontsource/dm-mono/400.css'
import '@fontsource/dm-mono/500.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/app.css'
import './styles/chat.css'
import './styles/shell.css'
import './styles/landing.css'
import './styles/settings.css'
import App from './App'
import { AuthProvider } from './auth/authProvider'
import { ToastProvider } from './components/toast'
import { LiveProvider } from './live/LiveProvider'
import { registerServiceWorker } from './lib/push'

const queryClient = new QueryClient()
registerServiceWorker() // browser push only (public/sw.js)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ToastProvider>
            <LiveProvider>
              <App />
            </LiveProvider>
          </ToastProvider>
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
)
