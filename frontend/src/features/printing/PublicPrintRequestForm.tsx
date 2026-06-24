import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import { FilePicker, TextArea, TextInput } from "./PublicPrintRequestParts";
import type { PublicFilamentSpool } from "./publicApi";

export type FormState = {
  requesterName: string;
  title: string;
  projectBrief: string;
  preferredSettings: string;
  filamentSpoolId: string;
  material: string;
  color: string;
  quantity: number;
  sourceLink: string;
  contactEmail: string;
  contactPhone: string;
};

export const initialForm: FormState = {
  requesterName: "",
  title: "",
  projectBrief: "",
  preferredSettings: "",
  filamentSpoolId: "",
  material: "",
  color: "",
  quantity: 1,
  sourceLink: "",
  contactEmail: "",
  contactPhone: "",
};

export function optional(value: string) {
  const trimmed = value.trim();
  return trimmed || undefined;
}

// Group active spools by material so same-material filaments are listed together and
// distinguished by color (the public /spools endpoint already orders by material,color).
export function groupSpoolsByMaterial(
  spools: PublicFilamentSpool[],
): [string, PublicFilamentSpool[]][] {
  const groups = new Map<string, PublicFilamentSpool[]>();
  for (const spool of spools) {
    const key = spool.material || "Other";
    const bucket = groups.get(key);
    if (bucket) bucket.push(spool);
    else groups.set(key, [spool]);
  }
  return [...groups.entries()];
}

type PrintDetailsFormProps = {
  form: FormState;
  updateField: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  spoolsQuery: UseQueryResult<PublicFilamentSpool[], Error>;
  modelFiles: File[];
  setModelFiles: Dispatch<SetStateAction<File[]>>;
  screenshotFiles: File[];
  setScreenshotFiles: Dispatch<SetStateAction<File[]>>;
  verified: boolean;
  submitPending: boolean;
  submitError?: Error | null;
  uploadProgress: string;
  website: string;
  onWebsiteChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function PrintDetailsForm({
  form,
  updateField,
  spoolsQuery,
  modelFiles,
  setModelFiles,
  screenshotFiles,
  setScreenshotFiles,
  verified,
  submitPending,
  submitError,
  uploadProgress,
  website,
  onWebsiteChange,
  onSubmit,
}: PrintDetailsFormProps) {
  return (
    <Card>
      <p className="text-xs font-semibold tracking-wide text-accent-ink">
        Print Details
      </p>
      <form className="mt-4 space-y-4" onSubmit={onSubmit}>
        {/* Honeypot: hidden from humans; bots that autofill it trigger the server decoy. */}
        <input
          aria-hidden="true"
          autoComplete="off"
          className="hidden"
          name="website"
          tabIndex={-1}
          value={website}
          onChange={(event) => onWebsiteChange(event.target.value)}
        />
        <fieldset className="space-y-4" disabled={!verified || submitPending}>
          <TextInput
            label="Title"
            required
            value={form.title}
            onChange={(value) => updateField("title", value)}
          />
          <TextArea
            label="Project brief"
            value={form.projectBrief}
            onChange={(value) => updateField("projectBrief", value)}
          />
          <TextArea
            label="Slicer settings / personal preferences"
            value={form.preferredSettings}
            onChange={(value) => updateField("preferredSettings", value)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Filament / material
              </span>
              <select
                className="desk-input w-full"
                value={form.filamentSpoolId}
                onChange={(event) =>
                  updateField("filamentSpoolId", event.target.value)
                }
              >
                <option value="">No preference</option>
                {groupSpoolsByMaterial(spoolsQuery.data ?? []).map(([material, spools]) => (
                  <optgroup key={material} label={material}>
                    {spools.map((spool) => (
                      <option key={spool.id} value={spool.id}>
                        {spool.color || "Default color"}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {spoolsQuery.isLoading ? (
                <p className="mt-1 text-xs text-muted">Loading filament...</p>
              ) : null}
              {spoolsQuery.isError ? (
                <p className="mt-1 text-xs text-danger">
                  {spoolsQuery.error.message}
                </p>
              ) : null}
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold tracking-wide text-muted">
                Quantity
              </span>
              <input
                className="desk-input w-full"
                min={1}
                type="number"
                value={form.quantity}
                onChange={(event) =>
                  updateField("quantity", Math.max(1, Number(event.target.value) || 1))
                }
              />
            </label>
            <TextInput label="Source link (optional)" value={form.sourceLink} onChange={(value) => updateField("sourceLink", value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <FilePicker
              accept=".stl,.3mf,.step,.stp,.obj"
              files={modelFiles}
              label="STL/model files"
              setFiles={setModelFiles}
            />
            <FilePicker
              accept="image/*,application/pdf"
              files={screenshotFiles}
              label="Estimated print-time screenshots (Bambu Lab)"
              setFiles={setScreenshotFiles}
            />
          </div>
        </fieldset>

        {!verified ? (
          <p className="rounded-lg border border-tone-yellow bg-tone-yellow px-3 py-2 text-sm font-medium text-tone-yellow-ink dark:bg-[#332b00] dark:text-[#fcdf46]">
            Verify your Check-In before submitting a print request.
          </p>
        ) : null}
        {uploadProgress ? <p className="text-sm text-muted">{uploadProgress}</p> : null}
        {submitError ? (
          <p className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {submitError.message}
          </p>
        ) : null}
        <button
          className="desk-button-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
          disabled={
            !verified ||
            !form.requesterName.trim() ||
            !form.contactEmail.trim() ||
            !form.contactPhone.trim() ||
            !form.title.trim() ||
            submitPending
          }
          type="submit"
        >
          {submitPending ? "Submitting..." : "Submit print request"}
        </button>
      </form>
    </Card>
  );
}
