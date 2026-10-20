import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { RoomLayout } from './components/roomLayout'
import { CreateTaskPage } from './pages/CreateTaskPage'
import { JoinPage } from './pages/joinPage'
import { JoinRequestsPage } from './pages/JoinRequestsPage'
import { LoginPage } from './pages/loginPage'
import { MembersPage } from './pages/MembersPage'
import { RegisterPage } from './pages/registerPage'
import { RoomHomePage } from './pages/RoomHomePage'
import { RoomSettingsPage } from './pages/RoomSettingsPage'
import { RoomsPage } from './pages/roomsPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import { RoomProvider } from './room/roomProvider'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/rooms" element={<RoomsPage />} />
        <Route path="/join/:code" element={<JoinPage />} />

        <Route path="/rooms/:roomId" element={<RoomProvider />}>
          <Route element={<RoomLayout />}>
            <Route index element={<RoomHomePage />} />
            <Route path="members" element={<MembersPage />} />
            <Route path="join-requests" element={<JoinRequestsPage />} />
            <Route path="settings" element={<RoomSettingsPage />} />
            <Route path="tasks/new" element={<CreateTaskPage />} />
            <Route path="tasks/:taskId" element={<TaskDetailPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/rooms" replace />} />
    </Routes>
  )
}