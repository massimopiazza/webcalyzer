import { useCallback, useMemo, useState } from "react";
import { Profile, profileSchema, runnableProfileSchema } from "./schema";
import { ErrorMap, issuesToMap } from "./errors";

export type ProfileFormState = {
  profile: Profile;
  errors: ErrorMap;
  runnableErrors: ErrorMap;
  isValid: boolean;
  isRunnable: boolean;
  setProfile: (next: Profile | ((prev: Profile) => Profile)) => void;
  patch: (path: (string | number)[], value: unknown) => void;
  reset: (next: Profile) => void;
};

export function useProfileForm(initial: Profile): ProfileFormState {
  const [profile, setProfile] = useState<Profile>(initial);

  const errors = useMemo(() => {
    const result = profileSchema.safeParse(profile);
    return result.success ? {} : issuesToMap(result.error.issues);
  }, [profile]);

  const runnableErrors = useMemo(() => {
    const result = runnableProfileSchema.safeParse(profile);
    return result.success ? {} : issuesToMap(result.error.issues);
  }, [profile]);

  const patch = useCallback((path: (string | number)[], value: unknown) => {
    setProfile((prev) => updatePath(prev, path, value));
  }, []);

  const reset = useCallback((next: Profile) => {
    setProfile(next);
  }, []);

  return {
    profile,
    errors,
    runnableErrors,
    isValid: Object.keys(errors).length === 0,
    isRunnable: Object.keys(runnableErrors).length === 0,
    setProfile,
    patch,
    reset,
  };
}

function updatePath<T>(source: T, path: (string | number)[], value: unknown): T {
  if (path.length === 0) return value as T;
  const [head, ...rest] = path;
  if (typeof head === "number" || (typeof head === "string" && /^\d+$/.test(head))) {
    const arr = Array.isArray(source) ? [...(source as unknown[])] : [];
    const idx = typeof head === "number" ? head : parseInt(head, 10);
    arr[idx] = updatePath(arr[idx], rest, value);
    return arr as unknown as T;
  }
  const obj = (source && typeof source === "object" ? { ...(source as object) } : {}) as Record<
    string,
    unknown
  >;
  obj[head as string] = updatePath(obj[head as string], rest, value);
  return obj as unknown as T;
}
