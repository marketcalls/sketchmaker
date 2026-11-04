import { Link } from 'react-router-dom';
import { Clapperboard, Coins, MoreVertical, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { formatRelativeTime } from '@/lib/dateUtils';
import { formatUsd } from '@/stores/pricingStore';
import type { FacelessTemplate, ProjectSummary } from '@/api/faceless';
import { AspectGlyph, ProjectStatusBadge, formatDuration } from './shared';

// Estimated USD a project has used across its steps.
export function projectSpend(project: Pick<ProjectSummary, 'usd_by_step'>): number {
  return Object.values(project.usd_by_step ?? {}).reduce((n, v) => n + (Number(v) || 0), 0);
}

export function ProjectCard({
  project,
  template,
  seriesName,
  onDelete,
}: {
  project: ProjectSummary;
  template?: FacelessTemplate;
  seriesName?: string;
  onDelete?: (p: ProjectSummary) => void;
}) {
  const vertical = project.aspect === '9:16' || project.aspect === '4:5';
  const spent = projectSpend(project);
  return (
    <article className="relative flex overflow-hidden rounded-xl border border-border bg-card shadow-card transition-colors duration-150 hover:border-foreground/20">
      <Link
        to={`/faceless/projects/${project.id}`}
        className="flex min-w-0 flex-1 gap-3 p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <div
          className={
            vertical
              ? 'relative aspect-[9/16] w-20 shrink-0 overflow-hidden rounded-lg bg-secondary/50'
              : 'relative aspect-video w-32 shrink-0 self-start overflow-hidden rounded-lg bg-secondary/50'
          }
        >
          {project.thumbnail_url ? (
            <img
              src={project.thumbnail_url}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="flex h-full w-full flex-col items-center justify-center gap-1">
              <Clapperboard
                className={project.status === 'rendered' ? 'h-6 w-6 text-muted-foreground' : 'h-6 w-6 text-muted-foreground/40'}
                aria-hidden="true"
              />
              {project.scene_count > 0 && (
                <span className="font-mono text-[10px] tabular text-muted-foreground">{project.scene_count} sc</span>
              )}
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1 py-0.5">
          <div className="mb-1.5">
            <ProjectStatusBadge status={project.status} />
          </div>
          <h3 className="line-clamp-2 text-base font-semibold leading-tight">{project.title || 'Untitled project'}</h3>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {template?.name ?? project.template_id}
            {seriesName && (
              <>
                {' '}/ {seriesName}
              </>
            )}
          </p>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] tabular text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <AspectGlyph aspect={project.aspect} className="scale-75" />
              {project.aspect}
            </span>
            <span>{formatDuration(project.length_seconds)}</span>
            <span>{formatRelativeTime(project.updated_at)}</span>
            {spent > 0 && <span>{formatUsd(spent)} est.</span>}
          </p>
        </div>
      </Link>
      {onDelete && (
        <div className="p-1.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-9 w-9" aria-label={`Actions for ${project.title || 'project'}`}>
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => onDelete(project)}>
                <Trash2 className="mr-2 h-4 w-4" /> Delete project
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </article>
  );
}

export function SpendSummary({ projects }: { projects: ProjectSummary[] }) {
  const total = projects.reduce((n, p) => n + projectSpend(p), 0);
  return (
    <div className="panel flex items-center gap-4 rounded-xl p-4">
      <Coins className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted-foreground">Estimated spend</p>
        <p className="font-mono text-2xl font-medium tabular text-foreground">{formatUsd(total)}</p>
        <p className="text-xs text-muted-foreground">Across recent projects. Each paid step shows an estimate before it runs.</p>
      </div>
      <Button asChild variant="outline" size="sm">
        <Link to="/usage">Usage</Link>
      </Button>
    </div>
  );
}
