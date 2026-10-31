import { useEffect, useState } from "react";

/** Minimal hash router — no dependency. Returns the path after "#/". */
export function useHashRoute(): string {
  const read = () => window.location.hash.replace(/^#\/?/, "") || "today";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onHash = () => setRoute(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route.split("/")[0];
}

export function navigate(route: string, param?: string): void {
  const hash = param ? `#/${route}/${param}` : `#/${route}`;
  if (window.location.hash !== hash) {
    window.location.hash = hash;
  }
}

/** The segment after the route, e.g. "applied" in "#/jobs/applied" — used to deep-link a status filter. */
export function useHashParam(): string {
  const read = () => window.location.hash.split("/")[2] || "";
  const [param, setParam] = useState(read);
  useEffect(() => {
    const onHash = () => setParam(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return param;
}

type Async<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Fetch-on-mount with a manual reload + a bump counter for refresh-all. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((value) => alive && (setData(value), setError(null)))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}

const CHAMELEON_UPDATE_KEY = "jobhunt.chameleon.update.v1";

export function useChameleonUpdateSplash(): [boolean, () => void] {
  const [show, setShow] = useState(() => !window.localStorage.getItem(CHAMELEON_UPDATE_KEY));
  const dismiss = () => {
    window.localStorage.setItem(CHAMELEON_UPDATE_KEY, "1");
    setShow(false);
  };
  return [show, dismiss];
}

const COLLAPSED_COLUMNS_KEY = "jobhunt.pipeline.collapsed";

/** Which Pipeline kanban columns are collapsed, remembered across reloads. */
export function useCollapsedColumns(): [Set<string>, (status: string) => void] {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(window.localStorage.getItem(COLLAPSED_COLUMNS_KEY) || "[]"));
    } catch {
      return new Set();
    }
  });
  const toggle = (status: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      window.localStorage.setItem(COLLAPSED_COLUMNS_KEY, JSON.stringify([...next]));
      return next;
    });
  };
  return [collapsed, toggle];
}

const SEEN_INTERVIEWS_KEY = "jobhunt.interviews.seen.v1";

/** Job ids already acknowledged at interviewing/offer, so the milestone banner fires once per job, not once per page load. */
export function useSeenInterviewIds(): [Set<number>, (id: number) => void] {
  const [seen, setSeen] = useState<Set<number>>(() => {
    try {
      return new Set(JSON.parse(window.localStorage.getItem(SEEN_INTERVIEWS_KEY) || "[]"));
    } catch {
      return new Set();
    }
  });
  const markSeen = (id: number) => {
    setSeen((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      window.localStorage.setItem(SEEN_INTERVIEWS_KEY, JSON.stringify([...next]));
      return next;
    });
  };
  return [seen, markSeen];
}
