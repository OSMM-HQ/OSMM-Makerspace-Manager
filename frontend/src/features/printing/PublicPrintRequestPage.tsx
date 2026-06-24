import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { MakerspaceBrand } from "../../components/MakerspaceBrand";
import { OsmmBadge } from "../../components/OsmmLogo";
import { useTenant, useTenantPath } from "../../lib/tenant";
import { formatSlug } from "../inventory/PublicInventoryParts";
import { useTenantBootstrap } from "../inventory/usePublicInventory";
import {
  PrintDetailsForm,
  initialForm,
  optional,
  type FormState,
} from "./PublicPrintRequestForm";
import {
  fetchPublicSpools,
  fetchPrintStatus,
  fetchPrintStatusByEmail,
  presignPrintUpload,
  submitPrintRequest,
  uploadToStorage,
  verifyPrintCheckin,
  type PrintIdentityBody,
} from "./publicApi";
import {
  PrintAccessErrorPanel,
  PrintAccessLoadingPanel,
  PrintCheckInCard,
  PrintStatusPanel,
  PrintUnavailablePanel,
} from "./PublicPrintRequestPanels";
import { uploadPrintFilesBounded } from "./PublicPrintUploads";

function identityFromForm(form: FormState): PrintIdentityBody {
  return {
    requester_name: form.requesterName.trim(),
    contact_email: form.contactEmail.trim(),
    contact_phone: form.contactPhone.trim(),
  };
}

function identityKey(identity: PrintIdentityBody): string {
  return [
    identity.requester_name,
    identity.contact_email,
    identity.contact_phone,
  ].join("\n");
}

function hasCompleteIdentity(identity: PrintIdentityBody): boolean {
  return Boolean(
    identity.requester_name && identity.contact_email && identity.contact_phone,
  );
}

export function PublicPrintRequestPage() {
  const queryClient = useQueryClient();
  const { slug } = useParams();
  const tenant = useTenant();
  const makerspaceSlug = tenant.mode === "single" ? tenant.slug : slug ?? "";
  const tenantPath = useTenantPath(makerspaceSlug);
  const [verifiedIdentity, setVerifiedIdentity] = useState("");
  const [verifiedName, setVerifiedName] = useState("");
  const [form, setForm] = useState<FormState>(initialForm);
  const [modelFiles, setModelFiles] = useState<File[]>([]);
  const [screenshotFiles, setScreenshotFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [activeStatusToken, setActiveStatusToken] = useState("");
  const [statusEmail, setStatusEmail] = useState("");
  const statusLinkHandledRef = useRef(false);
  const [website, setWebsite] = useState("");

  const bootstrapQuery = useTenantBootstrap(makerspaceSlug, tenant.mode === "central");
  const bootstrap = tenant.mode === "single" ? tenant.bootstrap : bootstrapQuery.data;
  const modules = useMemo(
    () => (tenant.mode === "single" ? tenant.modules : new Set(bootstrap?.modules ?? [])),
    [bootstrap?.modules, tenant],
  );
  const enabled = modules.has("printing");
  const currentIdentity = identityFromForm(form);
  const currentIdentityKey = identityKey(currentIdentity);
  const verified = hasCompleteIdentity(currentIdentity) &&
    currentIdentityKey === verifiedIdentity;
  const displayName =
    bootstrap?.branding.display_name ||
    bootstrap?.makerspace.name ||
    formatSlug(makerspaceSlug) ||
    "Makerspace";

  const spoolsQuery = useQuery({
    queryKey: ["public-print-spools", makerspaceSlug],
    queryFn: () => fetchPublicSpools(makerspaceSlug),
    enabled: Boolean(makerspaceSlug) && enabled,
  });
  const statusQuery = useQuery({
    queryKey: ["public-print-status", activeStatusToken],
    queryFn: () => fetchPrintStatus(activeStatusToken),
    enabled: Boolean(activeStatusToken),
    refetchInterval: (query) =>
      query.state.data?.status === "printing" ? 30_000 : false,
  });
  const statusByEmailMutation = useMutation({
    mutationFn: (email: string) =>
      fetchPrintStatusByEmail(makerspaceSlug, email.trim()),
  });
  const verifyMutation = useMutation({
    mutationFn: (identity: PrintIdentityBody) =>
      verifyPrintCheckin(makerspaceSlug, identity),
    onSuccess: (data, identity) => {
      setVerifiedIdentity(identityKey(identity));
      setVerifiedName(data.username);
    },
  });

  useEffect(() => {
    if (statusLinkHandledRef.current) return;
    statusLinkHandledRef.current = true;
    const token = new URLSearchParams(window.location.search).get("token")?.trim();
    if (token) setActiveStatusToken(token);
  }, []);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateIdentityField(
    key: "requesterName" | "contactEmail" | "contactPhone",
    value: string,
  ) {
    const nextForm = { ...form, [key]: value };
    updateField(key, value);
    if (identityKey(identityFromForm(nextForm)) !== verifiedIdentity) {
      setVerifiedIdentity("");
      setVerifiedName("");
      verifyMutation.reset();
    }
  }

  const submitMutation = useMutation({
    mutationFn: async () => {
      const identity = identityFromForm(form);
      const files = [
        ...modelFiles.map((file) => ({ file, kind: "stl" as const })),
        ...screenshotFiles.map((file) => ({ file, kind: "screenshot" as const })),
      ];
      const fileIds = await uploadPrintFilesBounded(files, async (item) => {
        const presigned = await presignPrintUpload(makerspaceSlug, {
          ...identity,
          kind: item.kind,
          filename: item.file.name,
          content_type:
            item.kind === "stl"
              ? item.file.type || "application/octet-stream"
              : item.file.type,
        });
        await uploadToStorage(presigned.upload, item.file);
        return presigned.file_id;
      }, setUploadProgress);

      setUploadProgress(files.length ? "Submitting request..." : "");
      const chosenSpool = spoolsQuery.data?.find(
        (spool) => String(spool.id) === form.filamentSpoolId,
      );
      return submitPrintRequest(makerspaceSlug, {
        ...identity,
        website,
        title: form.title.trim(),
        project_brief: optional(form.projectBrief),
        preferred_settings: optional(form.preferredSettings),
        material: chosenSpool?.material || undefined,
        color: chosenSpool?.color || undefined,
        filament_spool_id: form.filamentSpoolId
          ? Number(form.filamentSpoolId)
          : null,
        quantity: form.quantity,
        source_link: optional(form.sourceLink),
        file_ids: fileIds,
      });
    },
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["public-print-spools", makerspaceSlug] });
      queryClient.invalidateQueries({ queryKey: ["public-print-status"] });
      setUploadProgress("");
      setSubmitted(true);
      setStatusEmail(form.contactEmail.trim());
      setActiveStatusToken(response.public_token);
    },
    onError: () => setUploadProgress(""),
  });

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (verified && form.title.trim()) submitMutation.mutate();
  }

  function checkStatusByEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (statusEmail.trim()) statusByEmailMutation.mutate(statusEmail.trim());
  }

  return (
    <main className="desk-shell">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-screen-xl flex-col gap-4 px-5 py-6 sm:px-8">
          <p className="text-sm font-semibold tracking-wide text-accent-ink">
            Public 3D Print Request
          </p>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <MakerspaceBrand
                name={displayName}
                logoUrl={bootstrap?.makerspace.logo_url}
                size="lg"
              />
              <p className="mt-2 text-sm text-muted">
                Submit print files - check status anytime with your email.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <OsmmBadge />
              <Link className="desk-button" to={tenantPath()}>
                Back to inventory
              </Link>
            </div>
          </div>
        </div>
      </header>

      {bootstrapQuery.isLoading ? <PrintAccessLoadingPanel /> : null}
      {bootstrapQuery.isError ? <PrintAccessErrorPanel /> : null}

      {!bootstrapQuery.isLoading && !bootstrapQuery.isError && !enabled ? (
        <PrintUnavailablePanel
          catalogPath={tenantPath()}
          tokenStatus={statusQuery.data}
          tokenStatusPending={Boolean(activeStatusToken) && statusQuery.isPending}
          tokenStatusError={statusQuery.error}
        />
      ) : null}

      {!bootstrapQuery.isLoading && !bootstrapQuery.isError && enabled ? (
        <section className="mx-auto grid max-w-screen-xl grid-cols-1 gap-5 px-5 py-6 sm:px-8 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-4">
            <PrintCheckInCard
              form={form}
              verified={verified}
              verifiedName={verifiedName}
              verifyPending={verifyMutation.isPending}
              verifyError={verifyMutation.error}
              onRequesterNameChange={(value) => updateIdentityField("requesterName", value)}
              onContactEmailChange={(value) => updateIdentityField("contactEmail", value)}
              onContactPhoneChange={(value) => updateIdentityField("contactPhone", value)}
              onVerify={() => verifyMutation.mutate(currentIdentity)}
            />
            <PrintDetailsForm
              form={form}
              updateField={updateField}
              spoolsQuery={spoolsQuery}
              modelFiles={modelFiles}
              setModelFiles={setModelFiles}
              screenshotFiles={screenshotFiles}
              setScreenshotFiles={setScreenshotFiles}
              verified={verified}
              submitPending={submitMutation.isPending}
              submitError={submitMutation.error}
              uploadProgress={uploadProgress}
              website={website}
              onWebsiteChange={setWebsite}
              onSubmit={submitForm}
            />
          </div>

          <aside className="min-w-0 space-y-4 lg:sticky lg:top-0 lg:max-h-[100dvh] lg:overflow-y-auto">
            <PrintStatusPanel
              submitted={submitted}
              statusEmail={statusEmail}
              statusEmailPending={statusByEmailMutation.isPending}
              statusEmailError={statusByEmailMutation.error}
              statusEmailResults={statusByEmailMutation.data?.results}
              tokenStatus={statusQuery.data}
              tokenStatusPending={Boolean(activeStatusToken) && statusQuery.isPending}
              tokenStatusError={statusQuery.error}
              onStatusEmailChange={setStatusEmail}
              onSubmitStatusEmail={checkStatusByEmail}
            />
          </aside>
        </section>
      ) : null}
    </main>
  );
}
