import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { clearAccessToken, setAccessToken, staffRequest } from "../../lib/api";
import { ThemeToggle } from "../../components/ThemeToggle";
import { ApiClientsPanel } from "./ApiClientsPanel";
import { DirectLoans } from "./DirectLoans";
import {
  AuditLog,
  BulkImport,
  Inventory,
  OperationsReports,
  Panel,
  PrintingPanel,
  QrTools,
  Queues,
  StocktakePanel,
  StockTransferPanel,
  Users,
  type Makerspace,
  useStaffGet,
} from "./StaffPanels";

type AuthUser = {
  username: string;
  role: string;
  makerspaces: { id: number; slug: string; role: string }[];
};

export function StaffApp({ guestOnly = false }: { guestOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState("queues");
  const login = useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      staffRequest<{ access: string; user: AuthUser }>("/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setAccessToken(data.access);
      setUser(data.user);
      setSelected(data.user.makerspaces[0]?.id ?? null);
    },
  });

  const makerspaces = useStaffGet<Makerspace[]>(
    ["staff", "makerspaces"],
    "/admin/makerspaces",
    Boolean(user),
  );
  const activeMakerspace = useMemo(
    () => makerspaces.data?.find((item) => item.id === selected),
    [makerspaces.data, selected],
  );

  if (!user) {
    return (
      <LoginPanel
        error={login.error?.message}
        guestOnly={guestOnly}
        onSubmit={login.mutate}
      />
    );
  }

  return (
    <main className="desk-shell grid lg:grid-cols-[260px_1fr]">
      <aside className="border-b border-line bg-panel lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-black text-bg">
            MI
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">Makerspace Desk</p>
            <p className="text-xs text-muted">{guestOnly ? "Guest admin" : "Space Manager"}</p>
          </div>
        </div>
        <div className="p-4">
          <select
            className="desk-input w-full"
            value={selected ?? ""}
            onChange={(event) => setSelected(Number(event.target.value))}
          >
            {makerspaces.data?.map((makerspace) => (
              <option key={makerspace.id} value={makerspace.id}>
                {makerspace.name}
              </option>
            ))}
          </select>
          <nav className="mt-4 grid gap-1">
            {["queues", "direct", "inventory", "printing", "transfers", "stocktake", "reports", "bulk", "qr", "api", "users", "audit"].map((item) => (
              <button
                key={item}
                className={`rounded-md px-3 py-2 text-left text-sm font-medium transition ${
                  tab === item
                    ? "bg-accent text-bg"
                    : "text-muted hover:bg-surface hover:text-ink"
                }`}
                onClick={() => setTab(item)}
              >
                  {item === "qr" ? "QR Tools" : item === "direct" ? "Direct handout" : item === "api" ? "API clients" : item === "stocktake" ? "Stocktake" : item === "printing" ? "3D Printing" : item[0].toUpperCase() + item.slice(1)}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <section className="min-w-0">
        <header className="border-b border-line bg-bg/95 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                {activeMakerspace?.public_code ?? activeMakerspace?.slug ?? "No workspace"}
              </p>
              <h1 className="text-2xl font-bold text-ink">
                {activeMakerspace?.name ?? "Inventory Control"}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">
                {user.username}
              </span>
              <ThemeToggle />
              <button
                className="desk-button"
                onClick={() => {
                  clearAccessToken();
                  setUser(null);
                  queryClient.clear();
                }}
              >
                Sign out
              </button>
            </div>
          </div>
        </header>

        <div className="min-w-0 p-5">
          {!activeMakerspace ? <Panel title="No makerspace">Assign a makerspace to this account.</Panel> : null}
          {activeMakerspace && tab === "queues" ? (
            <Queues makerspace={activeMakerspace} guestOnly={guestOnly} />
          ) : null}
          {activeMakerspace && tab === "inventory" ? (
            <Inventory makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "printing" ? (
            <PrintingPanel makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "transfers" ? (
            <StockTransferPanel makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "stocktake" ? (
            <StocktakePanel makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "reports" ? (
            <OperationsReports makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "direct" ? (
            <DirectLoans makerspace={activeMakerspace} />
          ) : null}
          {activeMakerspace && tab === "bulk" ? <BulkImport makerspace={activeMakerspace} /> : null}
          {activeMakerspace && tab === "qr" ? <QrTools makerspace={activeMakerspace} /> : null}
          {activeMakerspace && tab === "api" ? <ApiClientsPanel makerspace={activeMakerspace} /> : null}
          {activeMakerspace && tab === "users" ? <Users /> : null}
          {activeMakerspace && tab === "audit" ? <AuditLog /> : null}
        </div>
      </section>
    </main>
  );
}

function LoginPanel({
  error,
  guestOnly,
  onSubmit,
}: {
  error?: string;
  guestOnly: boolean;
  onSubmit: (payload: { username: string; password: string }) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return (
    <main className="desk-shell grid place-items-center px-5">
      <form
        className="desk-panel w-full max-w-md p-6"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ username, password });
        }}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-accent">
          {guestOnly ? "Guest admin desk" : "Space Manager desk"}
        </p>
        <h1 className="mt-2 text-2xl font-bold text-ink">Sign in</h1>
        <p className="mt-2 text-sm text-muted">
          Use your staff account to manage requests, inventory, and handovers.
        </p>
        <label className="mt-5 block text-sm font-semibold">Username</label>
        <input className="desk-input mt-1 w-full" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label className="mt-3 block text-sm font-semibold">Password</label>
        <input className="desk-input mt-1 w-full" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
        <button className="desk-button-primary mt-5 w-full">
          Sign in
        </button>
      </form>
    </main>
  );
}
