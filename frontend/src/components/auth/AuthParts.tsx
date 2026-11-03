import * as React from 'react';
import { Check, Eye, EyeOff, Circle } from 'lucide-react';
import { Input, type InputProps } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/** The card every auth screen sits in. */
export function AuthCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('panel space-y-6 rounded-xl p-6 sm:p-8', className)}>{children}</div>;
}

export function AuthHeader({ title, description }: { title: string; description?: React.ReactNode }) {
  return (
    <div className="space-y-1.5 text-center">
      <h1 className="text-balance text-xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="text-pretty text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}

/** Form-level message: an error from the server, or a confirmation. */
export function FormAlert({
  children,
  tone = 'error',
}: {
  children: React.ReactNode;
  tone?: 'error' | 'success';
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'rounded-md border p-3 text-sm',
        tone === 'error'
          ? 'border-destructive/30 bg-destructive/10 text-destructive'
          : 'border-success/30 bg-success/10 text-success',
      )}
    >
      {children}
    </div>
  );
}

/** Inline error under a field. Pair the id with the input's aria-describedby. */
export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-destructive">
      {message}
    </p>
  );
}

/** Password field with a show or hide toggle that keeps the field's size. */
export const PasswordInput = React.forwardRef<HTMLInputElement, Omit<InputProps, 'type'>>(
  ({ className, disabled, ...props }, ref) => {
    const [visible, setVisible] = React.useState(false);
    return (
      <div className="relative">
        <Input
          ref={ref}
          type={visible ? 'text' : 'password'}
          className={cn('pr-10', className)}
          disabled={disabled}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          disabled={disabled}
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = 'PasswordInput';

/** Password rules, always shown so the form does not grow while typing. */
export function PasswordChecklist({ rules, id }: { rules: { label: string; met: boolean }[]; id?: string }) {
  return (
    <ul id={id} className="grid gap-1 pt-1 sm:grid-cols-2" aria-label="Password requirements">
      {rules.map((rule) => (
        <li
          key={rule.label}
          className={cn(
            'flex items-center gap-1.5 text-xs transition-colors duration-150',
            rule.met ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          {rule.met ? (
            <Check className="h-3 w-3 shrink-0 text-success" aria-hidden="true" />
          ) : (
            <Circle className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
          )}
          <span>
            {rule.label}
            <span className="sr-only">{rule.met ? ', done' : ', not yet'}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Placeholder in the shape of an auth card while its settings load. */
export function AuthCardSkeleton({ fields = 2 }: { fields?: number }) {
  return (
    <AuthCard>
      <div className="flex flex-col items-center gap-2" aria-hidden="true">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-56" />
      </div>
      <div className="space-y-3" aria-hidden="true">
        {Array.from({ length: fields }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
      <span className="sr-only">Loading</span>
    </AuthCard>
  );
}
