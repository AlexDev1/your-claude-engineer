import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import App from './App'
import Analytics from './pages/Analytics'
import TaskManager from './pages/TaskManager'
import Settings from './pages/Settings'
import Import from './pages/Import'
import Export from './pages/Export'
import './styles/themes.css'
import './styles/mobile.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<TaskManager />} />
            <Route path="tasks" element={<TaskManager />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="import" element={<Import />} />
            <Route path="export" element={<Export />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
)
