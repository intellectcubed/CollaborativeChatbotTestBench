// The filter shows the lines whose New York date is in the range. It never changes what runs.
export function inFilter(line, filter) {
  const day = line.when.slice(0, 10);
  return (!filter.from || day >= filter.from) && (!filter.to || day <= filter.to);
}

export const isBusy = state => state === "running" || state === "paused";
