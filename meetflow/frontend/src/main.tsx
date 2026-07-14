import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { configureAmplify } from '@/lib/amplify'

configureAmplify()

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
