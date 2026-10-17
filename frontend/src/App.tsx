import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/loginPage'
import { RegisterPage } from './pages/registerPage'
import { RoomsPage } from './pages/roomsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/rooms" element={<RoomsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/rooms" replace />} />
    </Routes>
  )
}