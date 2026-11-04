import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  AuthCard,
  AuthCardSkeleton,
  AuthHeader,
  FieldError,
  FormAlert,
  PasswordChecklist,
  PasswordInput,
} from '@/components/auth/AuthParts';
import { useAuthStore } from '@/stores/authStore';
import { getErrorMessage } from '@/utils/errors';

const PASSWORD_MIN_LENGTH = 12;
const PASSWORD_MAX_BYTES = 72;

const setupSchema = z
  .object({
    username: z
      .string()
      .min(3, 'Username must be at least 3 characters')
      .max(30, 'Username must be at most 30 characters')
      .regex(/^[a-zA-Z0-9_]+$/, 'Username can only contain letters, numbers, and underscores'),
    password: z
      .string()
      .min(PASSWORD_MIN_LENGTH, `Password must be at least ${PASSWORD_MIN_LENGTH} characters`)
      .refine(
        (value) => new TextEncoder().encode(value).length <= PASSWORD_MAX_BYTES,
        `Password must be at most ${PASSWORD_MAX_BYTES} bytes`
      ),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  });

type SetupFormData = z.infer<typeof setupSchema>;

export function SetupPage() {
  const { setup, isLoading, isAuthenticated, setupRequired, webSetup } = useAuthStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<SetupFormData>({
    resolver: zodResolver(setupSchema),
  });

  const password = watch('password', '');

  const onSubmit = async (data: SetupFormData) => {
    setIsSubmitting(true);
    setFormError(null);
    try {
      // On success setupRequired turns false and the redirect below takes over.
      await setup(data.username, data.password);
    } catch (err: unknown) {
      setFormError(getErrorMessage(err, 'Setup did not complete. Please try again.'));
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return <AuthCardSkeleton fields={3} />;
  }

  if (!setupRequired) {
    return <Navigate to={isAuthenticated ? '/generate' : '/login'} replace />;
  }

  if (!webSetup) {
    return (
      <AuthCard>
        <AuthHeader title="Set up Sketchmaker" description="This site has no account yet." />
        <p className="text-sm text-muted-foreground">
          On a public site, the account is created on the server, so nobody else can claim it first. Run this on the
          server, then come back and sign in:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-border bg-muted p-3 font-mono text-xs">
          sudo sketchmaker create-account
        </pre>
      </AuthCard>
    );
  }

  return (
    <AuthCard>
      <AuthHeader title="Set up Sketchmaker" description="Create your account to get started." />

      {formError && <FormAlert>{formError}</FormAlert>}

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
            disabled={isSubmitting}
            autoFocus
          />
          <FieldError id="username-error" message={errors.username?.message} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            placeholder="Create a password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? 'password-error password-rules' : 'password-rules'}
            {...register('password')}
            disabled={isSubmitting}
          />
          <FieldError id="password-error" message={errors.password?.message} />
          <PasswordChecklist
            id="password-rules"
            rules={[{ label: `At least ${PASSWORD_MIN_LENGTH} characters`, met: password.length >= PASSWORD_MIN_LENGTH }]}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">Confirm password</Label>
          <PasswordInput
            id="confirmPassword"
            autoComplete="new-password"
            placeholder="Type it again"
            aria-invalid={errors.confirmPassword ? true : undefined}
            aria-describedby={errors.confirmPassword ? 'confirm-error' : undefined}
            {...register('confirmPassword')}
            disabled={isSubmitting}
          />
          <FieldError id="confirm-error" message={errors.confirmPassword?.message} />
        </div>

        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Creating account
            </>
          ) : (
            'Create account'
          )}
        </Button>
      </form>
    </AuthCard>
  );
}
