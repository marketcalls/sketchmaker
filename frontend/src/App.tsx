import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, Suspense, lazy } from 'react';
import { Loader2 } from 'lucide-react';

// Layouts - keep as eager imports (needed for route structure)
import { MainLayout } from '@/components/layout/MainLayout';
import { AuthLayout } from '@/components/layout/AuthLayout';

// Auth pages - eager load for fast initial experience
import { LoginPage } from '@/pages/auth/LoginPage';
import { SetupPage } from '@/pages/auth/SetupPage';

// Components
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

// Stores
import { useAuthStore } from '@/stores/authStore';
import { usePricingStore } from '@/stores/pricingStore';
import { useUIStore } from '@/stores/uiStore';

// =============================================================================
// LAZY LOADED PAGES - Split into separate chunks
// =============================================================================

const GeneratePage = lazy(() => import('@/pages/user/GeneratePage').then(m => ({ default: m.GeneratePage })));
const StoriesPage = lazy(() => import('@/pages/user/StoriesPage').then(m => ({ default: m.StoriesPage })));
const SubtitlesPage = lazy(() => import('@/pages/user/SubtitlesPage').then(m => ({ default: m.SubtitlesPage })));
const GalleryPage = lazy(() => import('@/pages/user/GalleryPage').then(m => ({ default: m.GalleryPage })));
const MagixPage = lazy(() => import('@/pages/user/MagixPage').then(m => ({ default: m.MagixPage })));
const LogoPage = lazy(() => import('@/pages/user/LogoPage').then(m => ({ default: m.LogoPage })));
const ExplainerPage = lazy(() => import('@/pages/user/ExplainerPage').then(m => ({ default: m.ExplainerPage })));
const VirtualPage = lazy(() => import('@/pages/user/VirtualPage').then(m => ({ default: m.VirtualPage })));
const MotionControlPage = lazy(() => import('@/pages/user/MotionControlPage').then(m => ({ default: m.MotionControlPage })));
const AssetsPage = lazy(() => import('@/pages/user/AssetsPage').then(m => ({ default: m.AssetsPage })));
const LipSyncPage = lazy(() => import('@/pages/user/LipSyncPage').then(m => ({ default: m.LipSyncPage })));
const RemoveBgPage = lazy(() => import('@/pages/user/RemoveBgPage').then(m => ({ default: m.RemoveBgPage })));
const ReducePage = lazy(() => import('@/pages/user/ReducePage').then(m => ({ default: m.ReducePage })));
const SettingsPage = lazy(() => import('@/pages/user/SettingsPage').then(m => ({ default: m.SettingsPage })));
const UsagePage = lazy(() => import('@/pages/user/UsagePage').then(m => ({ default: m.UsagePage })));
const MyJobsPage = lazy(() => import('@/pages/user/MyJobsPage').then(m => ({ default: m.MyJobsPage })));
const NotificationsPage = lazy(() => import('@/pages/user/NotificationsPage').then(m => ({ default: m.NotificationsPage })));

// Motion Graphics Studio
const MotionGraphicsHomePage = lazy(() => import('@/pages/user/motion-graphics/MotionGraphicsHomePage').then(m => ({ default: m.MotionGraphicsHomePage })));
const MotionGraphicsStudioPage = lazy(() => import('@/pages/user/motion-graphics/MotionGraphicsStudioPage').then(m => ({ default: m.MotionGraphicsStudioPage })));

// =============================================================================
// LOADING COMPONENT
// =============================================================================

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  );
}

// =============================================================================
// APP COMPONENT
// =============================================================================

function App() {
  const { checkAuth, isAuthenticated } = useAuthStore();
  const { fetchCosts } = usePricingStore();
  const { theme, setTheme } = useUIStore();

  useEffect(() => {
    // Check auth on mount
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    // Fetch the price table when authenticated
    if (isAuthenticated) {
      fetchCosts();
    }
  }, [isAuthenticated, fetchCosts]);

  useEffect(() => {
    // Apply theme on mount, fallback to 'dark' if invalid value
    const validTheme = theme === 'light' || theme === 'dark' ? theme : 'dark';
    setTheme(validTheme);
  }, []);

  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Navigate to="/generate" replace />} />

          {/* Auth routes */}
          <Route element={<AuthLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/setup" element={<SetupPage />} />
          </Route>

          {/* Protected user routes */}
          <Route
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/generate" element={<GeneratePage />} />
            <Route path="/stories" element={<StoriesPage />} />
            <Route path="/motion-graphics" element={<MotionGraphicsHomePage />} />
            <Route path="/motion-graphics/:id" element={<MotionGraphicsStudioPage />} />
            <Route path="/subtitles" element={<SubtitlesPage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/magix" element={<MagixPage />} />
            <Route path="/logo" element={<LogoPage />} />
            <Route path="/explainer" element={<ExplainerPage />} />
            <Route path="/virtual" element={<VirtualPage />} />
            <Route path="/motion-control" element={<MotionControlPage />} />
            <Route path="/lip-sync" element={<LipSyncPage />} />
            <Route path="/remove-bg" element={<RemoveBgPage />} />
            <Route path="/reduce" element={<ReducePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/my-assets" element={<AssetsPage />} />
            <Route path="/my-jobs" element={<MyJobsPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
          </Route>

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/generate" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
