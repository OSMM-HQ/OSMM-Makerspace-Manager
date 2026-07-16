import { Link } from "react-router-dom";

import { OsmmHomeLink, OsmmLogo } from "../../components/OsmmLogo";
import { SiteFooter } from "../../components/SiteFooter";
import { ThemeToggle } from "../../components/ThemeToggle";
import { Card } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import {
  usePublicRoadmap,
  type PublicRoadmapItem,
} from "./roadmapApi";

type RoadmapStatus = PublicRoadmapItem["status"];

const STATUS_GROUPS: {
  status: RoadmapStatus;
  label: string;
  description: string;
  tone: string;
}[] = [
  {
    status: "shipped",
    label: "Shipped",
    description: "Available in the platform now.",
    tone: "border-emerald-200 bg-emerald-50 text-emerald-950",
  },
  {
    status: "in_progress",
    label: "In progress",
    description: "Actively being designed and built.",
    tone: "border-sky-200 bg-sky-50 text-sky-950",
  },
  {
    status: "planned",
    label: "Planned",
    description: "Ideas accepted for future work.",
    tone: "border-violet-200 bg-violet-50 text-violet-950",
  },
];

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
});

export function RoadmapPage() {
  const roadmapQuery = usePublicRoadmap();
  const items = roadmapQuery.data ?? [];

  return (
    <main className="desk-shell flex min-h-screen flex-col">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <OsmmHomeLink className="items-center gap-3 text-ink">
            <OsmmLogo className="shrink-0" size={36} />
            <div className="min-w-0">
              <p className="text-sm font-semibold">OSMM</p>
              <p className="text-xs text-muted">Public roadmap</p>
            </div>
          </OsmmHomeLink>
          <nav aria-label="Public navigation" className="flex flex-wrap items-center gap-2">
            <Link className="desk-button" to="/">
              Catalog
            </Link>
            <ThemeToggle />
            <Link className="desk-button" to="/admin">
              Staff login
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto w-full max-w-7xl flex-1 px-5 py-8">
        <div className="max-w-3xl">
          <h1 className="text-3xl font-bold text-ink sm:text-4xl">
            Roadmap and changelog
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
            Follow what has shipped, what we are building, and what is planned
            for the makerspace platform.
          </p>
        </div>

        {roadmapQuery.isLoading ? <RoadmapLoading /> : null}

        {roadmapQuery.isError ? (
          <Card className="mt-8 max-w-xl">
            <h2 className="text-xl font-semibold text-ink">
              Roadmap unavailable
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              The public roadmap could not be loaded. Please try again.
            </p>
            <button
              className="desk-button-primary mt-4"
              disabled={roadmapQuery.isFetching}
              type="button"
              onClick={() => roadmapQuery.refetch()}
            >
              {roadmapQuery.isFetching ? "Retrying..." : "Retry"}
            </button>
          </Card>
        ) : null}

        {roadmapQuery.isSuccess && items.length === 0 ? (
          <Card className="mt-8 max-w-xl">
            <h2 className="text-xl font-semibold text-ink">
              The roadmap is taking shape
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Public plans and release notes will appear here when they are
              published.
            </p>
          </Card>
        ) : null}

        {items.length > 0 ? (
          <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-3">
            {STATUS_GROUPS.map((group) => (
              <RoadmapGroup
                key={group.status}
                group={group}
                items={items.filter((item) => item.status === group.status)}
              />
            ))}
          </div>
        ) : null}
      </section>

      <SiteFooter />
    </main>
  );
}

function RoadmapGroup({
  group,
  items,
}: {
  group: (typeof STATUS_GROUPS)[number];
  items: PublicRoadmapItem[];
}) {
  const headingId = `roadmap-${group.status}`;
  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-xl border p-4 ${group.tone}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold" id={headingId}>
            {group.label}
          </h2>
          <p className="mt-1 text-sm leading-5">{group.description}</p>
        </div>
        <span className="rounded-full border border-current/20 px-2.5 py-1 font-mono text-xs font-semibold">
          {group.label}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {items.length === 0 ? (
          <p className="rounded-lg border border-current/20 bg-white/60 px-3 py-5 text-sm">
            No {group.label.toLowerCase()} items yet.
          </p>
        ) : (
          items.map((item, index) => (
            <RoadmapEntry
              key={`${item.status}-${item.title}-${item.published_at ?? "undated"}-${index}`}
              item={item}
              statusLabel={group.label}
            />
          ))
        )}
      </div>
    </section>
  );
}

function RoadmapEntry({
  item,
  statusLabel,
}: {
  item: PublicRoadmapItem;
  statusLabel: string;
}) {
  return (
    <article className="rounded-lg bg-white/75 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-current/20 px-2 py-0.5 text-xs font-semibold">
          {statusLabel}
        </span>
        {item.category ? (
          <span className="font-mono text-xs">{item.category}</span>
        ) : null}
      </div>
      <h3 className="mt-3 text-lg font-semibold">{item.title}</h3>
      {item.published_at ? (
        <time
          className="mt-1 block text-xs"
          dateTime={item.published_at}
        >
          {dateFormatter.format(new Date(item.published_at))}
        </time>
      ) : null}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
        {item.description}
      </p>
    </article>
  );
}

function RoadmapLoading() {
  return (
    <div
      aria-live="polite"
      className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-3"
      role="status"
    >
      <span className="sr-only">Loading roadmap</span>
      {STATUS_GROUPS.map((group) => (
        <div className={`rounded-xl border p-4 ${group.tone}`} key={group.status}>
          <Skeleton className="h-7 w-32 motion-reduce:animate-none" />
          <Skeleton className="mt-3 h-4 w-48 motion-reduce:animate-none" />
          <Skeleton className="mt-5 h-36 w-full motion-reduce:animate-none" />
        </div>
      ))}
    </div>
  );
}
