export type FeatureDefinition = {
  key: string;
  // null => standalone feature with no parent-module prerequisite (always toggleable).
  parent_module: string | null;
  label: string;
};

export const FEATURE_DEFINITIONS: readonly FeatureDefinition[] = [
  { key: "payments.machines", parent_module: "machines", label: "Machine payments" },
  { key: "payments.bookings", parent_module: "bookings", label: "Booking payments" },
  { key: "payments.events", parent_module: "events", label: "Event payments" },
  { key: "payments.membership", parent_module: "membership", label: "Membership payments" },
  { key: "inventory.self_checkout", parent_module: null, label: "Self checkout" },
];

export function featureEnabled(features: Iterable<string>, key: string) {
  return new Set(features).has(key);
}