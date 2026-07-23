import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { MachineServiceRequest, PrinterPool, TypedManualUsageResponse } from "../../../../generated/api";
import { collectionResults, getMachineTypes, getMachines, machineKeys, type Machine, type MeteringUnit } from "../../machinesApi";
import { staffRequest } from "../../../../lib/api";
import { Panel, useStaffGet } from "../shared";

type Props = { makerspaceId: number; canManage: boolean };
type ActionName = "accept" | "reject" | "start" | "complete" | "fail" | "collect";
type Action = { id: number; name: ActionName };
type ActionValues = { machine_id: string; consumable_pool_id: string; estimated_minutes: string; planned_quantity: string; actual_minutes: string; actual_quantity: string; percent_complete: string; reason: string; };

const unitLabels: Record<MeteringUnit, string> = { weight: "grams", volume: "milliliters", length: "millimeters", count: "count", minutes: "minutes" };
const poolUnits: Partial<Record<MeteringUnit, "grams" | "milliliters" | "millimeters" | "count">> = { weight: "grams", volume: "milliliters", length: "millimeters", count: "count" };

function actionsFor(request: MachineServiceRequest, onAction: (name: ActionName) => void) {
  if (request.status === "pending") return <><button onClick={() => onAction("accept")}>Accept</button><button onClick={() => onAction("reject")}>Reject</button></>;
  if (request.status === "accepted") return <button onClick={() => onAction("start")}>Start</button>;
  if (request.status === "in_progress") return <><button onClick={() => onAction("complete")}>Complete</button><button onClick={() => onAction("fail")}>Fail</button></>;
  return request.status === "completed" ? <button onClick={() => onAction("collect")}>Collect</button> : null;
}

export function MachineServiceConsole({ makerspaceId, canManage }: Props) {
  const queryClient = useQueryClient();
  const [typeSlug, setTypeSlug] = useState("");
  const [action, setAction] = useState<Action | null>(null);
  const [values, setValues] = useState<ActionValues>({ machine_id: "", consumable_pool_id: "", estimated_minutes: "60", planned_quantity: "", actual_minutes: "0", actual_quantity: "", percent_complete: "0", reason: "" });
  const [pool, setPool] = useState({ material: "", color: "", brand: "", quantity: "" });
  const [manual, setManual] = useState({ machine_id: "", consumable_pool_id: "", duration_minutes: "", quantity: "", outcome: "success", percent_complete: "100", reason: "", note: "" });
  const types = useQuery({ queryKey: machineKeys.types(makerspaceId), queryFn: () => getMachineTypes(makerspaceId), enabled: canManage });
  const serviceTypes = useMemo(() => collectionResults(types.data).filter((type) => type.slug !== "3d_printer"), [types.data]);
  const selectedType = serviceTypes.find((type) => type.slug === typeSlug) ?? serviceTypes[0];
  const meteringUnit = (selectedType?.capability_config?.metering_unit ?? "count") as MeteringUnit;
  const unitLabel = unitLabels[meteringUnit];
  const poolUnit = poolUnits[meteringUnit];
  const machineTypeFilter = selectedType ? `machine_type=${encodeURIComponent(selectedType.slug)}` : "";
  const requests = useStaffGet<MachineServiceRequest[]>(["machine-service-requests", makerspaceId, selectedType?.id], `/admin/makerspaces/${makerspaceId}/machine-service/requests?${machineTypeFilter}`, canManage && !!selectedType);
  const manualUsage = useStaffGet<TypedManualUsageResponse[]>(["machine-service-manual", makerspaceId, selectedType?.id], `/admin/makerspaces/${makerspaceId}/machine-service/typed-manual-usage?${machineTypeFilter}`, canManage && !!selectedType);
  const allPools = useStaffGet<PrinterPool[]>(["machine-service-pools", makerspaceId], `/admin/makerspaces/${makerspaceId}/machine-service/consumable-pools`, canManage);
  const machineList = useQuery({ queryKey: machineKeys.list(makerspaceId), queryFn: () => getMachines(makerspaceId), enabled: canManage });
  const machines = useMemo(() => (machineList.data?.results ?? []).filter((machine) => machine.machine_type.slug === selectedType?.slug), [machineList.data, selectedType?.slug]);
  const pools = useMemo(() => !poolUnit ? [] : (allPools.data ?? []).filter((item) => item.unit === poolUnit && (!item.machine_id || machines.some((machine) => machine.id === item.machine_id))), [allPools.data, machines, poolUnit]);

  const invalidate = () => void Promise.all([
    queryClient.invalidateQueries({ queryKey: ["machine-service-requests", makerspaceId, selectedType?.id] }),
    queryClient.invalidateQueries({ queryKey: ["machine-service-manual", makerspaceId, selectedType?.id] }),
    queryClient.invalidateQueries({ queryKey: ["machine-service-pools", makerspaceId] }),
  ]);
  const createPool = useMutation({
    mutationFn: () => staffRequest<PrinterPool>(`/admin/makerspaces/${makerspaceId}/machine-service/consumable-pools`, { method: "POST", body: JSON.stringify({ ...pool, quantity: pool.quantity, unit: poolUnit }) }),
    onSuccess: () => { setPool({ material: "", color: "", brand: "", quantity: "" }); invalidate(); },
  });
  const adjustPool = useMutation({
    mutationFn: ({ id, quantity_delta }: { id: number; quantity_delta: string }) => staffRequest(`/admin/machine-service/consumable-pools/${id}/adjustments`, { method: "POST", body: JSON.stringify({ quantity_delta, reason: "Manual correction" }) }),
    onSuccess: invalidate,
  });
  const submitManual = useMutation({
    mutationFn: () => staffRequest(`/admin/makerspaces/${makerspaceId}/machine-service/typed-manual-usage`, { method: "POST", body: JSON.stringify({ machine_id: Number(manual.machine_id), consumable_pool_id: poolUnit && manual.consumable_pool_id ? Number(manual.consumable_pool_id) : null, duration_minutes: Number(manual.duration_minutes), quantity: poolUnit && manual.quantity ? manual.quantity : undefined, metering_unit: meteringUnit, outcome: manual.outcome, percent_complete: Number(manual.percent_complete), reason: manual.reason || undefined, note: manual.note || undefined }) }),
    onSuccess: () => { setManual({ machine_id: "", consumable_pool_id: "", duration_minutes: "", quantity: "", outcome: "success", percent_complete: "100", reason: "", note: "" }); invalidate(); },
  });
  const runAction = useMutation({
    mutationFn: () => {
      if (!action) throw new Error("Choose an action.");
      const body = action.name === "accept" ? { estimated_minutes: Number(values.estimated_minutes) }
        : action.name === "start" ? { machine_id: values.machine_id ? Number(values.machine_id) : null, consumable_pool_id: poolUnit && values.consumable_pool_id ? Number(values.consumable_pool_id) : undefined, estimated_minutes: Number(values.estimated_minutes), planned_quantity: poolUnit && values.planned_quantity ? values.planned_quantity : undefined }
        : action.name === "complete" ? { actual_minutes: Number(values.actual_minutes), actual_quantity: poolUnit && values.actual_quantity ? values.actual_quantity : undefined }
        : action.name === "fail" ? { actual_minutes: Number(values.actual_minutes), actual_quantity: poolUnit && values.actual_quantity ? values.actual_quantity : undefined, percent_complete: Number(values.percent_complete), reason: values.reason }
        : action.name === "reject" ? { reason: values.reason } : {};
      return staffRequest(`/admin/machine-service/requests/${action.id}/${action.name}`, { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => { setAction(null); invalidate(); },
  });

  if (!canManage) return null;
  return <div className="mt-6 grid gap-4"><Panel title="Machine service queue">
    <div className="mb-3 max-w-md"><label className="grid gap-1 text-xs font-semibold text-muted">Machine type<select className="desk-input" value={selectedType?.slug ?? ""} onChange={(event) => setTypeSlug(event.target.value)}><option value="">Select a type</option>{serviceTypes.map((type) => <option key={type.id} value={type.slug}>{type.name}</option>)}</select></label></div>
    {!selectedType ? <p className="text-sm text-muted">No non-printer machine types are configured.</p> : <><p className="mb-3 text-sm text-muted">This type is metered in {unitLabel}. {poolUnit ? "Use a compatible consumable pool for reservations and reconciliation." : "Minutes-based services do not use consumable pools."}</p>
      <div className="grid gap-2">{requests.data?.map((request) => <article className="rounded-md border border-line bg-surface p-3" key={request.id}><div className="flex flex-wrap items-center justify-between gap-2"><strong>{request.title}</strong><span>{request.status.replace("_", " ")}</span></div><p className="mt-1 text-xs text-muted">Planned {request.planned_quantity ?? "0"} {unitLabel} · actual {request.actual_consumed_quantity ?? "0"} {unitLabel}</p><div className="mt-2 flex flex-wrap gap-2">{actionsFor(request, (name) => setAction({ id: request.id, name }))}</div></article>) ?? <p className="text-sm text-muted">Loading service queue...</p>}</div>
      {action ? <ServiceActionForm action={action} values={values} setValues={setValues} machines={machines} pools={pools} unitLabel={unitLabel} hasPool={!!poolUnit} pending={runAction.isPending} onSubmit={() => runAction.mutate()} onCancel={() => setAction(null)} /> : null}
    </>}</Panel>
    {selectedType && poolUnit ? <Panel title={`${selectedType.name} consumable pools`}><div className="grid gap-2 md:grid-cols-5"><input className="desk-input" placeholder="Material" value={pool.material} onChange={(event) => setPool({ ...pool, material: event.target.value })} /><input className="desk-input" placeholder="Colour" value={pool.color} onChange={(event) => setPool({ ...pool, color: event.target.value })} /><input className="desk-input" placeholder="Brand" value={pool.brand} onChange={(event) => setPool({ ...pool, brand: event.target.value })} /><input className="desk-input" type="number" min="0" placeholder={`Initial ${unitLabel}`} value={pool.quantity} onChange={(event) => setPool({ ...pool, quantity: event.target.value })} /><button disabled={!pool.material.trim() || !pool.quantity || createPool.isPending} onClick={() => createPool.mutate()}>Add pool</button></div><div className="mt-3 grid gap-2">{pools.map((item) => <div className="flex items-center justify-between rounded-md border border-line p-2" key={item.id}><span>{[item.brand, item.material, item.color].filter(Boolean).join(" ")} · {item.remaining_grams} {unitLabel}</span><button onClick={() => adjustPool.mutate({ id: item.id, quantity_delta: prompt(`Adjustment in ${unitLabel} (+/-)`) ?? "0" })}>Adjust</button></div>)}</div></Panel> : null}
    {selectedType ? <Panel title="Manual usage"><div className="grid gap-2 md:grid-cols-4"><select className="desk-input" value={manual.machine_id} onChange={(event) => setManual({ ...manual, machine_id: event.target.value })}><option value="">Machine</option>{machines.map((machine) => <option key={machine.id} value={machine.id}>{machine.name}</option>)}</select>{poolUnit ? <select className="desk-input" value={manual.consumable_pool_id} onChange={(event) => setManual({ ...manual, consumable_pool_id: event.target.value })}><option value="">No pool</option>{pools.map((item) => <option key={item.id} value={item.id}>{item.material} {item.color}</option>)}</select> : null}<input className="desk-input" type="number" min="0" placeholder="Minutes" value={manual.duration_minutes} onChange={(event) => setManual({ ...manual, duration_minutes: event.target.value })} />{poolUnit ? <input className="desk-input" type="number" min="0" placeholder={unitLabel} value={manual.quantity} onChange={(event) => setManual({ ...manual, quantity: event.target.value })} /> : null}<select className="desk-input" value={manual.outcome} onChange={(event) => setManual({ ...manual, outcome: event.target.value })}><option value="success">Success</option><option value="failed">Failed</option></select>{manual.outcome === "failed" ? <input className="desk-input" placeholder="Failure reason" value={manual.reason} onChange={(event) => setManual({ ...manual, reason: event.target.value })} /> : null}<input className="desk-input" placeholder="Note" value={manual.note} onChange={(event) => setManual({ ...manual, note: event.target.value })} /><button disabled={!manual.machine_id || !manual.duration_minutes || submitManual.isPending} onClick={() => submitManual.mutate()}>Log usage</button></div><div className="mt-3 grid gap-2">{manualUsage.data?.map((entry) => <p className="rounded-md border border-line p-2 text-sm" key={entry.id}>{entry.outcome} · {entry.consumed_quantity} {unitLabel} · {entry.duration_minutes} min</p>)}</div></Panel> : null}
    {([requests.error, allPools.error, machineList.error, createPool.error, adjustPool.error, submitManual.error, runAction.error].find((error) => error instanceof Error) as Error | undefined) ? <p className="text-sm text-danger">{([requests.error, allPools.error, machineList.error, createPool.error, adjustPool.error, submitManual.error, runAction.error].find((error) => error instanceof Error) as Error).message}</p> : null}
  </div>;
}

function ServiceActionForm({ action, values, setValues, machines, pools, unitLabel, hasPool, pending, onSubmit, onCancel }: { action: Action; values: ActionValues; setValues: Dispatch<SetStateAction<ActionValues>>; machines: Machine[]; pools: PrinterPool[]; unitLabel: string; hasPool: boolean; pending: boolean; onSubmit: () => void; onCancel: () => void }) {
  const input = (key: keyof ActionValues, label: string) => <label className="grid gap-1 text-xs">{label}<input className="desk-input" value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} /></label>;
  return <div className="mt-3 rounded-md border border-accent bg-bg p-3"><p className="font-semibold capitalize">{action.name}</p><div className="mt-2 grid gap-2 md:grid-cols-3">{action.name === "accept" ? input("estimated_minutes", "Estimated minutes") : null}{action.name === "start" ? <><select className="desk-input" value={values.machine_id} onChange={(event) => setValues({ ...values, machine_id: event.target.value })}><option value="">Machine</option>{machines.map((machine) => <option key={machine.id} value={machine.id}>{machine.name}</option>)}</select>{hasPool ? <select className="desk-input" value={values.consumable_pool_id} onChange={(event) => setValues({ ...values, consumable_pool_id: event.target.value })}><option value="">Pool</option>{pools.map((pool) => <option key={pool.id} value={pool.id}>{pool.material} {pool.color}</option>)}</select> : null}{input("estimated_minutes", "Estimated minutes")}{hasPool ? input("planned_quantity", `Planned ${unitLabel}`) : null}</> : null}{action.name === "complete" || action.name === "fail" ? <>{input("actual_minutes", "Actual minutes")}{hasPool ? input("actual_quantity", `Actual ${unitLabel}`) : null}{action.name === "fail" ? <>{input("percent_complete", "Percent complete")}{input("reason", "Reason")}</> : null}</> : null}{action.name === "reject" ? input("reason", "Reason") : null}</div><div className="mt-2 flex gap-2"><button disabled={pending} onClick={onSubmit}>Confirm</button><button onClick={onCancel}>Cancel</button></div></div>;
}