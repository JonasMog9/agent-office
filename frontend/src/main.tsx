import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Health from './health/Health.tsx'
import Stats from './stats/Stats.tsx'

const path = window.location.pathname.replace(/\/+$/, '')
const page = path === '/stats' ? <Stats /> : path === '/health' ? <Health /> : <App />

createRoot(document.getElementById('root')!).render(<StrictMode>{page}</StrictMode>)
