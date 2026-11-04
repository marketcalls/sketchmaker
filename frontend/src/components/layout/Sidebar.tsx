import { Link, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  Image,
  FileImage,
  Wand2,
  Lightbulb,
  Shirt,
  Video,
  Eraser,
  Minimize2,
  Settings,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Film,
  Clapperboard,
  Subtitles,
  PenTool,
  AudioLines,
  Type,
  FolderOpen,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useUIStore } from '@/stores/uiStore';
import { studioEase } from '@/components/motion';

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
}

const createItems: NavItem[] = [
  { href: '/generate', label: 'Generate', icon: Image },
  { href: '/stories', label: 'Stories', icon: Film, badge: 'New' },
  { href: '/faceless', label: 'Faceless Studio', icon: Clapperboard, badge: 'New' },
  { href: '/motion-graphics', label: 'Motion Graphics', icon: Type, badge: 'New' },
  { href: '/subtitles', label: 'Subtitles', icon: Subtitles },
  { href: '/magix', label: 'Magix', icon: Wand2 },
  { href: '/logo', label: 'Logo', icon: PenTool },
  { href: '/explainer', label: 'Explainer', icon: Lightbulb },
  { href: '/virtual', label: 'Virtual Try-On', icon: Shirt },
  { href: '/motion-control', label: 'Motion Control', icon: Video },
  { href: '/lip-sync', label: 'Lip Sync', icon: AudioLines, badge: 'New' },
  { href: '/remove-bg', label: 'Remove BG', icon: Eraser },
  { href: '/reduce', label: 'Reduce', icon: Minimize2 },
];

const libraryItems: NavItem[] = [
  { href: '/gallery', label: 'My Gallery', icon: FileImage },
  { href: '/my-assets', label: 'My Assets', icon: FolderOpen },
];

const bottomNavItems: NavItem[] = [
  { href: '/usage', label: 'Usage', icon: BarChart3 },
  { href: '/settings', label: 'Settings', icon: Settings },
];

function SidebarLink({
  item,
  active,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      to={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      title={collapsed ? item.label : undefined}
      className={cn(
        'relative flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active ? 'text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
        collapsed && 'justify-center px-2'
      )}
    >
      {active && (
        <motion.span
          layoutId="sidebar-active"
          transition={{ duration: 0.2, ease: studioEase }}
          className="absolute inset-0 rounded-md bg-accent"
          aria-hidden="true"
        />
      )}
      <item.icon className={cn('relative z-10 h-[18px] w-[18px] shrink-0', !collapsed && 'mr-3', active && 'text-primary')} />
      {!collapsed && (
        <>
          <span className="relative z-10">{item.label}</span>
          {item.badge && (
            <span className="relative z-10 ml-auto text-[10px] font-medium text-primary/80">
              {item.badge}
            </span>
          )}
        </>
      )}
    </Link>
  );
}

function SectionLabel({ children, collapsed }: { children: string; collapsed: boolean }) {
  if (collapsed) return <div className="mx-auto my-2 h-px w-6 bg-border" />;
  return (
    <p className="px-3 pb-1 pt-4 text-xs font-medium text-muted-foreground/80 first:pt-1">
      {children}
    </p>
  );
}

export function Sidebar() {
  const location = useLocation();
  const { sidebarOpen, sidebarCollapsed, setSidebarCollapsed, setSidebarOpen } = useUIStore();

  const isActive = (href: string) =>
    location.pathname === href || location.pathname.startsWith(href + '/');

  const renderItems = (items: NavItem[]) =>
    items.map((item) => (
      <SidebarLink
        key={item.href}
        item={item}
        active={isActive(item.href)}
        collapsed={sidebarCollapsed}
        onNavigate={() => setSidebarOpen(false)}
      />
    ));

  return (
    <>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-background/70 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] border-r border-border/70 bg-background transition-[width,transform] duration-200',
          sidebarCollapsed ? 'w-16' : 'w-64',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
      >
        <div className="flex h-full flex-col">
          <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
            <SectionLabel collapsed={sidebarCollapsed}>Studio</SectionLabel>
            {renderItems(createItems)}
            <SectionLabel collapsed={sidebarCollapsed}>Library</SectionLabel>
            {renderItems(libraryItems)}
          </nav>

          <div className="border-t border-border/70 p-2">
            {renderItems(bottomNavItems)}
          </div>

          {/* Collapse toggle */}
          <div className="hidden border-t border-border/70 p-2 md:flex">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className={cn('w-full', sidebarCollapsed && 'px-2')}
            >
              {sidebarCollapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <>
                  <ChevronLeft className="mr-2 h-4 w-4" />
                  Collapse
                </>
              )}
            </Button>
          </div>
        </div>
      </aside>
    </>
  );
}
