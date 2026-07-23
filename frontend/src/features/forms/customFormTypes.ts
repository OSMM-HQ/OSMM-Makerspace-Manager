export const CUSTOM_QUESTION_TYPES = [
  "short_text",
  "paragraph",
  "number",
  "date",
  "single_choice",
  "multi_choice",
  "dropdown",
  "yes_no",
] as const;

export type CustomQuestionType = (typeof CUSTOM_QUESTION_TYPES)[number];

export type CustomFormQuestion = {
  id: string;
  label: string;
  type: CustomQuestionType;
  options: string[];
  required: boolean;
};

export type CustomFormSchema = CustomFormQuestion[] | null;
export type CustomAnswerValue = string | number | boolean | string[];
export type CustomAnswers = Partial<Record<string, CustomAnswerValue>>;

export type StoredCustomAnswer = {
  id: string;
  label: string;
  type: CustomQuestionType;
  value: CustomAnswerValue;
};

export type CustomAnswerSnapshot = {
  version: 1;
  answers: StoredCustomAnswer[];
};

export const CHOICE_QUESTION_TYPES = new Set<CustomQuestionType>([
  "single_choice",
  "multi_choice",
  "dropdown",
]);

export const QUESTION_TYPE_LABELS: Record<CustomQuestionType, string> = {
  short_text: "Short text",
  paragraph: "Paragraph",
  number: "Number",
  date: "Date",
  single_choice: "Single choice",
  multi_choice: "Multiple choice",
  dropdown: "Dropdown",
  yes_no: "Yes / No",
};

export function customAnswerErrors(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, detail]) => {
      const messages = Array.isArray(detail) ? detail : [detail];
      const text = messages.filter((item): item is string => typeof item === "string").join(" ");
      return text ? [[key, text]] : [];
    }),
  );
}

export function validateCustomAnswers(schema: CustomFormSchema, answers: CustomAnswers) {
  const errors: Record<string, string> = {};
  for (const question of schema ?? []) {
    const value = answers[question.id];
    const empty = value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
    if (question.required && empty) {
      errors[question.id] = "This question is required.";
    } else if (question.type === "number" && !empty && !Number.isFinite(Number(value))) {
      errors[question.id] = "Enter a valid number.";
    }
  }
  return errors;
}
