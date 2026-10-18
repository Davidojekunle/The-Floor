import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/loginPage'
import { RegisterPage } from './pages/registerPage'
import { RoomsPage } from './pages/roomsPage'
import { JoinPage } from './pages/joinPage'
import { MembersPage } from './pages/MembersPage'
import { RoomLayout } from './components/roomLayout'
import { RoomProvider } from './room/roomProvider'
import { JoinRequestsPage } from './pages/JoinRequestsPage'
import { RoomHomePage } from './pages/RoomHomePage'
import { RoomSettingsPage } from './pages/RoomSettingsPage'
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/rooms" element={<RoomsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/rooms" replace />} />
    
       
       <Route element={<ProtectedRoute />}>
  <Route path="/rooms" element={<RoomsPage />} />
  <Route path="/join/:code" element={<JoinPage />} />

  <Route path="/rooms/:roomId" element={<RoomProvider />}>
    <Route element={<RoomLayout />}>
      <Route index element={<RoomHomePage />} />
      <Route path="join-requests" element={<JoinRequestsPage />} />
      <Route path="settings" element={<RoomSettingsPage />} />
    </Route>
  </Route>
</Route>
<Route path="members" element={<MembersPage />} />
</Routes>


    
  )
}