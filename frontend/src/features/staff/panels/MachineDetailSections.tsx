import { useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addMachineErrorLog,
  addMachineOperator,
  addMachineUsage,
  collectionResults,
  deleteMachineDocument,
  deleteMachineOperator,
  getMachineDocumentUrl,
  getMachineDocuments,
  getMachineErrorLogs,
  getMachineOperators,
  getMachineUsage,
  machineKeys,
  uploadMachineDocument,
  type MachineAccessLevel,
} from "../machinesApi";

export function MachineDetailSections({ machineId, makerspaceId, canManage }: {
  machineId: number; makerspaceId: number; canManage: boolean;
}) {
  return (
    <>
      <OperatorsSection machineId={machineId} canManage={canManage} />
      <UsageSection machineId={machineId} makerspaceId={makerspaceId} />
      <DocumentsSection machineId={machineId} />
      <ErrorLogsSection machineId={machineId} />
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-t border-line pt-4"><h3 className="mb-3 text-sm font-semibold text-ink">{title}</h3>{children}</section>;
}

function OperatorsSection({ machineId, canManage }: { machineId: number; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [userId, setUserId] = useState("");
  const [accessLevel, setAccessLevel] = useState<MachineAccessLevel>("operate");
  const operators = useQuery({ queryKey: machineKeys.operators(machineId), queryFn: () => getMachineOperators(machineId) });
  const items = collectionResults(operators.data);
  const add = useMutation({
    mutationFn: () => addMachineOperator(machineId, { user_id: Number(userId), access_level: accessLevel }),
    onSuccess: async () => {
      setUserId("");
      await queryClient.invalidateQueries({ queryKey: machineKeys.operators(machineId) });
    },
  });
  const remove = useMutation({
    mutationFn: (userPk: number) => deleteMachineOperator(machineId, userPk),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: machineKeys.operators(machineId) }),
  });

  return (
    <Section title="Operators">
      {operators.isLoading ? <p className="text-sm text-muted">Loading operators...</p> : null}
      {operators.error instanceof Error ? <p className="text-sm text-danger">{operators.error.message}</p> : null}
      {!operators.isLoading && !operators.error && !items.length ? <p className="text-sm text-muted">No operators assigned.</p> : null}
      <div className="grid gap-2">
        {items.map((operator) => (
          <div key={operator.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-bg p-2 text-sm">
            <span className="font-medium text-ink">{operator.username}</span>
            <span className="text-muted">User #{operator.user} · {operator.access_level}</span>
            {canManage ? <button className="desk-button ml-auto" type="button" disabled={remove.isPending}
              onClick={() => remove.mutate(operator.user)}>Remove</button> : null}
          </div>
        ))}
      </div>
      {canManage ? (
        <form className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end"
          onSubmit={(event) => { event.preventDefault(); add.mutate(); }}>
          <label className="grid gap-1 text-xs font-semibold text-muted">User ID
            <input className="desk-input" type="number" min="1" value={userId} onChange={(event) => setUserId(event.target.value)} required />
          </label>
          <label className="grid gap-1 text-xs font-semibold text-muted">Access level
            <select className="desk-input" value={accessLevel} onChange={(event) => setAccessLevel(event.target.value as MachineAccessLevel)}>
              <option value="operate">Operate</option><option value="manage">Manage</option><option value="full">Full</option>
            </select>
          </label>
          <button className="desk-button-primary" type="submit" disabled={add.isPending || !userId}>{add.isPending ? "Adding..." : "Add"}</button>
        </form>
      ) : null}
      {add.error instanceof Error ? <p className="mt-2 text-sm text-danger">{add.error.message}</p> : null}
      {remove.error instanceof Error ? <p className="mt-2 text-sm text-danger">{remove.error.message}</p> : null}
    </Section>
  );
}

function UsageSection({ machineId, makerspaceId }: { machineId: number; makerspaceId: number }) {
  const queryClient = useQueryClient();
  const [hours, setHours] = useState("");
  const [note, setNote] = useState("");
  const usage = useQuery({ queryKey: machineKeys.usage(machineId), queryFn: () => getMachineUsage(machineId) });
  const items = collectionResults(usage.data);
  const add = useMutation({
    mutationFn: () => addMachineUsage(machineId, { hours, note: note.trim() }),
    onSuccess: async () => {
      setHours(""); setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: machineKeys.usage(machineId) }),
        queryClient.invalidateQueries({ queryKey: machineKeys.detail(machineId) }),
        queryClient.invalidateQueries({ queryKey: machineKeys.list(makerspaceId) }),
      ]);
    },
  });

  return (
    <Section title="Usage">
      {usage.isLoading ? <p className="text-sm text-muted">Loading usage...</p> : null}
      {usage.error instanceof Error ? <p className="text-sm text-danger">{usage.error.message}</p> : null}
      {!usage.isLoading && !usage.error && !items.length ? <p className="text-sm text-muted">No usage logged yet.</p> : null}
      <div className="grid gap-2">
        {items.map((entry) => (
          <div key={entry.id} className="rounded-md border border-line bg-bg p-2 text-sm">
            <div className="flex items-center justify-between gap-2"><strong className="text-ink">{entry.hours} h</strong><span className="text-xs text-muted">{formatDate(entry.created_at)}</span></div>
            {entry.note ? <p className="mt-1 break-words text-muted">{entry.note}</p> : null}
            <p className="mt-1 text-xs text-muted">{entry.source}{entry.logged_by_username ? ` · ${entry.logged_by_username}` : ""}</p>
          </div>
        ))}
      </div>
      <form className="mt-3 grid gap-2 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-end"
        onSubmit={(event) => { event.preventDefault(); add.mutate(); }}>
        <label className="grid gap-1 text-xs font-semibold text-muted">Hours
          <input className="desk-input" type="number" min="0.01" step="0.01" value={hours} onChange={(event) => setHours(event.target.value)} required />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted">Note
          <input className="desk-input" maxLength={255} value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <button className="desk-button-primary" type="submit" disabled={add.isPending || !hours}>{add.isPending ? "Logging..." : "Add usage"}</button>
      </form>
      {add.error instanceof Error ? <p className="mt-2 text-sm text-danger">{add.error.message}</p> : null}
    </Section>
  );
}

function DocumentsSection({ machineId }: { machineId: number }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("manual");
  const documents = useQuery({ queryKey: machineKeys.documents(machineId), queryFn: () => getMachineDocuments(machineId) });
  const items = collectionResults(documents.data);
  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a document to upload");
      return uploadMachineDocument(machineId, file, docType.trim());
    },
    onSuccess: async () => {
      setFile(null); setDocType("manual");
      if (fileInput.current) fileInput.current.value = "";
      await queryClient.invalidateQueries({ queryKey: machineKeys.documents(machineId) });
    },
  });
  const view = useMutation({
    mutationFn: (documentId: number) => getMachineDocumentUrl(documentId),
    onSuccess: ({ url }) => { window.open(url, "_blank", "noopener,noreferrer"); },
  });
  const remove = useMutation({
    mutationFn: deleteMachineDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: machineKeys.documents(machineId) }),
  });

  return (
    <Section title="Documents">
      {documents.isLoading ? <p className="text-sm text-muted">Loading documents...</p> : null}
      {documents.error instanceof Error ? <p className="text-sm text-danger">{documents.error.message}</p> : null}
      {!documents.isLoading && !documents.error && !items.length ? <p className="text-sm text-muted">No machine documents uploaded.</p> : null}
      <div className="grid gap-2">
        {items.map((document) => (
          <div key={document.id} className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-bg p-2 text-sm">
            <span className="min-w-0 flex-1"><strong className="block truncate text-ink">{document.original_filename}</strong>
              <span className="text-xs text-muted">{document.doc_type} · {formatBytes(document.size_bytes)}</span>
            </span>
            <button className="desk-button" type="button" disabled={view.isPending} onClick={() => view.mutate(document.id)}>View</button>
            <button className="desk-button" type="button" disabled={remove.isPending} onClick={() => remove.mutate(document.id)}>Delete</button>
          </div>
        ))}
      </div>
      <form className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_10rem_auto] sm:items-end"
        onSubmit={(event) => { event.preventDefault(); upload.mutate(); }}>
        <label className="grid gap-1 text-xs font-semibold text-muted">File
          <input ref={fileInput} className="desk-input" type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted">Document type
          <input className="desk-input" maxLength={16} value={docType} onChange={(event) => setDocType(event.target.value)} required />
        </label>
        <button className="desk-button-primary" type="submit" disabled={upload.isPending || !file || !docType.trim()}>
          {upload.isPending ? "Uploading..." : "Upload"}
        </button>
      </form>
      {upload.error instanceof Error ? <p className="mt-2 text-sm text-danger">{upload.error.message}</p> : null}
      {view.error instanceof Error ? <p className="mt-2 text-sm text-danger">{view.error.message}</p> : null}
      {remove.error instanceof Error ? <p className="mt-2 text-sm text-danger">{remove.error.message}</p> : null}
    </Section>
  );
}

function ErrorLogsSection({ machineId }: { machineId: number }) {
  const queryClient = useQueryClient();
  const [severity, setSeverity] = useState("error");
  const [message, setMessage] = useState("");
  const logs = useQuery({ queryKey: machineKeys.errors(machineId), queryFn: () => getMachineErrorLogs(machineId) });
  const items = collectionResults(logs.data);
  const add = useMutation({
    mutationFn: () => addMachineErrorLog(machineId, { severity: severity.trim(), message: message.trim() }),
    onSuccess: async () => {
      setMessage("");
      await queryClient.invalidateQueries({ queryKey: machineKeys.errors(machineId) });
    },
  });

  return (
    <Section title="Error logs">
      {logs.isLoading ? <p className="text-sm text-muted">Loading error logs...</p> : null}
      {logs.error instanceof Error ? <p className="text-sm text-danger">{logs.error.message}</p> : null}
      {!logs.isLoading && !logs.error && !items.length ? <p className="text-sm text-muted">No errors logged.</p> : null}
      <div className="grid gap-2">
        {items.map((entry) => (
          <div key={entry.id} className="rounded-md border border-line bg-bg p-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="text-ink">{entry.severity}</strong><span className="text-xs text-muted">{formatDate(entry.created_at)}</span>
            </div>
            <p className="mt-1 whitespace-pre-wrap break-words text-muted">{entry.message}</p>
            {entry.logged_by_username ? <p className="mt-1 text-xs text-muted">Logged by {entry.logged_by_username}</p> : null}
          </div>
        ))}
      </div>
      <form className="mt-3 grid gap-2" onSubmit={(event) => { event.preventDefault(); add.mutate(); }}>
        <label className="grid gap-1 text-xs font-semibold text-muted">Severity
          <input className="desk-input" maxLength={16} value={severity} onChange={(event) => setSeverity(event.target.value)} required />
        </label>
        <label className="grid gap-1 text-xs font-semibold text-muted">Message
          <textarea className="desk-input min-h-20" value={message} onChange={(event) => setMessage(event.target.value)} required />
        </label>
        <button className="desk-button-primary justify-self-start" type="submit" disabled={add.isPending || !severity.trim() || !message.trim()}>
          {add.isPending ? "Logging..." : "Add error log"}
        </button>
      </form>
      {add.error instanceof Error ? <p className="mt-2 text-sm text-danger">{add.error.message}</p> : null}
    </Section>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
