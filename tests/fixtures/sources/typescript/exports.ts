export type Model = { id: string };
export interface Service { run(): void }
export const value = 1;
export { value as renamed, type Model };
export default value;
