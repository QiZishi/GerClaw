import { gerclawRequest } from "./client";
import {
  capabilityCatalogSchema,
  type CapabilityManifest,
} from "./capabilities-contract";

export async function listCapabilities(): Promise<CapabilityManifest[]> {
  const result = await gerclawRequest("capabilities", capabilityCatalogSchema);
  return result.capabilities;
}
