import type { CustomAnswerSnapshot, CustomAnswerValue } from "./customFormTypes";

function displayValue(value: CustomAnswerValue) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export function CustomAnswersView({ snapshot }: { snapshot: CustomAnswerSnapshot | null | undefined }) {
  if (!snapshot?.answers.length) {
    return <p className="text-sm text-muted">No custom answers were submitted.</p>;
  }

  return (
    <dl className="grid gap-3">
      {snapshot.answers.map((answer) => (
        <div key={answer.id} className="rounded-lg bg-surface p-3">
          <dt className="text-xs font-semibold text-muted">{answer.label}</dt>
          <dd className="mt-1 whitespace-pre-wrap break-words text-sm text-ink">{displayValue(answer.value)}</dd>
        </div>
      ))}
    </dl>
  );
}
