import { Navigate, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  AuthCard,
  AuthHeader,
  FieldError,
  FormAlert,
  PasswordInput,
} from '@/components/auth/AuthParts';
import { useAuthStore } from '@/stores/authStore';
import { safeRedirectPath } from '@/lib/security';

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { login, isLoading, error, clearError, setupRequired } = useAuthStore();

  // Get redirect URL from state (SPA navigation) or query param (fallback for page reloads)
  const fromLocation = location.state?.from;
  const redirectParam = searchParams.get('redirect');
  // `redirect` is attacker-controllable, so only same-origin paths are honoured.
  const from = safeRedirectPath(
    fromLocation ? `${fromLocation.pathname}${fromLocation.search || ''}` : redirectParam,
    '/generate'
  );

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    try {
      clearError();
      await login(data.username, data.password);
      navigate(from, { replace: true });
    } catch {
      // Error is handled by the store
    }
  };

  if (setupRequired) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <AuthCard>
      <AuthHeader title="Welcome back" description="Sign in with your username and password." />

      {error && <FormAlert>{error}</FormAlert>}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="username">Username</Label>
          <Input
            id="username"
            type="text"
            autoComplete="username"
            placeholder="Your username"
            aria-invalid={errors.username ? true : undefined}
            aria-describedby={errors.username ? 'username-error' : undefined}
            {...register('username')}
            disabled={isLoading}
            autoFocus
          />
          <FieldError id="username-error" message={errors.username?.message} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder="Your password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? 'password-error' : undefined}
            {...register('password')}
            disabled={isLoading}
          />
          <FieldError id="password-error" message={errors.password?.message} />
        </div>

        <Button type="submit" className="w-full" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Signing in
            </>
          ) : (
            'Sign in'
          )}
        </Button>
      </form>
    </AuthCard>
  );
}
