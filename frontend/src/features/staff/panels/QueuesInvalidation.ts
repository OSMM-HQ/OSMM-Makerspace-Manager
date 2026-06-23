import type { QueryClient } from "@tanstack/react-query";
import { invalidateInventoryViews } from "../queryInvalidation";

export type InvalidationScope = {
  inventory: boolean;
  needsFix: boolean;
  ledger: boolean;
};

export function actionInvalidationScope(path: string): InvalidationScope {
  const inventory = path.endsWith("/accept") || path.endsWith("/issue") || path.endsWith("/return");
  const ledger = path.endsWith("/issue") || path.endsWith("/return") || path.endsWith("/return-due");
  const needsFix = path.endsWith("/issue") || path.endsWith("/return");
  return { inventory, ledger, needsFix };
}

export function invalidateRequestQueues(queryClient: QueryClient, makerspaceId: number, scope: InvalidationScope) {
  queryClient.invalidateQueries({ queryKey: ["pending", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["accepted", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["active", makerspaceId] });
  queryClient.invalidateQueries({ queryKey: ["request-history", makerspaceId] });

  if (scope.inventory) {
    invalidateInventoryViews(queryClient, makerspaceId);
  }
  if (scope.needsFix) {
    queryClient.invalidateQueries({ queryKey: ["needs-fix-shelf", makerspaceId] });
  }
  if (scope.ledger) {
    queryClient.invalidateQueries({ queryKey: ["ledger", makerspaceId] });
    queryClient.invalidateQueries({ queryKey: ["ledger", "all"] });
  }
}
