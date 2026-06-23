import { Skeleton } from "../../../components/ui/Skeleton";

export function RequestListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid gap-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="rounded-md border border-line bg-surface p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-7 w-32" />
          </div>
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}
