import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';

interface TablePaginationProps {
  page: number;
  totalPages: number;
  /** Total number of rows; shows "1 to 25 of 240" when given with pageSize. */
  total?: number;
  pageSize?: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  disabled?: boolean;
  className?: string;
}

/** Calm pagination row placed under a table, inside the same frame. */
export function TablePagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100],
  disabled = false,
  className,
}: TablePaginationProps) {
  const pages = Math.max(1, totalPages);
  const showRange = total !== undefined && pageSize !== undefined && total > 0;
  const from = showRange ? (page - 1) * pageSize! + 1 : 0;
  const to = showRange ? Math.min(page * pageSize!, total!) : 0;

  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-t border-border px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between',
        className
      )}
    >
      <div className="flex items-center gap-3">
        {onPageSizeChange && pageSize !== undefined && (
          <div className="flex items-center gap-2">
            <span className="text-xs">Rows</span>
            <Select value={String(pageSize)} onValueChange={(v) => onPageSizeChange(Number(v))}>
              <SelectTrigger className="h-8 w-[76px] text-xs" aria-label="Rows per page">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {pageSizeOptions.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {showRange && (
          <span className="tabular text-xs">
            {from.toLocaleString()} to {to.toLocaleString()} of {total!.toLocaleString()}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="w-8 px-0"
          aria-label="First page"
          disabled={page <= 1 || disabled}
          onClick={() => onPageChange(1)}
        >
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="w-8 px-0"
          aria-label="Previous page"
          disabled={page <= 1 || disabled}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular px-2 text-xs">
          Page {page} of {pages}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="w-8 px-0"
          aria-label="Next page"
          disabled={page >= pages || disabled}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="w-8 px-0"
          aria-label="Last page"
          disabled={page >= pages || disabled}
          onClick={() => onPageChange(pages)}
        >
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
