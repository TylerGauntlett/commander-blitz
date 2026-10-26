/**
 * A player's energy counters (107.14), as a chip beside their name.
 *
 * Drawn only while there is energy: nearly every deck never makes any, and a
 * chip reading zero on every seat would be one more mark saying nothing. It
 * sits inline in a row that already has a fixed height, so arriving costs no
 * reflow.
 */

export function EnergyChip({ pid, energy }: { pid: number; energy: number }) {
  if (energy <= 0) return null;
  const hint = `${energy} energy`;
  return (
    <span className="energy-chip tabular" data-testid={`energy-${pid}`} data-hint={hint}>
      <span className="energy-chip__mark" aria-hidden="true">
        E
      </span>
      {energy}
    </span>
  );
}
