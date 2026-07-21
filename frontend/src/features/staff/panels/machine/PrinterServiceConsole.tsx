import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  MachineServiceReport,
  MachineServiceRequest,
  PrinterPool,
  TypedManualUsageResponse,
} from "../../../../generated/api";
import {
  createMachine,
  getMachineTypes,
  getMachines,
  machineKeys,
  updateMachine,
  uploadMachineImage,
  type Machine,
} from "../../machinesApi";
import { staffRequest } from "../../../../lib/api";
import { Panel, useStaffGet } from "../shared";

type Props = { makerspaceId: number; canManage: boolean };
type ActionName = "accept" | "reject" | "start" | "complete" | "fail" | "collect" | "reprint";
type Action = { id: number; name: ActionName };
type ActionValues = {
  machine_id: string; consumable_pool_id: string; estimated_minutes: string; planned_grams: string;
  actual_minutes: string; actual_grams: string; percent_complete: string; reason: string;
};

const printerFilter = "machine_type=3d_printer";
const requestPath = (makerspaceId: number) =>
  `/admin/makerspaces/${makerspaceId}/machine-service/requests?${printerFilter}`;
const poolsPath = (makerspaceId: number) =>
  `/admin/makerspaces/${makerspaceId}/machine-service/consumable-pools`;
const blankActionValues: ActionValues = {
  machine_id: "", consumable_pool_id: "", estimated_minutes: "60", planned_grams: "",
  actual_minutes: "0", actual_grams: "", percent_complete: "0", reason: "",
};

export function PrinterServiceConsole({ makerspaceId, canManage }: Props) {
  const queryClient = useQueryClient();
  const [machineName, setMachineName] = useState("");
  const [machineModel, setMachineModel] = useState("");
  const [machineImage, setMachineImage] = useState<File | null>(null);
  const [pool, setPool] = useState({ material: "PLA", color: "", brand: "", initial_grams: "1000", low_threshold_grams: "" });
  const [manual, setManual] = useState({ machine_id: "", consumable_pool_id: "", duration_minutes: "", grams: "", outcome: "success", percent_complete: "100", reason: "", note: "" });
  const [action, setAction] = useState<Action | null>(null);
  const [actionValues, setActionValues] = useState<ActionValues>(blankActionValues);

  const types = useQuery({ queryKey: machineKeys.types(makerspaceId), queryFn: () => getMachineTypes(makerspaceId), enabled: canManage });
  const machines = useQuery({ queryKey: ["printer-machines", makerspaceId], queryFn: () => getMachines(makerspaceId), enabled: canManage });
  const pools = useStaffGet<PrinterPool[]>(["printer-pools", makerspaceId], poolsPath(makerspaceId), canManage);
  const requests = useStaffGet<MachineServiceRequest[]>(["printer-service-requests", makerspaceId], requestPath(makerspaceId), canManage);
  const manualUsage = useStaffGet<TypedManualUsageResponse[]>(["printer-manual-usage", makerspaceId], `/admin/makerspaces/${makerspaceId}/machine-service/typed-manual-usage?${printerFilter}`, canManage);
  const report = useStaffGet<MachineServiceReport>(["printer-service-report", makerspaceId], `/admin/makerspace/${makerspaceId}/machine-service-report?${printerFilter}`, canManage);
  const printerType = types.data && (Array.isArray(types.data) ? types.data : types.data.results).find((type) => type.slug === "3d_printer");
  const printers = useMemo(() => (machines.data?.results ?? []).filter((machine) => machine.machine_type.slug === "3d_printer"), [machines.data]);

  const invalidate = () => {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["printer-machines", makerspaceId] }),
      queryClient.invalidateQueries({ queryKey: ["printer-pools", makerspaceId] }),
      queryClient.invalidateQueries({ queryKey: ["printer-service-requests", makerspaceId] }),
      queryClient.invalidateQueries({ queryKey: ["printer-manual-usage", makerspaceId] }),
      queryClient.invalidateQueries({ queryKey: ["printer-service-report", makerspaceId] }),
      queryClient.invalidateQueries({ queryKey: machineKeys.list(makerspaceId) }),
    ]);
  };

  const createPrinter = useMutation({
    mutationFn: async () => {
      if (!printerType) throw new Error("The 3D-printer machine type is not configured.");
      const created = await createMachine(makerspaceId, { name: machineName.trim(), machine_type_id: printerType.id, location: "", notes: "", firmware_version: "", camera_feed_url: "", type_payload: { model: machineModel.trim() } });
      if (machineImage) await uploadMachineImage(created.id, machineImage);
      return created;
    },
    onSuccess: () => { setMachineName(""); setMachineModel(""); setMachineImage(null); invalidate(); },
  });
  const createPool = useMutation({
    mutationFn: () => staffRequest<PrinterPool>(poolsPath(makerspaceId), { method: "POST", body: JSON.stringify({ ...pool, low_threshold_grams: pool.low_threshold_grams || null }) }),
    onSuccess: () => { setPool({ material: "PLA", color: "", brand: "", initial_grams: "1000", low_threshold_grams: "" }); invalidate(); },
  });
  const adjustPool = useMutation({
    mutationFn: ({ id, quantity_delta }: { id: number; quantity_delta: string }) => staffRequest(`/admin/machine-service/consumable-pools/${id}/adjustments`, { method: "POST", body: JSON.stringify({ quantity_delta, reason: "Manual correction" }) }),
    onSuccess: invalidate,
  });
  const submitManual = useMutation({
    mutationFn: () => staffRequest(`/admin/makerspaces/${makerspaceId}/machine-service/typed-manual-usage`, { method: "POST", body: JSON.stringify({ machine_id: Number(manual.machine_id), consumable_pool_id: manual.consumable_pool_id ? Number(manual.consumable_pool_id) : null, duration_minutes: Number(manual.duration_minutes), grams: manual.grams || undefined, outcome: manual.outcome, percent_complete: Number(manual.percent_complete), reason: manual.reason || undefined, note: manual.note || undefined }) }),
    onSuccess: () => { setManual({ machine_id: "", consumable_pool_id: "", duration_minutes: "", grams: "", outcome: "success", percent_complete: "100", reason: "", note: "" }); invalidate(); },
  });
  const runAction = useMutation({
    mutationFn: () => {
      if (!action) throw new Error("Choose an action.");
      return staffRequest(`/admin/machine-service/requests/${action.id}/${action.name}`, { method: "POST", body: JSON.stringify(actionBody(action, actionValues)) });
    },
    onSuccess: () => { setAction(null); setActionValues(blankActionValues); invalidate(); },
  });
  const settlePayment = useMutation({
    mutationFn: ({ paymentId, operation }: { paymentId: number; operation: "mark-offline" | "waive" }) =>
      staffRequest(`/admin/machine-service/payments/${paymentId}/${operation}`, { method: "POST" }),
    onSuccess: invalidate,
  });

  if (!canManage) return null;
  return <div className="mt-6 grid gap-4">
    <Panel title="3D-printer queue">
      <p className="mb-3 text-sm text-muted">Accept jobs, reserve filament, start work, reconcile actual grams, then complete, fail, collect, or reprint. Charges are calculated at completion.</p>
      <div className="grid gap-2">
        {requests.data?.map((request) => <article className="rounded-md border border-line bg-surface p-3" key={request.id}>
          <div className="flex flex-wrap items-center justify-between gap-2"><strong>{request.title}</strong><span>{request.status.replace("_", " ")}</span></div>
          <p className="mt-1 text-xs text-muted">Planned {request.planned_grams}g · payment {request.payment ? `${request.payment.amount} ${request.payment.currency} · ${request.payment.status}` : "—"}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <ServiceActions request={request} onAction={(name) => setAction({ id: request.id, name })} />
            {request.payment?.status === "pending" ? <>
              <button disabled={settlePayment.isPending} onClick={() => settlePayment.mutate({ paymentId: request.payment!.id, operation: "mark-offline" })}>{settlePayment.isPending ? "Settling…" : "Mark paid offline"}</button>
              <button disabled={settlePayment.isPending} onClick={() => settlePayment.mutate({ paymentId: request.payment!.id, operation: "waive" })}>Waive payment</button>
            </> : null}
          </div>
        </article>) ?? <p className="text-sm text-muted">Loading printer queue…</p>}
      </div>
      {action ? <ActionForm action={action} values={actionValues} setValues={setActionValues} printers={printers} pools={pools.data ?? []} pending={runAction.isPending} onCancel={() => setAction(null)} onSubmit={() => runAction.mutate()} /> : null}
      <ErrorBlock error={requests.error ?? runAction.error ?? settlePayment.error} />
    </Panel>
    <Panel title="Printers">
      <div className="grid gap-2 md:grid-cols-4"><input className="desk-input" placeholder="Printer name" value={machineName} onChange={(event) => setMachineName(event.target.value)} /><input className="desk-input" placeholder="Model" value={machineModel} onChange={(event) => setMachineModel(event.target.value)} /><input className="desk-input" type="file" accept="image/*" onChange={(event) => setMachineImage(event.target.files?.[0] ?? null)} /><button disabled={!machineName.trim() || createPrinter.isPending} onClick={() => createPrinter.mutate()}>Add printer</button></div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">{printers.map((machine) => <PrinterRow key={machine.id} machine={machine} onStatus={(status) => updateMachine(machine.id, { status }).then(invalidate)} />)}</div>
      <ErrorBlock error={createPrinter.error} />
    </Panel>
    <Panel title="Filament pools">
      <div className="grid gap-2 md:grid-cols-5"><input className="desk-input" value={pool.material} placeholder="Material" onChange={(event) => setPool({ ...pool, material: event.target.value })} /><input className="desk-input" value={pool.color} placeholder="Colour" onChange={(event) => setPool({ ...pool, color: event.target.value })} /><input className="desk-input" value={pool.brand} placeholder="Brand" onChange={(event) => setPool({ ...pool, brand: event.target.value })} /><input className="desk-input" value={pool.initial_grams} type="number" placeholder="Initial grams" onChange={(event) => setPool({ ...pool, initial_grams: event.target.value })} /><button disabled={!pool.material.trim() || createPool.isPending} onClick={() => createPool.mutate()}>Add pool</button></div>
      <div className="mt-3 grid gap-2">{pools.data?.map((item) => <div className="flex items-center justify-between rounded-md border border-line p-2" key={item.id}><span>{[item.brand, item.material, item.color].filter(Boolean).join(" ")} · {item.remaining_grams}g</span><button onClick={() => adjustPool.mutate({ id: item.id, quantity_delta: prompt("Adjustment in grams (+/-)") ?? "0" })}>Adjust</button></div>)}</div>
      <ErrorBlock error={pools.error ?? createPool.error ?? adjustPool.error} />
    </Panel>
    <Panel title="Manual usage">
      <div className="grid gap-2 md:grid-cols-4"><select className="desk-input" value={manual.machine_id} onChange={(event) => setManual({ ...manual, machine_id: event.target.value })}><option value="">Printer</option>{printers.map((machine) => <option value={machine.id} key={machine.id}>{machine.name}</option>)}</select><select className="desk-input" value={manual.consumable_pool_id} onChange={(event) => setManual({ ...manual, consumable_pool_id: event.target.value })}><option value="">No pool</option>{(pools.data ?? []).map((item) => <option value={item.id} key={item.id}>{item.material} {item.color}</option>)}</select><input className="desk-input" placeholder="Minutes" type="number" value={manual.duration_minutes} onChange={(event) => setManual({ ...manual, duration_minutes: event.target.value })} /><input className="desk-input" placeholder="Grams" type="number" value={manual.grams} onChange={(event) => setManual({ ...manual, grams: event.target.value })} /><select className="desk-input" value={manual.outcome} onChange={(event) => setManual({ ...manual, outcome: event.target.value })}><option value="success">Success</option><option value="failed">Failed</option></select>{manual.outcome === "failed" ? <><input className="desk-input" placeholder="Percent complete" type="number" value={manual.percent_complete} onChange={(event) => setManual({ ...manual, percent_complete: event.target.value })} /><input className="desk-input" placeholder="Failure reason" value={manual.reason} onChange={(event) => setManual({ ...manual, reason: event.target.value })} /></> : null}<input className="desk-input" placeholder="Note" value={manual.note} onChange={(event) => setManual({ ...manual, note: event.target.value })} /><button disabled={!manual.machine_id || !manual.duration_minutes || submitManual.isPending} onClick={() => submitManual.mutate()}>Log usage</button></div>
      <div className="mt-3 grid gap-2">{manualUsage.data?.map((entry) => <p className="rounded-md border border-line p-2 text-sm" key={entry.id}>{entry.outcome} · {entry.consumed_grams}g · {entry.duration_minutes} min{entry.outcome === "failed" ? ` · ${entry.percent_complete}%` : ""}</p>)}</div>
      <ErrorBlock error={manualUsage.error ?? submitManual.error} />
    </Panel>
    <Panel title="Printer reports">
      <div className="grid gap-2 md:grid-cols-4">{report.data?.status_totals.map((total) => <p className="rounded-md border border-line p-3 text-sm" key={`${total.makerspace_id ?? makerspaceId}`}>Submitted {total.submitted} · completed {total.completed} · failed {total.failed}</p>)}</div>
      {report.data?.machines.map((machine) => <p className="mt-2 text-sm" key={machine.machine_id}>{machine.machine_name}: {machine.completed_count} complete, {machine.failed_count} failed, {machine.total_recorded_service_hours}h</p>)}
      <ErrorBlock error={report.error} />
    </Panel>
  </div>;
}

function actionBody(action: Action, values: ActionValues) {
  if (action.name === "accept") return { estimated_minutes: Number(values.estimated_minutes), planned_grams: values.planned_grams || undefined };
  if (action.name === "start") return { machine_id: values.machine_id ? Number(values.machine_id) : null, consumable_pool_id: values.consumable_pool_id ? Number(values.consumable_pool_id) : undefined, estimated_minutes: Number(values.estimated_minutes), planned_grams: values.planned_grams || undefined };
  if (action.name === "complete") return { actual_minutes: Number(values.actual_minutes), actual_grams: values.actual_grams || undefined };
  if (action.name === "fail") return { actual_minutes: Number(values.actual_minutes), actual_grams: values.actual_grams || undefined, percent_complete: Number(values.percent_complete), reason: values.reason };
  return action.name === "reject" ? { reason: values.reason } : {};
}

function ServiceActions({ request, onAction }: { request: MachineServiceRequest; onAction: (name: ActionName) => void }) {
  if (request.status === "pending") return <><button onClick={() => onAction("accept")}>Accept</button><button onClick={() => onAction("reject")}>Reject</button></>;
  if (request.status === "accepted") return <button onClick={() => onAction("start")}>Start</button>;
  if (request.status === "in_progress") return <><button onClick={() => onAction("complete")}>Complete</button><button onClick={() => onAction("fail")}>Fail</button></>;
  if (request.status === "completed") return <button onClick={() => onAction("collect")}>Collect</button>;
  return request.status === "failed" ? <button onClick={() => onAction("reprint")}>Reprint</button> : null;
}

function PrinterRow({ machine, onStatus }: { machine: Machine; onStatus: (status: Machine["status"]) => void }) {
  const model = (machine.type_payload as { model?: string } | undefined)?.model;
  return <div className="rounded-md border border-line p-3"><strong>{machine.name}</strong><p className="text-xs text-muted">{model || "No model"} · {machine.status}</p><select className="desk-input mt-2" value={machine.status} onChange={(event) => onStatus(event.target.value as Machine["status"])}><option value="idle">Idle</option><option value="running">Running</option><option value="maintenance">Maintenance</option><option value="offline">Offline</option></select></div>;
}

function ActionForm({ action, values, setValues, printers, pools, pending, onCancel, onSubmit }: { action: Action; values: ActionValues; setValues: Dispatch<SetStateAction<ActionValues>>; printers: Machine[]; pools: PrinterPool[]; pending: boolean; onCancel: () => void; onSubmit: () => void }) {
  const input = (key: keyof ActionValues, label: string) => <label className="grid gap-1 text-xs">{label}<input className="desk-input" value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} /></label>;
  return <div className="mt-3 rounded-md border border-accent bg-bg p-3"><p className="font-semibold capitalize">{action.name}</p><div className="mt-2 grid gap-2 md:grid-cols-3">{action.name === "start" ? <><select className="desk-input" value={values.machine_id} onChange={(event) => setValues({ ...values, machine_id: event.target.value })}><option value="">Printer</option>{printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select><select className="desk-input" value={values.consumable_pool_id} onChange={(event) => setValues({ ...values, consumable_pool_id: event.target.value })}><option value="">Pool</option>{pools.map((pool) => <option key={pool.id} value={pool.id}>{pool.material} {pool.color}</option>)}</select>{input("estimated_minutes", "Estimated minutes")}{input("planned_grams", "Planned grams")}</> : null}{action.name === "accept" ? <>{input("estimated_minutes", "Estimated minutes")}{input("planned_grams", "Planned grams")}</> : null}{action.name === "complete" || action.name === "fail" ? <>{input("actual_minutes", "Actual minutes")}{input("actual_grams", "Actual grams")}{action.name === "fail" ? <>{input("percent_complete", "Percent complete")}{input("reason", "Reason")}</> : null}</> : null}{action.name === "reject" ? input("reason", "Reason") : null}</div><div className="mt-2 flex gap-2"><button disabled={pending} onClick={onSubmit}>Confirm</button><button onClick={onCancel}>Cancel</button></div></div>;
}

function ErrorBlock({ error }: { error: unknown }) {
  return error instanceof Error ? <p className="mt-2 text-sm text-danger">{error.message}</p> : null;
}