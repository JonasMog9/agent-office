import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import Stats from './stats/Stats.tsx'

const page = window.location.pathname.replace(/\/+$/, '') === '/stats' ? <Stats /> : <App />

createRoot(document.getElementById('root')!).render(<StrictMode>{page}</StrictMode>)
