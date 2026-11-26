import { Navigate, Route, Routes } from 'react-router'
import NavBar from './components/NavBar.tsx'
import AuthPage from './pages/AuthPage.tsx'
import NewsPage from './pages/NewsPage.tsx'
import ProfilePage from './pages/ProfilePage.tsx'
import RecommendationsPage from './pages/RecommendationsPage.tsx'
import SettingsPage from './pages/SettingsPage.tsx'
import WelcomePage from './pages/WelcomePage.tsx'

export default function App() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route index element={<NewsPage />} />
        <Route path="recommendations" element={<RecommendationsPage />} />
        {/* Keys give each form fresh state when switching between log in and sign up. */}
        <Route path="login" element={<AuthPage key="login" mode="login" />} />
        <Route path="signup" element={<AuthPage key="signup" mode="signup" />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="welcome" element={<WelcomePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
