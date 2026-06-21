import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge, ConfirmDialog, EmptyState } from "../../../components/ui";
import { staffRequest } from "../../../lib/api";
import { Panel, useStaffGet, type Makerspace } from "./shared";
import {
  AddStaffModal,
  CreateMakerspaceModal,
  ResetPasswordModal,
  RestrictUserModal,
  type MakerspaceForm,
  type ResetPasswordForm,
  type ResetPasswordResult,
  type RestrictForm,
  type StaffForm,
} from "./UsersModals";

type RoleValue = "space_manager" | "inventory_manager" | "guest_admin" | "print_manager";
type User = { id: number; username: string; email: string; access_status: "active" | "restricted" | "suspended" | string };
type StaffMembership = {
  id: number;
  user: User;
  makerspace_id: number;
  makerspace_slug: string;
  role: RoleValue;
};
type StaffListResponse = StaffMembership[] | { results: StaffMembership[] };

const roles: { value: RoleValue; label: string; path: string }[] = [
  { value: "space_manager", label: "Space Managers", path: "/admin/users/space-managers" },
  { value: "inventory_manager", label: "Inventory Managers", path: "/admin/users/inventory-managers" },
  { value: "guest_admin", label: "Guest Admins", path: "/admin/users/guest-admins" },
  { value: "print_manager", label: "Print Managers", path: "/admin/users/print-managers" },
];

const staffKeys = roles.map((role) => ["staff", "users", role.value]);
const emptyStaffForm: StaffForm = {
  username: "",
  email: "",
  first_name: "",
  last_name: "",
  password: "",
  role: "inventory_manager",
  makerspace_id: "",
};
const emptyRestrictForm: RestrictForm = { status: "restricted", reason: "" };
const emptyMakerspaceForm: MakerspaceForm = {
  name: "",
  public_code: "",
  slug: "",
  location: "",
  superadmin_access_enabled: true,
};
const emptyResetPasswordForm: ResetPasswordForm = { password: "" };

export function Users({ makerspaces, isSuperadmin }: { makerspaces: Makerspace[]; isSuperadmin: boolean }) {
  const queryClient = useQueryClient();
  const [activeRole, setActiveRole] = useState<RoleValue>("space_manager");
  const [addOpen, setAddOpen] = useState(false);
  const [makerspaceOpen, setMakerspaceOpen] = useState(false);
  const [staffForm, setStaffForm] = useState<StaffForm>(emptyStaffForm);
  const [makerspaceForm, setMakerspaceForm] = useState<MakerspaceForm>(emptyMakerspaceForm);
  const [restrictTarget, setRestrictTarget] = useState<StaffMembership | null>(null);
  const [restrictForm, setRestrictForm] = useState<RestrictForm>(emptyRestrictForm);
  const [restoreTarget, setRestoreTarget] = useState<StaffMembership | null>(null);
  const [resetPasswordTarget, setResetPasswordTarget] = useState<StaffMembership | null>(null);
  const [resetPasswordForm, setResetPasswordForm] = useState<ResetPasswordForm>(emptyResetPasswordForm);
  const [resetPasswordResult, setResetPasswordResult] = useState<ResetPasswordResult | null>(null);

  const spaceManagers = useStaffGet<StaffListResponse>(["staff", "users", "space_manager"], "/admin/users/space-managers");
  const inventoryManagers = useStaffGet<StaffListResponse>(["staff", "users", "inventory_manager"], "/admin/users/inventory-managers");
  const guestAdmins = useStaffGet<StaffListResponse>(["staff", "users", "guest_admin"], "/admin/users/guest-admins");
  const printManagers = useStaffGet<StaffListResponse>(["staff", "users", "print_manager"], "/admin/users/print-managers");
  const lists = [spaceManagers, inventoryManagers, guestAdmins, printManagers];
  const activeIndex = roles.findIndex((role) => role.value === activeRole);
  const activeRows = staffResults(lists[activeIndex]?.data);
  const makerspaceNames = useMemo(
    () => new Map(makerspaces.map((space) => [space.id, space.name])),
    [makerspaces],
  );
  const invalidateStaff = () => {
    staffKeys.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
  };

  const createStaff = useMutation({
    mutationFn: () => staffRequest(rolePath(staffForm.role), {
      method: "POST",
      body: JSON.stringify(staffPayload(staffForm)),
    }),
    onSuccess: () => {
      setAddOpen(false);
      setStaffForm(emptyStaffForm);
      invalidateStaff();
    },
  });
  const restrict = useMutation({
    mutationFn: () =>
      restrictTarget
        ? staffRequest(`/admin/users/${restrictTarget.user.id}/restrict`, {
            method: "POST",
            body: JSON.stringify({ status: restrictForm.status, reason: restrictForm.reason.trim() }),
          })
        : Promise.resolve(),
    onSuccess: () => {
      setRestrictTarget(null);
      setRestrictForm(emptyRestrictForm);
      invalidateStaff();
    },
  });
  const restore = useMutation({
    mutationFn: (membership: StaffMembership) =>
      staffRequest(`/admin/users/${membership.user.id}/restore-access`, { method: "POST" }),
    onSuccess: () => {
      setRestoreTarget(null);
      invalidateStaff();
    },
  });
  const resetPassword = useMutation({
    mutationFn: () => {
      if (!resetPasswordTarget) {
        throw new Error("No user selected");
      }
      const password = resetPasswordForm.password;
      return staffRequest<ResetPasswordResult>(`/admin/users/${resetPasswordTarget.user.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify(password ? { password } : {}),
      });
    },
    onSuccess: (result) => {
      setResetPasswordResult(result);
      invalidateStaff();
    },
  });
  const createMakerspace = useMutation({
    mutationFn: () =>
      staffRequest("/admin/makerspaces", {
        method: "POST",
        body: JSON.stringify(makerspacePayload(makerspaceForm)),
      }),
    onSuccess: () => {
      setMakerspaceOpen(false);
      setMakerspaceForm(emptyMakerspaceForm);
      queryClient.invalidateQueries({ queryKey: ["staff", "makerspaces"] });
    },
  });

  const openAdd = () => {
    setStaffForm({ ...emptyStaffForm, makerspace_id: makerspaces[0] ? String(makerspaces[0].id) : "" });
    setAddOpen(true);
  };
  const openRestrict = (membership: StaffMembership) => {
    setRestrictTarget(membership);
    setRestrictForm(emptyRestrictForm);
  };
  const openResetPassword = (membership: StaffMembership) => {
    resetPassword.reset();
    setResetPasswordTarget(membership);
    setResetPasswordForm(emptyResetPasswordForm);
    setResetPasswordResult(null);
  };
  const closeResetPassword = () => {
    resetPassword.reset();
    setResetPasswordTarget(null);
    setResetPasswordForm(emptyResetPasswordForm);
    setResetPasswordResult(null);
  };
  const panelError = lists.find((list) => list.error)?.error?.message ?? restore.error?.message;

  return (
    <Panel title="Users">
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-2">
            {roles.map((role, index) => (
              <button
                key={role.value}
                className={`desk-button ${activeRole === role.value ? "border-accent text-accent-ink" : ""}`}
                type="button"
                onClick={() => setActiveRole(role.value)}
              >
                {role.label} ({staffResults(lists[index].data).length})
              </button>
            ))}
          </div>
          <div className="desk-actions ml-auto flex flex-wrap gap-2">
            <button className="desk-button-primary" type="button" onClick={openAdd}>
              Add staff
            </button>
            {isSuperadmin ? (
              <button className="desk-button" type="button" onClick={() => setMakerspaceOpen(true)}>
                Create makerspace
              </button>
            ) : null}
          </div>
        </div>

        {panelError ? <p className="text-sm text-danger">{panelError}</p> : null}
        <StaffTable
          rows={activeRows}
          makerspaceNames={makerspaceNames}
          loading={lists[activeIndex]?.isLoading ?? false}
          onRestrict={openRestrict}
          onRestore={setRestoreTarget}
          onResetPassword={openResetPassword}
        />
      </div>

      <AddStaffModal
        open={addOpen}
        form={staffForm}
        makerspaces={makerspaces}
        pending={createStaff.isPending}
        error={createStaff.error}
        onChange={setStaffForm}
        onClose={() => setAddOpen(false)}
        onSubmit={() => createStaff.mutate()}
      />
      <RestrictUserModal
        open={Boolean(restrictTarget)}
        userLabel={restrictTarget?.user.username ?? ""}
        form={restrictForm}
        pending={restrict.isPending}
        error={restrict.error}
        onChange={setRestrictForm}
        onClose={() => setRestrictTarget(null)}
        onSubmit={() => restrict.mutate()}
      />
      <CreateMakerspaceModal
        open={makerspaceOpen}
        form={makerspaceForm}
        pending={createMakerspace.isPending}
        error={createMakerspace.error}
        onChange={setMakerspaceForm}
        onClose={() => setMakerspaceOpen(false)}
        onSubmit={() => createMakerspace.mutate()}
      />
      <ResetPasswordModal
        open={Boolean(resetPasswordTarget)}
        userLabel={resetPasswordTarget?.user.username ?? ""}
        form={resetPasswordForm}
        pending={resetPassword.isPending}
        error={resetPassword.error}
        result={resetPasswordResult}
        onChange={setResetPasswordForm}
        onClose={closeResetPassword}
        onSubmit={() => resetPassword.mutate()}
      />
      <ConfirmDialog
        open={Boolean(restoreTarget)}
        title="Restore access"
        message={restoreTarget ? `Restore access for ${restoreTarget.user.username}?` : ""}
        confirmLabel="Restore"
        pending={restore.isPending}
        onCancel={() => setRestoreTarget(null)}
        onConfirm={() => {
          if (restoreTarget) restore.mutate(restoreTarget);
        }}
      />
    </Panel>
  );
}

function StaffTable({ rows, makerspaceNames, loading, onRestrict, onRestore, onResetPassword }: {
  rows: StaffMembership[];
  makerspaceNames: Map<number, string>;
  loading: boolean;
  onRestrict: (membership: StaffMembership) => void;
  onRestore: (membership: StaffMembership) => void;
  onResetPassword: (membership: StaffMembership) => void;
}) {
  if (loading) return <p className="text-sm text-muted">Loading staff...</p>;
  if (!rows.length) return <EmptyState title="No staff" description="No memberships exist for this role." />;
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-bg">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-surface text-xs uppercase text-muted">
          <tr className="border-b border-line">
            {["Username", "Email", "Makerspace", "Access", ""].map((header) => (
              <th key={header} className="px-3 py-2 font-semibold">{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((membership) => (
            <tr key={membership.id} className="border-b border-line last:border-b-0">
              <td className="px-3 py-2 font-semibold text-ink"><span className="block max-w-40 break-words">{membership.user.username}</span></td>
              <td className="px-3 py-2 text-muted"><span className="block max-w-56 break-all">{membership.user.email || "-"}</span></td>
              <td className="px-3 py-2 text-ink">
                <span className="block max-w-48 break-words">
                  {makerspaceNames.get(membership.makerspace_id) ?? membership.makerspace_slug}
                </span>
              </td>
              <td className="px-3 py-2"><AccessBadge status={membership.user.access_status} /></td>
              <td className="px-3 py-2">
                <div className="desk-actions flex flex-wrap justify-end gap-2">
                  <button className="desk-button" type="button" onClick={() => onRestrict(membership)}>
                    Restrict
                  </button>
                  <button className="desk-button" type="button" onClick={() => onResetPassword(membership)}>
                    Reset password
                  </button>
                  <button
                    className="desk-button"
                    type="button"
                    disabled={membership.user.access_status === "active"}
                    onClick={() => onRestore(membership)}
                  >
                    Restore
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccessBadge({ status }: { status: string }) {
  const tone = status === "active" ? "success" : status === "restricted" ? "warn" : "danger";
  return <Badge tone={tone}>{status.replace(/_/g, " ")}</Badge>;
}

function staffResults(data?: StaffListResponse) {
  if (!data) return [];
  return Array.isArray(data) ? data : data.results ?? [];
}

function rolePath(role: RoleValue) {
  return roles.find((item) => item.value === role)?.path ?? roles[0].path;
}

function staffPayload(form: StaffForm) {
  return {
    username: form.username.trim(),
    email: form.email.trim(),
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    password: form.password,
    role: form.role,
    makerspace_id: Number(form.makerspace_id),
  };
}

function makerspacePayload(form: MakerspaceForm) {
  return {
    name: form.name.trim(),
    public_code: form.public_code.trim(),
    slug: form.slug.trim(),
    location: form.location.trim(),
    superadmin_access_enabled: form.superadmin_access_enabled,
  };
}
