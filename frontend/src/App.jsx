import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import MainLayout from './components/MainLayout';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import Reports from './pages/Reports';
import Login from './pages/Login';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import './App.css';

const ProtectedRoute = ({ children }) => {
  const { token } = useAuth();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

function App() {
  const [isDark, setIsDark] = useState(true);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#6366f1',
          borderRadius: 8,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
        },
        components: {
          Layout: {
            siderBg: isDark ? '#111827' : '#ffffff',
            headerBg: isDark ? '#111827' : '#ffffff',
            bodyBg: isDark ? '#0f172a' : '#f5f5f5',
          },
          Menu: {
            darkItemBg: '#111827',
            darkItemSelectedBg: '#1e293b',
          },
        },
      }}
    >
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/*" element={
              <ProtectedRoute>
                <MainLayout isDark={isDark} setIsDark={setIsDark}>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/reports" element={<Reports />} />
                    <Route path="/projects/:id" element={<ProjectDetail />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </MainLayout>
              </ProtectedRoute>
            } />
          </Routes>
        </Router>
      </AuthProvider>
    </ConfigProvider>
  );
}

export default App;
