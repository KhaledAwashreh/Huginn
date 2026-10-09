/** Keep uncollected values (and duplicate saved rows) unless the user removes them. */
export function mergeCollectedValues<T>(
  current: T[],
  selected: string[],
  getValue: (row: T) => string,
  makeRow: (value: string) => T,
): T[] {
  const selectedSet = new Set(selected);
  const kept = current.filter((row) => selectedSet.has(getValue(row)));
  const existing = new Set(current.map(getValue));
  for (const value of selected) {
    if (!existing.has(value)) {
      kept.push(makeRow(value));
      existing.add(value);
    }
  }
  return kept;
}

export function mergeCollectedExclusions<T extends { kind: string }>(
  allRows: T[],
  selectedValues: string[],
  getValue: (row: T) => string | undefined,
  makeRow: (value: string) => T,
): T[] {
  const selected = new Set(selectedValues);
  const kept = allRows.filter((row) => {
    const value = getValue(row);
    return value === undefined || selected.has(value);
  });
  const existing = new Set(
    allRows.map(getValue).filter((value): value is string => value !== undefined),
  );
  for (const value of selectedValues) {
    if (!existing.has(value)) {
      kept.push(makeRow(value));
      existing.add(value);
    }
  }
  return kept;
}
