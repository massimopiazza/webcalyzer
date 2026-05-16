import { useEffect, useState } from "react";
import { api, Meta } from "./api";

let cached: Meta | null = null;
let pending: Promise<Meta> | null = null;
const subscribers = new Set<(m: Meta) => void>();

function fetchMeta() {
  if (!pending) {
    pending = api.meta().then((m) => {
      cached = m;
      subscribers.forEach((sub) => sub(m));
      return m;
    });
  }
  return pending;
}

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(cached);
  useEffect(() => {
    let active = true;
    if (!cached) {
      fetchMeta().then((m) => {
        if (active) setMeta(m);
      });
    } else {
      setMeta(cached);
    }
    const sub = (m: Meta) => {
      if (active) setMeta(m);
    };
    subscribers.add(sub);
    return () => {
      active = false;
      subscribers.delete(sub);
    };
  }, []);
  return meta;
}

export function getCachedMeta() {
  return cached;
}
