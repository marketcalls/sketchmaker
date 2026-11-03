import { Navigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, user, isLoading, setupRequired } = useAuthStore();
  const location = useLocation();

  // Only the first check blocks the page. A later re-check (checkAuth runs
  // again on focus and after some actions) keeps the signed-in page mounted,
  // so nothing flashes or loses its state.
  if (isLoading && !(isAuthenticated && user)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" role="status">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (setupRequired) {
      return <Navigate to="/setup" replace />;
    }
    // Pass redirect URL both in state (for SPA navigation) and query param (as fallback)
    const redirectPath = `${location.pathname}${location.search}`;
    const loginUrl = redirectPath && redirectPath !== '/'
      ? `/login?redirect=${encodeURIComponent(redirectPath)}`
      : '/login';
    return <Navigate to={loginUrl} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
