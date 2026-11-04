import { Outlet, useLocation } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { MissingKeysBanner } from '@/components/common/MissingKeysBanner';
import { MediaNotice } from '@/components/media/MediaNotice';
import { PageTransition } from '@/components/motion';
import { SEO } from '@/components/SEO';
import { useUIStore } from '@/stores/uiStore';
import { cn } from '@/lib/utils';
import { VERSION, APP_INFO } from '@/version';

export function MainLayout() {
  const { sidebarCollapsed } = useUIStore();
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* The tab title for pages that do not set their own. */}
      <SEO />
      <Navbar />
      {/* Beside the sidebar, not under it, or the start of the message is hidden. */}
      <div className={cn('transition-[margin] duration-200', sidebarCollapsed ? 'md:ml-16' : 'md:ml-64')}>
        <MissingKeysBanner />
      </div>
      <MediaNotice />
      <Sidebar />
      <main
        className={cn(
          'flex-1 transition-[margin] duration-200 pt-6 pb-10 px-4 md:px-8',
          sidebarCollapsed ? 'md:ml-16' : 'md:ml-64'
        )}
      >
        <div className="mx-auto max-w-7xl">
          <PageTransition key={location.pathname}>
            <Outlet />
          </PageTransition>
        </div>
      </main>
      <footer
        className={cn(
          'transition-[margin] duration-200 py-5 px-4 border-t border-border/70',
          sidebarCollapsed ? 'md:ml-16' : 'md:ml-64'
        )}
      >
        <div className="mx-auto max-w-7xl flex flex-col items-center gap-3 text-sm text-muted-foreground">
          <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
            <span className="text-sm font-medium text-foreground">{APP_INFO.name}</span>
            <span className="hidden sm:inline text-border">|</span>
            <span className="rounded-md border border-border px-1.5 py-0.5 font-mono text-[10px]">
              v{VERSION.full}
            </span>
            <span className="hidden sm:inline text-border">|</span>
            <span>{APP_INFO.copyright}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
