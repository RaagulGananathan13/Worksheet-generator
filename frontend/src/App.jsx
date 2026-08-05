import { useEffect } from 'react';
import useWorksheetStore from './store/worksheetStore';
import useAuthStore from './store/authStore';
import AuthPage from './components/Auth/AuthPage';
import Dashboard from './components/Dashboard/Dashboard';
import UploadScreen from './components/UploadScreen/UploadScreen';
import SinhalaUploadScreen from './components/UploadScreen/SinhalaUploadScreen';
import EditorLayout from './components/Editor/EditorLayout';

export default function App() {
  const view = useWorksheetStore((s) => s.view);
  const setView = useWorksheetStore((s) => s.setView);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const initialize = useAuthStore((s) => s.initialize);

  // Initialize auth on mount — check stored JWT
  useEffect(() => {
    initialize();
  }, [initialize]);

  // Redirect to auth if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated && view !== 'auth') {
      setView('auth');
    }
    if (!isLoading && isAuthenticated && view === 'auth') {
      setView('dashboard');
    }
  }, [isLoading, isAuthenticated, view, setView]);

  // Show loading spinner while checking stored token
  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-surface-50">
        <div className="flex flex-col items-center gap-3 animate-fade-in">
          <img src="/gb-logo.jpg" alt="GeniusBees" className="h-12 object-contain opacity-60" />
          <div className="w-6 h-6 border-2 border-surface-300 border-t-brand-orange rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-surface-100 text-surface-900">
      {view === 'auth' && <AuthPage />}
      {view === 'dashboard' && <Dashboard />}
      {view === 'upload' && <UploadScreen />}
      {view === 'upload-sinhala' && <SinhalaUploadScreen />}
      {view === 'editor' && <EditorLayout />}
    </div>
  );
}
