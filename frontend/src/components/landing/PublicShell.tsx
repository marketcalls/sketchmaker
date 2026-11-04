import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/stores/authStore';

const navLink =
  'rounded-sm transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background';

const footerStudios = [
  { href: '/faceless', label: 'Faceless Studio' },
  { href: '/motion-graphics', label: 'Motion Graphics' },
  { href: '/stories', label: 'Video Stories' },
  { href: '/logo', label: 'Logo Studio' },
  { href: '/lip-sync', label: 'Lip Sync' },
];

const footerTools = [
  { href: '/generate', label: 'Image Generation' },
  { href: '/magix', label: 'Magix Photography' },
  { href: '/virtual', label: 'Virtual Try-On' },
  { href: '/motion-control', label: 'Motion Control' },
  { href: '/explainer', label: 'Visual Explainers' },
  { href: '/subtitles', label: 'Auto Subtitles' },
  { href: '/remove-bg', label: 'Background Removal' },
];

/** Top bar for the home page. Fixed: the page leaves room for it. A signed-in
 * visitor gets a way into the studio instead of the login buttons. */
export function PublicHeader() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-border bg-background/95">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/" className={`flex items-center gap-2 ${navLink}`}>
          <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
          <span className="font-display text-xl leading-none tracking-tight sm:text-2xl">Sketchmaker</span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex" aria-label="Main">
          {/* A plain anchor so the page scrolls to the section without a reload. */}
          <a href="/#studio" className={navLink}>Studio</a>
        </nav>
        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <Button size="sm" asChild>
              <Link to="/generate">Open studio</Link>
            </Button>
          ) : (
            <>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/login">Login</Link>
              </Button>
              <Button size="sm" asChild>
                <Link to="/login">Get started</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

/** Four-column footer for the home page. */
export function PublicFooter() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const currentYear = new Date().getFullYear();

  return (
    <footer className="relative z-10 border-t border-border px-4 py-12">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 grid gap-10 md:grid-cols-4">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
              <span className="font-display text-xl tracking-tight">Sketchmaker</span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              One studio for faceless video, motion graphics, logos and images.
            </p>
          </div>

          <div>
            <h4 className="mb-3 text-sm font-medium text-foreground">Product</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><a href="/#studio" className={navLink}>Studio</a></li>
              <li>
                {isAuthenticated ? (
                  <Link to="/generate" className={navLink}>Open studio</Link>
                ) : (
                  <Link to="/login" className={navLink}>Login</Link>
                )}
              </li>
            </ul>
          </div>

          <div>
            <h4 className="mb-3 text-sm font-medium text-foreground">Studios</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {footerStudios.map((item) => (
                <li key={item.href}><Link to={item.href} className={navLink}>{item.label}</Link></li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="mb-3 text-sm font-medium text-foreground">Tools</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {footerTools.map((item) => (
                <li key={item.href}><Link to={item.href} className={navLink}>{item.label}</Link></li>
              ))}
            </ul>
          </div>
        </div>

        <div className="border-t border-border pt-6 text-center">
          <p className="text-sm text-muted-foreground">
            &copy; {currentYear} Sketchmaker. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
