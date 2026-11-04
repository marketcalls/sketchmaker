import type { FacelessProject, PaidStep } from '@/api/faceless';
import { activeRun } from './stepState';

// Why a paid action is unavailable right now, or null. Keeps buttons honest
// up front.
export function usePaidGate(project: FacelessProject, step: PaidStep): string | null {
  if (!project.script) return 'Draft a script first';
  if (project.compliance?.blocked) return 'Resolve the blocking compliance flag first';
  if (activeRun(project, 'script')) return 'Wait for the script draft to finish';
  if (activeRun(project, step)) return 'Already running';
  return null;
}
