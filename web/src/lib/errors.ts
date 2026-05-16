import type { ZodIssue } from "zod";

export type ErrorMap = Record<string, string>;

export function issuesToMap(issues: ZodIssue[]): ErrorMap {
  const out: ErrorMap = {};
  for (const issue of issues) {
    const key = issue.path.join(".");
    if (!out[key]) out[key] = issue.message;
  }
  return out;
}

export function getError(errors: ErrorMap, path: (string | number)[]): string | null {
  return errors[path.join(".")] || null;
}

export function pathStartsWith(errorKey: string, path: (string | number)[]): boolean {
  const prefix = path.join(".");
  return errorKey === prefix || errorKey.startsWith(prefix + ".");
}

export function hasErrorWithPrefix(errors: ErrorMap, path: (string | number)[]): boolean {
  return Object.keys(errors).some((k) => pathStartsWith(k, path));
}
