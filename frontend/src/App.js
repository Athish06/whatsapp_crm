import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Toaster } from 'sonner';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import CampaignCreatorPage from './pages/CampaignCreatorPage';
import BatchMonitorPage from './pages/BatchMonitorPage';
import TemplatesPage from './pages/TemplatesPage';
import Sidebar from './components/Sidebar';
import './App.css';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#121212]">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
};

const DashboardLayout = ({ children }) => {
  return (
    <div className="flex h-screen bg-[#121212]">
      <Sidebar />
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        {children}
      </main>
    </div>
  );
};

const HistoryPage = () => (
  <div className="p-8">
    <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
      Campaign History
    </h1>
    <p className="text-muted-foreground">View your past campaigns and their performance</p>
    <div className="mt-8 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-12 text-center">
      <p className="text-muted-foreground">History feature coming soon</p>
    </div>
  </div>
);

const SettingsPage = () => (
  <div className="p-8">
    <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
      Settings
    </h1>
    <p className="text-muted-foreground">Manage your account and preferences</p>
    <div className="mt-8 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-12 text-center">
      <p className="text-muted-foreground">Settings feature coming soon</p>
    </div>
  </div>
);

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: '#1C1C1C',
              border: '1px solid #2E2E2E',
              color: '#ffffff',
            },
          }}
        />
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
              <DashboardLayout>
                <DashboardPage />
              </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/campaign"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <CampaignCreatorPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/monitor"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <BatchMonitorPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/templates"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <TemplatesPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <HistoryPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <SettingsPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
