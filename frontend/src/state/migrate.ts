/**
 * Runs the storage migration as a side effect of being imported. `main.tsx`
 * imports this module first: the UI store reads its keys when its module is
 * evaluated, so the rename has to have happened before any other import runs.
 */
import { migrateLegacyStorage } from "./storage";

try {
  migrateLegacyStorage();
} catch {
  // No storage in this context (private mode, a sandboxed frame). The defaults
  // are what a first visit gets anyway.
}
