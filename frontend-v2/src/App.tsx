import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { sessionHint } from './auth/sessionHint'
import { useAuth } from './auth/useAuth'
const LandingPage = lazy(() => import('./landing/LandingPage').then((m) => ({ default: m.LandingPage })))
import { Shell } from './components/Shell'
import { lastRoom } from './lib/lastRoom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { SessionPending } from './components/SessionPending'
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
const PrivacyPage = lazy(() => import('./pages/PrivacyPage').then((m) => ({ default: m.PrivacyPage })))
const AuthPage = lazy(() => import('./pages/AuthPage').then((m) => ({ default: m.AuthPage })))
const ForgotPasswordPage = lazy(() => import('./pages/PasswordPages').then((m) => ({ default: m.ForgotPasswordPage })))
const ResetPasswordPage = lazy(() => import('./pages/PasswordPages').then((m) => ({ default: m.ResetPasswordPage })))
const VerifyEmailPage = lazy(() => import('./pages/EmailPages').then((m) => ({ default: m.VerifyEmailPage })))
const CancelEmailChangePage = lazy(() => import('./pages/EmailPages').then((m) => ({ default: m.CancelEmailChangePage })))
const ConfirmEmailPage = lazy(() => import('./pages/EmailPages').then((m) => ({ default: m.ConfirmEmailPage })))
const AccountPage = lazy(() => import('./pages/AccountPage').then((m) => ({ default: m.AccountPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage').then((m) => ({ default: m.NotificationsPage })))
const CalendarPage = lazy(() => import('./pages/CalendarPage').then((m) => ({ default: m.CalendarPage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then((m) => ({ default: m.ChatPage })))
const EditTaskPage = lazy(() => import('./pages/EditTaskPage').then((m) => ({ default: m.EditTaskPage })))
const JoinPage = lazy(() => import('./pages/JoinPage').then((m) => ({ default: m.JoinPage })))
const MembersPage = lazy(() => import('./pages/MembersPage').then((m) => ({ default: m.MembersPage })))
const MyWorkPage = lazy(() => import('./pages/MyWorkPage').then((m) => ({ default: m.MyWorkPage })))
const NewTaskPage = lazy(() => import('./pages/NewTaskPage').then((m) => ({ default: m.NewTaskPage })))
const RequestsPage = lazy(() => import('./pages/RequestsPage').then((m) => ({ default: m.RequestsPage })))
const RoomHomePage = lazy(() => import('./pages/RoomHomePage').then((m) => ({ default: m.RoomHomePage })))
const RoomsPage = lazy(() => import('./pages/RoomsPage').then((m) => ({ default: m.RoomsPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const TaskPage = lazy(() => import('./pages/TaskPage').then((m) => ({ default: m.TaskPage })))
const TemplateEditorPage = lazy(() => import('./pages/TemplateEditorPage').then((m) => ({ default: m.TemplateEditorPage })))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage').then((m) => ({ default: m.TemplatesPage })))
import { RoomProvider } from './room/RoomProvider'

// Each page's code is fetched the first time it's opened, so a phone downloads only what it shows.
const page = (el: ReactNode) => <Suspense fallback={null}>{el}</Suspense>

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={page(<AuthPage mode="login" />)} />
      <Route path="/register" element={page(<AuthPage mode="register" />)} />
      <Route path="/forgot-password" element={page(<ForgotPasswordPage />)} />
      <Route path="/reset-password" element={page(<ResetPasswordPage />)} />
      <Route path="/confirm-email" element={page(<ConfirmEmailPage />)} />
      <Route path="/cancel-email-change" element={page(<CancelEmailChangePage />)} />
      <Route path="/verify-email" element={page(<VerifyEmailPage />)} />
      <Route path="/" element={<Front />} />
      <Route path="/privacy" element={page(<PrivacyPage />)} />

      <Route element={<ProtectedRoute />}>
        <Route path="/join/:code" element={page(<JoinPage />)} />

        <Route element={<Shell />}>
        <Route path="/rooms" element={page(<RoomsPage />)} />
        <Route path="/my-work" element={page(<MyWorkPage />)} />
        <Route path="/account" element={page(<AccountPage />)} />
        <Route path="/admin" element={page(<AdminPage />)} />
        <Route path="/notifications" element={page(<NotificationsPage />)} />

        <Route path="/rooms/:roomId" element={<RoomProvider />}>
          <Route index element={page(<RoomHomePage />)} />
          <Route path="calendar" element={page(<CalendarPage />)} />
          <Route path="chat" element={page(<ChatPage />)} />
          <Route path="tasks/new" element={page(<NewTaskPage />)} />
          <Route path="tasks/:taskId" element={page(<TaskPage />)} />
          <Route path="tasks/:taskId/edit" element={page(<EditTaskPage />)} />
          <Route path="templates" element={page(<TemplatesPage />)} />
          <Route path="templates/new" element={page(<TemplateEditorPage />)} />
          <Route path="templates/:templateId" element={page(<TemplateEditorPage />)} />
          <Route path="members" element={page(<MembersPage />)} />
          <Route path="requests" element={page(<RequestsPage />)} />
          <Route path="settings" element={page(<SettingsPage />)} />
          <Route path="*" element={page(<NotFoundPage />)} />
        </Route>
        </Route>
      </Route>

      <Route path="*" element={page(<NotFoundPage />)} />
    </Routes>
  )
}

/** "/": the landing page for visitors; your last room once you're signed in. */
function Front() {
  const { user, loading } = useAuth()
  if (user) return <LastRoom />
  if (loading && sessionHint.get()) return <SessionPending /> // probably signed in: wait rather than flash the landing page
  return page(<LandingPage />)
}

/** Signing in (or opening the app) takes you back to the room you were last in. */
function LastRoom() {
  const { user } = useAuth()
  const id = lastRoom.get()
  return <Navigate to={id && user?.rooms.some((r) => r.id === id) ? `/rooms/${id}` : '/rooms'} replace />
}
