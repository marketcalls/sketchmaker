import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ErrorFallbackProps {
  onReset?: () => void;
}

/**
 * Shown when a render error escapes to the top-level boundary. Rendered outside
 * the router and layouts, so it stands alone.
 */
export function ErrorFallback({ onReset }: ErrorFallbackProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6" role="alert">
      <div className="w-full max-w-md text-center">
        <AlertTriangle className="mx-auto h-6 w-6 text-destructive" aria-hidden="true" />

        <h1 className="mt-4 text-2xl font-semibold tracking-tight">Something went wrong</h1>
        <p className="mt-2 text-pretty text-sm text-muted-foreground">
          This page stopped responding. Reloading usually clears it.
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button onClick={onReset ?? (() => window.location.reload())}>
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Try again
          </Button>
          <Button variant="outline" onClick={() => (window.location.href = '/')}>
            <Home className="h-4 w-4" aria-hidden="true" />
            Go home
          </Button>
        </div>
      </div>
    </div>
  );
}

interface ErrorBoundaryProps {
  children: ReactNode;
}

/** Keeps a render error from blanking the whole app. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Render error', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return <ErrorFallback onReset={() => this.setState({ hasError: false })} />;
    }
    return this.props.children;
  }
}
