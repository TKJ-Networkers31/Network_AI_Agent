/**
 * src/utils/capabilityInvoke.js
 *
 * Universal Action Dispatcher for VERA.
 * Delegates to ActionRegistry to execute typed actions, capabilities,
 * recovery operations, and tool invocations safely with complete error handling.
 */

import { executeTypedAction } from "../platform/adaptive-experience/interactions/ActionRegistry.js";

export async function invokeCapability(capability, helpers = {}) {
  const result = await executeTypedAction(capability, helpers);
  return result?.success ?? false;
}
