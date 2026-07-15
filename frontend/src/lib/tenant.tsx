import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  bootstrapTenant,
  setRuntimePublishableKey,
  type TenantBootstrap,
} from "./api";
import { applyTenantBranding } from "./branding";
import { configuredOriginBootstrap, configuredTenantToken } from "./runtimeConfig";

type TenantContextValue =
  | {
      mode: "central";
      loading: false;
      error: null;
      bootstrap: null;
      slug: "";
      makerspaceId: null;
      modules: Set<string>;
    }
  | {
      mode: "single";
      loading: boolean;
      error: Error | null;
      bootstrap: TenantBootstrap | null;
      slug: string;
      makerspaceId: number | null;
      modules: Set<string>;
    };

const TenantContext = createContext<TenantContextValue | null>(null);

const CENTRAL_VALUE: TenantContextValue = {
  mode: "central",
  loading: false,
  error: null,
  bootstrap: null,
  slug: "",
  makerspaceId: null,
  modules: new Set(),
};

export function TenantProvider({ children }: { children: ReactNode }) {
  const tenantToken = configuredTenantToken();
  const hasToken = Boolean(tenantToken);
  // SaaS one-domain-per-makerspace: with no explicit token but the origin-bootstrap
  // flag set, resolve the makerspace from the request origin/Host server-side. The
  // flag keeps central/dev/self-host deployments on the synchronous central path
  // (no extra request, behavior unchanged).
  const originBootstrap = !hasToken && configuredOriginBootstrap();

  const tokenQuery = useQuery({
    queryKey: ["runtime-tenant", tenantToken],
    queryFn: () => bootstrapTenant({ tenant: tenantToken }),
    enabled: hasToken,
    staleTime: Infinity,
  });
  // No tenant/slug params → the backend resolves the makerspace by Origin/Host.
  // retry:false so an unresolved origin (central portal) falls back promptly.
  const originQuery = useQuery({
    queryKey: ["runtime-tenant-origin"],
    queryFn: () => bootstrapTenant({}),
    enabled: originBootstrap,
    staleTime: Infinity,
    retry: false,
  });

  const activeQuery = hasToken ? tokenQuery : originQuery;

  useEffect(() => {
    if (activeQuery.data) {
      setRuntimePublishableKey(activeQuery.data.public_api.publishable_key);
      applyTenantBranding(activeQuery.data);
    }
  }, [activeQuery.data]);

  // Central portal: no token and no origin-bootstrap flag → central directory.
  if (!hasToken && !originBootstrap) {
    return (
      <TenantContext.Provider value={CENTRAL_VALUE}>{children}</TenantContext.Provider>
    );
  }
  // Origin bootstrap that resolved to no makerspace (a genuine 404 — the shared apex
  // has no tenant) falls back to the central directory. Any OTHER failure (network,
  // 5xx) is operational and must surface as a single-tenant error, not silently render
  // the wrong site.
  if (originBootstrap && !originQuery.isLoading && !originQuery.data) {
    const status = (originQuery.error as { status?: number } | null)?.status;
    if (status === 404) {
      return (
        <TenantContext.Provider value={CENTRAL_VALUE}>{children}</TenantContext.Provider>
      );
    }
  }

  const error = activeQuery.error instanceof Error ? activeQuery.error : null;
  const value: TenantContextValue = {
    mode: "single",
    loading: activeQuery.isLoading,
    error,
    bootstrap: activeQuery.data ?? null,
    slug: activeQuery.data?.makerspace.slug ?? "",
    makerspaceId: activeQuery.data?.makerspace.id ?? null,
    modules: new Set(activeQuery.data?.modules ?? []),
  };

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  const value = useContext(TenantContext);
  if (!value) {
    throw new Error("useTenant must be used inside TenantProvider");
  }
  return value;
}

export function tenantPath(mode: "central" | "single", slug: string, subpath = "") {
  const cleanSubpath = subpath.replace(/^\/+/, "");
  if (mode === "single") {
    return cleanSubpath ? `/${cleanSubpath}` : "/";
  }
  return cleanSubpath ? `/m/${slug}/${cleanSubpath}` : `/m/${slug}`;
}

export function useTenantPath(slug: string) {
  const tenant = useTenant();
  return (subpath = "") => tenantPath(tenant.mode, slug, subpath);
}
