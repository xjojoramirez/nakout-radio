interface SkeletonProps {
  variant?: "title" | "field" | "row";
  className?: string;
}

export function Skeleton({ variant, className }: SkeletonProps) {
  const classes = ["skeleton"];
  if (variant) classes.push(`skeleton-${variant}`);
  if (className) classes.push(className);
  return <div aria-hidden="true" className={classes.join(" ")} />;
}

export function SkeletonForm({ count }: { count: number }) {
  return (
    <div className="skeleton-form" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} variant="field" />
      ))}
    </div>
  );
}

export function SkeletonList({ rows }: { rows: number }) {
  return (
    <ul className="skeleton-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <Skeleton variant="row" />
        </li>
      ))}
    </ul>
  );
}

function NowSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={1} />
      <SkeletonList rows={5} />
    </section>
  );
}

function PlaylistsSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={3} />
      <SkeletonList rows={4} />
    </section>
  );
}

function GenresSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={2} />
      <SkeletonList rows={4} />
    </section>
  );
}

function ScheduleSkeleton() {
  return (
    <section className="admin-panel" aria-hidden="true">
      <Skeleton variant="title" />
      <SkeletonForm count={4} />
      <SkeletonList rows={3} />
    </section>
  );
}

export function PanelSkeleton({ tab }: { tab: string }) {
  switch (tab) {
    case "now":
      return <NowSkeleton />;
    case "playlists":
      return <PlaylistsSkeleton />;
    case "genres":
      return <GenresSkeleton />;
    case "schedule":
      return <ScheduleSkeleton />;
    default:
      return <section className="admin-panel" aria-hidden="true" />;
  }
}
