import * as React from "react"

import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"

type TableDensity = "default" | "compact"

interface TableContextValue {
  stickyHeader: boolean
  density: TableDensity
}

const TableContext = React.createContext<TableContextValue>({
  stickyHeader: false,
  density: "default",
})

export interface TableProps extends React.HTMLAttributes<HTMLTableElement> {
  /** Classes for the scrolling wrapper (for example a max height). */
  containerClassName?: string
  /**
   * Keep the header row visible while the rows scroll. The wrapper becomes
   * the scroll container with a default max height of 70vh; override it
   * with containerClassName.
   */
  stickyHeader?: boolean
  /** "compact" tightens row height for dense admin tables. */
  density?: TableDensity
}

const Table = React.forwardRef<HTMLTableElement, TableProps>(
  (
    { className, containerClassName, stickyHeader = false, density = "default", ...props },
    ref
  ) => (
    <TableContext.Provider value={{ stickyHeader, density }}>
      <div
        className={cn(
          "relative w-full overflow-auto",
          stickyHeader && "max-h-[70vh]",
          containerClassName
        )}
      >
        <table
          ref={ref}
          className={cn("w-full caption-bottom text-sm", className)}
          {...props}
        />
      </div>
    </TableContext.Provider>
  )
)
Table.displayName = "Table"

const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead
    ref={ref}
    className={cn("[&_tr]:border-b [&_tr]:hover:bg-transparent", className)}
    {...props}
  />
))
TableHeader.displayName = "TableHeader"

const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props}
  />
))
TableBody.displayName = "TableBody"

const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn(
      "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
      className
    )}
    {...props}
  />
))
TableFooter.displayName = "TableFooter"

const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b border-border transition-colors duration-150 hover:bg-accent/40 data-[state=selected]:bg-accent/60",
      className
    )}
    {...props}
  />
))
TableRow.displayName = "TableRow"

const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => {
  const { stickyHeader, density } = React.useContext(TableContext)
  return (
    <th
      ref={ref}
      className={cn(
        "text-left align-middle text-xs font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
        density === "compact" ? "h-9 px-3" : "h-10 px-4",
        // Borders on a collapsed table scroll away with the rows, so the
        // sticky header draws its own hairline.
        stickyHeader &&
          "sticky top-0 z-10 bg-card shadow-[inset_0_-1px_0_var(--color-border)]",
        className
      )}
      {...props}
    />
  )
})
TableHead.displayName = "TableHead"

const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => {
  const { density } = React.useContext(TableContext)
  return (
    <td
      ref={ref}
      className={cn(
        "align-middle [&:has([role=checkbox])]:pr-0",
        density === "compact" ? "px-3 py-2" : "px-4 py-3",
        className
      )}
      {...props}
    />
  )
})
TableCell.displayName = "TableCell"

const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn("mt-4 text-sm text-muted-foreground", className)}
    {...props}
  />
))
TableCaption.displayName = "TableCaption"

interface TableLoadingRowsProps {
  /** Number of columns, so each placeholder row spans the real layout. */
  columns: number
  rows?: number
}

/** Skeleton rows shown inside the table frame while data loads. */
function TableLoadingRows({ columns, rows = 5 }: TableLoadingRowsProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <TableRow key={r} aria-hidden="true" className="hover:bg-transparent">
          {Array.from({ length: columns }).map((_, c) => (
            <TableCell key={c}>
              <Skeleton className={cn("h-4", c === 0 ? "w-3/4" : "w-1/2")} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}

interface TableEmptyRowProps {
  columns: number
  children: React.ReactNode
  className?: string
}

/** A single full-width row for "nothing here" messages inside the table frame. */
function TableEmptyRow({ columns, children, className }: TableEmptyRowProps) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell
        colSpan={columns}
        className={cn("py-10 text-center text-sm text-muted-foreground", className)}
      >
        {children}
      </TableCell>
    </TableRow>
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
  TableLoadingRows,
  TableEmptyRow,
}
