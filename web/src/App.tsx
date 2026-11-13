import { Navigate, Route, Routes } from 'react-router'
import NavBar from './components/NavBar.tsx'
import AuthPage from './pages/AuthPage.tsx'
import NewsPage from './pages/NewsPage.tsx'
import ProfilePage from './pages/ProfilePage.tsx'

export default function App() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route index element={<NewsPage />} />
        {/* Keys give each form fresh state when switching between log in and sign up. */}
        <Route path="login" element={<AuthPage key="login" mode="login" />} />
        <Route path="signup" element={<AuthPage key="signup" mode="signup" />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
