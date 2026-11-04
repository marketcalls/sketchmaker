import { Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';

/** Unknown paths: into the studio when signed in, otherwise the home page.
 * Waits for the auth check, because a remembered session may have expired and
 * would otherwise bounce the visitor through /generate to the login page. */
export function UnknownPathRedirect() {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" role="status">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return <Navigate to={isAuthenticated ? '/generate' : '/'} replace />;
}
