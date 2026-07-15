export type RuntimeTenantConfig = {
  apiUrl?: string;
  tenantToken?: string;
  // SaaS-only: when true and no tenantToken is set, the app resolves its
  // makerspace by request origin/Host via GET /bootstrap (one branded site per
  // domain). Set exclusively by the SaaS Caddy overlay's config.js. Absent for
  // central/dev/self-host deployments so their behavior stays unchanged.
  originBootstrap?: boolean;
};

declare global {
  interface Window {
    __TENANT__?: RuntimeTenantConfig;
  }
}

function clean(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function runtimeTenantConfig(): RuntimeTenantConfig {
  const config = typeof window === "undefined" ? undefined : window.__TENANT__;
  return {
    apiUrl: clean(config?.apiUrl) || undefined,
    tenantToken: clean(config?.tenantToken) || undefined,
    originBootstrap: config?.originBootstrap === true,
  };
}

export function configuredOriginBootstrap(): boolean {
  return runtimeTenantConfig().originBootstrap === true;
}

export function configuredTenantToken(): string {
  return (
    runtimeTenantConfig().tenantToken ||
    clean(import.meta.env.VITE_TENANT_TOKEN) ||
    ""
  );
}

export function configuredApiUrl(): string {
  return (
    runtimeTenantConfig().apiUrl ||
    clean(import.meta.env.VITE_API_URL) ||
    "http://localhost:8000/api"
  ).replace(/\/+$/, "");
}
