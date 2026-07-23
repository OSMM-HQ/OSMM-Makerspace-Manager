export type RuleCatalogEntry = {
  stream: string;
  audience: string;
  targets: string[];
  events: string[];
};

export type RuleMute = {
  target: string;
  stream: string;
  event: string;
  audience: string;
};

export type NotificationChannel = {
  key: string;
  label: string;
};

export type NotificationFeature = {
  key: string;
  label: string;
  events: string[];
};

export type NotificationPreferenceCell = {
  feature: string;
  channel: string;
  enabled: boolean;
  source: "default" | "override";
};

export type NotificationRulesResponse = {
  catalog: RuleCatalogEntry[];
  mutes: RuleMute[];
  channels: NotificationChannel[];
  features: NotificationFeature[];
  preferences: NotificationPreferenceCell[];
};

export type MuteChange = RuleMute & {
  muted: boolean;
};

export type PreferenceChange = {
  feature: string;
  channel: string;
  enabled: boolean;
};
