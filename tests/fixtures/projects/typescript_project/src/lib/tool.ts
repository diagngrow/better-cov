export interface Options {}

export function run(selected: boolean): number {
  if (selected) return 1;
  return 0;
}

export function unused(): number {
  return 2;
}
