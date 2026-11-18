import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import AuthProvider from './components/AuthProvider.tsx'
import BriefingMenuProvider from './components/BriefingMenuProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <BriefingMenuProvider>
          <App />
        </BriefingMenuProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
