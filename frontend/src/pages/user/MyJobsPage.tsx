import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Image, Video, Clock, CheckCircle, CircleDot, XCircle, Loader2, RefreshCw, RotateCcw, Film, Captions, AudioLines, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { useJobsStore, type Job } from '@/stores/jobsStore';
import { cn } from '@/lib/utils';
import { SEO } from '@/components/SEO';
import { formatLocalDateTime } from '@/lib/dateUtils';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { apiClient } from '@/api/client';
import { friendlyError, getErrorMessage } from '@/utils/errors';

function JobCard({
  job,
  onRetry,
  onCancel,
}: {
  job: Job;
  onRetry: (jobId: string, jobType: 'video' | 'lipsync') => Promise<void>;
  onCancel: (jobId: string) => Promise<void>;
}) {
  const [isRetrying, setIsRetrying] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  // A job is "stuck" if it's completed but has no result (scheduler didn't process it)
  const isStuck = job.status === 'completed' && !job.resultId;
  // Only video and lip sync jobs have a retry route.
  const canRetry = (job.status === 'failed' || isStuck) && (job.jobType === 'video' || job.jobType === 'lipsync');
  const canCancel = job.status === 'pending' || job.status === 'in_progress';

  const handleCancel = async () => {
    setCancelError(null);
    try {
      await onCancel(job.jobId);
    } catch (err) {
      setCancelError(getErrorMessage(err, 'This job could not be cancelled.'));
    }
  };

  const handleRetry = async () => {
    if (job.jobType !== 'video' && job.jobType !== 'lipsync') return;
    setIsRetrying(true);
    try {
      await onRetry(job.jobId, job.jobType);
    } finally {
      setIsRetrying(false);
    }
  };

  const getStatusIcon = () => {
    switch (job.status) {
      case 'pending':
        return <Clock className="h-4 w-4 text-warning" />;
      case 'in_progress':
        return <CircleDot className="h-4 w-4 text-warning" />;
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-success" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-destructive" />;
    }
  };

  const getStatusBadge = () => {
    // Show "Stuck" badge for completed jobs without results
    if (isStuck) {
      return <Badge variant="warning">Stuck</Badge>;
    }

    const variants: Record<Job['status'], 'warning' | 'success' | 'destructive'> = {
      pending: 'warning',
      in_progress: 'warning',
      completed: 'success',
      failed: 'destructive',
    };
    const labels: Record<Job['status'], string> = {
      pending: 'Queued',
      in_progress: 'Generating',
      completed: 'Completed',
      failed: 'Failed',
    };
    return <Badge variant={variants[job.status]}>{labels[job.status]}</Badge>;
  };

  const linkTo = job.status === 'completed' && job.resultId ? '/gallery' : undefined;

  const getJobIcon = () => {
    switch (job.jobType) {
      case 'image':
        return <Image className="h-8 w-8 text-muted-foreground" />;
      case 'video':
        return <Video className="h-8 w-8 text-muted-foreground" />;
      case 'story':
        return <Film className="h-8 w-8 text-muted-foreground" />;
      case 'subtitle':
        return <Captions className="h-8 w-8 text-muted-foreground" />;
      case 'lipsync':
        return <AudioLines className="h-8 w-8 text-muted-foreground" />;
    }
  };

  const getJobLabel = () => {
    switch (job.jobType) {
      case 'image':
        return 'Image';
      case 'video':
        return 'Video';
      case 'story':
        return 'Story';
      case 'subtitle':
        return 'Subtitle';
      case 'lipsync':
        return 'Lip Sync';
    }
  };


  return (
    <Card className="overflow-hidden transition-colors duration-150 hover:bg-accent/40">
      <div className="flex">
        {/* Thumbnail or placeholder */}
        <div className="w-20 h-20 sm:w-24 sm:h-24 bg-muted flex items-center justify-center flex-shrink-0">
          {job.thumbnailUrl ? (
            <img src={job.thumbnailUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            getJobIcon()
          )}
        </div>

        {/* Content */}
        <div className="flex-1 p-3 sm:p-4 min-w-0">
          <div className="flex items-center justify-between mb-2 gap-2">
            <div className="flex items-center gap-2 min-w-0">
              {getStatusIcon()}
              <span className="text-sm font-medium truncate">
                {getJobLabel()} generation
              </span>
            </div>
            {getStatusBadge()}
          </div>

          {job.prompt && (
            <p className="text-sm text-muted-foreground line-clamp-1 mb-2">
              {job.prompt}
            </p>
          )}

          {(job.status === 'in_progress' || job.status === 'pending') && (
            <Progress value={job.progress} className="h-1.5 mb-2" />
          )}

          {job.error && (
            <p className="text-sm text-destructive line-clamp-1 mb-2">{friendlyError(job.error, 'This job failed.')}</p>
          )}

          {cancelError && (
            <p className="text-sm text-destructive line-clamp-1 mb-2">{cancelError}</p>
          )}

          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-xs tabular text-muted-foreground">
              {formatLocalDateTime(job.createdAt, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
            <div className="flex gap-2">
              {canCancel && (
                <Button variant="outline" size="sm" onClick={() => setConfirmCancel(true)}>
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              )}
              {canRetry && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRetry}
                  disabled={isRetrying}
                >
                  {isRetrying ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Retrying
                    </>
                  ) : (
                    <>
                      <RotateCcw className="h-4 w-4" />
                      Retry
                    </>
                  )}
                </Button>
              )}
              {linkTo && (
                <Button variant="outline" size="sm" asChild>
                  <Link to={linkTo}>View</Link>
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title="Cancel job"
        description="This job stops being tracked and is marked as failed. Work already sent to the provider may still finish and be billed."
        confirmText="Cancel job"
        cancelText="Keep job"
        variant="destructive"
        onConfirm={handleCancel}
      />
    </Card>
  );
}

export function MyJobsPage() {
  const {
    jobs,
    pendingCount,
    inProgressCount,
    isLoading,
    filter,
    typeFilter,
    fetchJobs,
    setFilter,
    setTypeFilter,
    startPolling,
    stopPolling,
    retryJob,
  } = useJobsStore();

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const activeJobsCount = pendingCount + inProgressCount;

  const cancelJob = async (jobId: string) => {
    await apiClient.post(`/jobs/${encodeURIComponent(jobId)}/cancel`);
    await fetchJobs(true);
  };

  return (
    <>
      <SEO
        title="My Jobs"
        description="Track your image and video generation jobs"
      />
      <div className="space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-balance text-2xl font-semibold tracking-tight">My jobs</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Track images, videos, stories, subtitles and lip sync while they generate.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => fetchJobs(true)}
            disabled={isLoading}
            className="w-full sm:w-auto"
          >
            <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
            {isLoading ? 'Refreshing' : 'Refresh'}
          </Button>
        </header>

        {/* Active jobs status line */}
        {activeJobsCount > 0 && (
          <div
            role="status"
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-border bg-card px-4 py-3 text-sm"
          >
            <span className="font-medium">
              {activeJobsCount} job{activeJobsCount > 1 ? 's' : ''} in progress
            </span>
            <span className="text-xs text-muted-foreground">
              This list refreshes every 30 seconds.
            </span>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col gap-4 sm:flex-row">
          <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="all" className="flex-1 sm:flex-none">All</TabsTrigger>
              <TabsTrigger value="pending" className="flex-1 sm:flex-none">Pending</TabsTrigger>
              <TabsTrigger value="completed" className="flex-1 sm:flex-none">Completed</TabsTrigger>
              <TabsTrigger value="failed" className="flex-1 sm:flex-none">Failed</TabsTrigger>
            </TabsList>
          </Tabs>

          <Tabs value={typeFilter} onValueChange={(v) => setTypeFilter(v as typeof typeFilter)}>
            <TabsList className="w-full sm:w-auto flex-wrap">
              <TabsTrigger value="all" className="flex-1 sm:flex-none">All</TabsTrigger>
              <TabsTrigger value="image" className="flex-1 sm:flex-none">Images</TabsTrigger>
              <TabsTrigger value="video" className="flex-1 sm:flex-none">Videos</TabsTrigger>
              <TabsTrigger value="story" className="flex-1 sm:flex-none">Stories</TabsTrigger>
              <TabsTrigger value="subtitle" className="flex-1 sm:flex-none">Subtitles</TabsTrigger>
              <TabsTrigger value="lipsync" className="flex-1 sm:flex-none">Lip Sync</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Jobs list */}
        <div className="space-y-3" aria-busy={isLoading && jobs.length === 0}>
          {isLoading && jobs.length === 0 ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="overflow-hidden">
                <div className="flex">
                  <Skeleton className="h-20 w-20 shrink-0 rounded-none sm:h-24 sm:w-24" />
                  <div className="flex-1 space-y-2 p-3 sm:p-4">
                    <div className="flex items-center justify-between gap-2">
                      <Skeleton className="h-4 w-36" />
                      <Skeleton className="h-5 w-16" />
                    </div>
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                </div>
              </Card>
            ))
          ) : jobs.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Clock className="mx-auto mb-3 h-6 w-6 text-muted-foreground" aria-hidden="true" />
                <p className="text-base font-semibold">No jobs found</p>
                <p className="mb-4 mt-1 text-sm text-muted-foreground">
                  Jobs you start appear here while they run.
                </p>
                <div className="flex flex-col sm:flex-row gap-3 justify-center flex-wrap">
                  <Button asChild>
                    <Link to="/generate">Generate image</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/motion-control">Create video</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/stories">Create story</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/subtitles">Add subtitles</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/lip-sync">Lip sync</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            jobs.map((job) => <JobCard key={job.jobId} job={job} onRetry={retryJob} onCancel={cancelJob} />)
          )}
        </div>

        {/* Info text */}
        {jobs.length > 0 && (
          <p className="text-center text-xs text-muted-foreground">
            Showing jobs from the last 7 days. Completed jobs are saved to your gallery.
          </p>
        )}
      </div>
    </>
  );
}

export default MyJobsPage;
