import type { User } from "./user";
import { type Config, runtime as localRuntime } from "./mixed";
import { type Only } from "./only-types";
export type { Model } from "./model";
export { type Shape, make as create } from "./factory";
type Lazy = typeof import("./type-query");
const runtime = import("./runtime");
export type { User, Config, Only };
export { localRuntime, runtime };
