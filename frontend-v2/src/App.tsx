import { Navigate, Route, Routes } from 'react-router-dom'
import { sessionHint } from './auth/sessionHint'
import { useAuth } from './auth/useAuth'
import { LandingPage } from './landing/LandingPage'
import { Shell } from './components/Shell'
import { lastRoom } from './lib/lastRoom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { ForgotPasswordPage, ResetPasswordPage } from './pages/PasswordPages'
import { CancelEmailChangePage, ConfirmEmailPage } from './pages/EmailPages'
import { AccountPage } from './pages/AccountPage'
import { AdminPage } from './pages/AdminPage'
import { NotificationsPage } from './pages/NotificationsPage'
import { CalendarPage } from './pages/CalendarPage'
import { ChatPage } from './pages/ChatPage'
import { EditTaskPage } from './pages/EditTaskPage'
import { JoinPage } from './pages/JoinPage'
import { MembersPage } from './pages/MembersPage'
import { MyWorkPage } from './pages/MyWorkPage'
import { NewTaskPage } from './pages/NewTaskPage'
import { RequestsPage } from './pages/RequestsPage'
import { RoomHomePage } from './pages/RoomHomePage'
import { RoomsPage } from './pages/RoomsPage'
import { SettingsPage } from './pages/SettingsPage'
import { TaskPage } from './pages/TaskPage'
import { TemplateEditorPage } from './pages/TemplateEditorPage'
import { TemplatesPage } from './pages/TemplatesPage'
import { RoomProvider } from './room/RoomProvider'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/confirm-email" element={<ConfirmEmailPage />} />
      <Route path="/cancel-email-change" element={<CancelEmailChangePage />} />
      <Route path="/" element={<Front />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/join/:code" element={<JoinPage />} />

        <Route element={<Shell />}>
        <Route path="/rooms" element={<RoomsPage />} />
        <Route path="/my-work" element={<MyWorkPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />

        <Route path="/rooms/:roomId" element={<RoomProvider />}>
          <Route index element={<RoomHomePage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="tasks/new" element={<NewTaskPage />} />
          <Route path="tasks/:taskId" element={<TaskPage />} />
          <Route path="tasks/:taskId/edit" element={<EditTaskPage />} />
          <Route path="templates" element={<TemplatesPage />} />
          <Route path="templates/new" element={<TemplateEditorPage />} />
          <Route path="templates/:templateId" element={<TemplateEditorPage />} />
          <Route path="members" element={<MembersPage />} />
          <Route path="requests" element={<RequestsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

/** "/": the landing page for visitors; your last room once you're signed in. */
function Front() {
  const { user, loading } = useAuth()
  if (user) return <LastRoom />
  if (loading && sessionHint.get()) return null // probably signed in: wait a moment rather than flash the landing page
  return <LandingPage />
}

/** Signing in (or opening the app) takes you back to the room you were last in. */
function LastRoom() {
  const { user } = useAuth()
  const id = lastRoom.get()
  return <Navigate to={id && user?.rooms.some((r) => r.id === id) ? `/rooms/${id}` : '/rooms'} replace />
}
