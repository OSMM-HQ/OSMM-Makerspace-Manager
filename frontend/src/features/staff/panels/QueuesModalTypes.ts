import type { HardwareRequest } from "./Queues";

export type ReturnDueValues = {
  returnDueAt: string;
};

export type RejectRequestValues = {
  reason: string;
};

export type IssueReject = {
  item_id: number;
  broken: number;
  disposition: "needs_fix" | "remove";
};

export type AssignIssueValues = {
  boxCode: string;
  evidenceId: number;
  remark: string;
  rejects: IssueReject[];
  assetQrPayloads: string[];
};

export type AssetReturnOutcome = "returned" | "damaged" | "missing";

export type ReturnRequestValues = {
  evidenceId: number;
  boxCode: string;
  remark: string;
  resolutions: Array<{
    item_id: number;
    returned: number;
    damaged: number;
    missing: number;
    assets?: Array<{ asset_id: number; outcome: AssetReturnOutcome }>;
  }>;
};

export type FormModalProps<T> = {
  row: HardwareRequest | null;
  open: boolean;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (values: T) => void;
};
