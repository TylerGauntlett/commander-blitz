/**
 * The app's localStorage keys are `commanderblitz.<name>`. They were
 * `automtg.*` before the rename, and those keys are a returning player's
 * imported library, their settings and the pod they were sitting in -- so the
 * first load after the rename moves each old key to its new name, once, and
 * removes the old one. A new key that already exists wins: nothing a player
 * has done since is overwritten by what they had before.
 */

export const STORAGE_PREFIX = "commanderblitz.";
const LEGACY_PREFIX = "automtg.";

/**
 * Rename every `automtg.*` key to `commanderblitz.*`. Returns how many moved.
 * Safe to call on every boot: with nothing left to move it reads the key
 * list and does nothing else.
 */
export function migrateLegacyStorage(storage: Storage = window.localStorage): number {
  const legacy: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key?.startsWith(LEGACY_PREFIX)) legacy.push(key);
  }
  let moved = 0;
  for (const oldKey of legacy) {
    const newKey = STORAGE_PREFIX + oldKey.slice(LEGACY_PREFIX.length);
    const value = storage.getItem(oldKey);
    if (value !== null && storage.getItem(newKey) === null) {
      storage.setItem(newKey, value);
      moved++;
    }
    storage.removeItem(oldKey);
  }
  return moved;
}
