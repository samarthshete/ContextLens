import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/benchmark" element={<App view="run" />} />
        <Route path="/runs/:runId" element={<App view="detail" />} />
        <Route path="/runs" element={<App view="runs" />} />
        <Route path="/queue" element={<App view="queue" />} />
        <Route path="/compare" element={<App view="compare" />} />
        <Route path="/dashboard" element={<App view="dashboard" />} />
        <Route path="/documents/:documentId" element={<App view="document" />} />
        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/benchmark" replace />} />
        <Route path="*" element={<Navigate to="/benchmark" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
