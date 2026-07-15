import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DetailDrawer, EmptyState, Skeleton, StatusBadge } from "../../../components/ui";
import {
  getMachine,
  machineKeys,
  retireMachine,
  setMachineStatus,
  unretireMachine,
  updateMachine,
  type MachineStatus,
} from "../machinesApi";
import { MachineDetailSections } from "./MachineDetailSections";

const MACHINE_STATUSES: MachineStatus[] = ["idle", "running", "reserved", "maintenance", "offline"];

export function MachineDetailDrawer({ machineId, makerspaceId, machineName, canManage, onClose }: {
  machineId: number; makerspaceId: number; machineName: string; canManage: boolean; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const machine = useQuery({ queryKey: machineKeys.detail(machineId), queryFn: () => getMachine(machineId) });
  const [form, setForm] = useState({ name: "", location: "", notes: "", firmware_version: "", camera_feed_url: "" });
  const [status, setStatusValue] = useState<MachineStatus>("idle");

  useEffect(() => {
    if (!machine.data) return;
    setForm({
      name: machine.data.name,
      location: machine.data.location,
      notes: machine.data.notes,
      firmware_version: machine.data.firmware_version,
      camera_feed_url: machine.data.camera_feed_url,
    });
    setStatusValue(machine.data.status);
  }, [machine.data]);

  const refreshMachine = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: machineKeys.detail(machineId) }),
      queryClient.invalidateQueries({ queryKey: machineKeys.list(makerspaceId) }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => updateMachine(machineId, {
      name: form.name.trim(),
      location: form.location.trim(),
      notes: form.notes.trim(),
      firmware_version: form.firmware_version.trim(),
      camera_feed_url: form.camera_feed_url.trim(),
    }),
    onSuccess: refreshMachine,
  });
  const statusMutation = useMutation({
    mutationFn: () => setMachineStatus(machineId, status),
    onSuccess: refreshMachine,
  });
  const lifecycle = useMutation({
    mutationFn: (action: "retire" | "unretire") => action === "retire" ? retireMachine(machineId) : unretireMachine(machineId),
    onSuccess: refreshMachine,
  });
  const updateField = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));

  return (
    <DetailDrawer open title={machineName} onClose={onClose}>
      {machine.isLoading ? <div className="grid gap-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /></div> : null}
      {machine.error instanceof Error ? <EmptyState title="Unable to load machine" description={machine.error.message} /> : null}
      {machine.data ? (
        <div className="grid gap-5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={machine.data.status} />
            {!machine.data.is_active ? <span className="rounded-md bg-warn/15 px-2 py-1 text-xs font-medium text-warn-ink">Retired</span> : null}
            <span className="text-sm text-muted">{machine.data.machine_type.name} · {machine.data.usage_hours} total hours</span>
          </div>
          <section className="grid gap-3">
            <h3 className="text-sm font-semibold text-ink">Machine details</h3>
            <label className="grid gap-1 text-xs font-semibold text-muted">Name
              <input className="desk-input" value={form.name} disabled={!canManage} onChange={(event) => updateField("name", event.target.value)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs font-semibold text-muted">Location
                <input className="desk-input" value={form.location} disabled={!canManage} onChange={(event) => updateField("location", event.target.value)} />
              </label>
              <label className="grid gap-1 text-xs font-semibold text-muted">Firmware version
                <input className="desk-input" value={form.firmware_version} disabled={!canManage} onChange={(event) => updateField("firmware_version", event.target.value)} />
              </label>
            </div>
            <label className="grid gap-1 text-xs font-semibold text-muted">Camera feed URL
              <input className="desk-input" type="url" value={form.camera_feed_url} disabled={!canManage}
                onChange={(event) => updateField("camera_feed_url", event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs font-semibold text-muted">Notes
              <textarea className="desk-input min-h-24" value={form.notes} disabled={!canManage}
                onChange={(event) => updateField("notes", event.target.value)} />
            </label>
            {canManage ? <button className="desk-button-primary justify-self-start" type="button"
              disabled={save.isPending || !form.name.trim()} onClick={() => save.mutate()}>
              {save.isPending ? "Saving..." : "Save changes"}
            </button> : null}
            {save.error instanceof Error ? <p className="text-sm text-danger">{save.error.message}</p> : null}
          </section>

          <section className="border-t border-line pt-4">
            <h3 className="mb-3 text-sm font-semibold text-ink">Status</h3>
            <div className="flex flex-col gap-2 sm:flex-row">
              <select className="desk-input flex-1" value={status} onChange={(event) => setStatusValue(event.target.value as MachineStatus)}>
                {MACHINE_STATUSES.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
              </select>
              <button className="desk-button-primary" type="button" disabled={statusMutation.isPending} onClick={() => statusMutation.mutate()}>
                {statusMutation.isPending ? "Setting..." : "Set status"}
              </button>
              <button className="desk-button" type="button" disabled={lifecycle.isPending}
                onClick={() => lifecycle.mutate(machine.data.is_active ? "retire" : "unretire")}>
                {machine.data.is_active ? "Retire" : "Reactivate"}
              </button>
            </div>
            {statusMutation.error instanceof Error ? <p className="mt-2 text-sm text-danger">{statusMutation.error.message}</p> : null}
            {lifecycle.error instanceof Error ? <p className="mt-2 text-sm text-danger">{lifecycle.error.message}</p> : null}
          </section>

          <MachineDetailSections machineId={machineId} makerspaceId={makerspaceId} canManage={canManage} />
        </div>
      ) : null}
    </DetailDrawer>
  );
}
