import type { ConsentKind, ConsentRecord } from "@smaran/contracts";

export interface ConsentChoices {
  camera: boolean;
  mic: boolean;
  data_sharing: boolean;
}

/** Current consent per kind, derived from server ConsentRecords (kind, granted, ts). Default: all off. */
export type ConsentState = ConsentChoices;

export const NO_CONSENT: ConsentState = { camera: false, mic: false, data_sharing: false };

/** Latest record per kind wins. Unknown/missing kind => not granted. */
export function consentFromRecords(records: ConsentRecord[]): ConsentState {
  const latest: Partial<Record<ConsentKind, ConsentRecord>> = {};
  for (const r of records) {
    const cur = latest[r.kind];
    if (!cur || r.ts > cur.ts) latest[r.kind] = r;
  }
  return {
    camera: latest.camera?.granted === true,
    mic: latest.mic?.granted === true,
    data_sharing: latest.data_sharing?.granted === true
  };
}

/** Camera/mic/emotion capture must never run without an explicit, current, server-recorded consent. */
export function hasValidConsent(consent: ConsentState | undefined, need: "camera" | "mic"): boolean {
  if (!consent) return false;
  return need === "camera" ? consent.camera : consent.mic;
}

/** One POST /patients/{id}/consents body per kind. */
export function buildConsentRequests(choices: ConsentChoices): Array<{ kind: ConsentKind; granted: boolean }> {
  return [
    { kind: "data_sharing", granted: choices.data_sharing },
    { kind: "camera", granted: choices.camera },
    { kind: "mic", granted: choices.mic }
  ];
}

/** DPDP Act 2023 alignment: data_sharing is a required answer; camera/mic default off. */
export function isConsentComplete(choices: Partial<ConsentChoices>): boolean {
  return typeof choices.data_sharing === "boolean";
}
