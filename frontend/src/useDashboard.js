import { mergeAllLayout } from "./layout.js";
import { useCallback, useEffect, useRef, useState } from "react";
export function readProfile() {
  try {
    const value = document.cookie
      .split(";")
      .map((v) => v.trim())
      .find((v) => v.startsWith("dashboard_profile="))
      ?.split("=")[1];
    return /^(admin|p-[0-9a-f]{24})$/.test(value) ? value : "admin";
  } catch {
    return "admin";
  }
}
export function rememberProfile(id) {
  try {
    document.cookie = `dashboard_profile=${id}; Path=/; SameSite=Lax`;
  } catch {
    /* Page session still works without cookies. */
  }
}
export default function useDashboard() {
  const [credential, setCredential] = useState(""),
    [profile, setProfile] = useState(readProfile),
    [snapshot, setSnapshot] = useState(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const cookie = useRef(readProfile()),
    epoch = useRef(0),
    controllers = useRef(new Set()),
    configRef = useRef(null),
    hold = useRef(false),
    nowProfile = useRef(profile),
    nowCredential = useRef(credential);
  nowProfile.current = profile;
  nowCredential.current = credential;
  const request = useCallback(async (path, options = {}) => {
    const generation = epoch.current,
      selected = nowProfile.current,
      c = new AbortController();
    controllers.current.add(c);
    const external = options.signal;
    const abort = () => c.abort();
    if (external?.aborted) c.abort();
    else external?.addEventListener("abort", abort, { once: true });
    try {
      const r = await fetch(path, {
        ...options,
        signal: c.signal,
        headers: {
          Authorization: "Bearer " + nowCredential.current,
          "Content-Type": "application/json",
          "X-Dashboard-Profile": selected,
          ...options.headers,
        },
      });
      const data = await r.json();
      if (generation !== epoch.current)
        throw new DOMException("Session changed", "AbortError");
      if (!r.ok) {
        const e = Error(data.error?.message || data.error || "Request failed");
        e.status = r.status;
        throw e;
      }
      const resolved = r.headers.get("X-Dashboard-Profile");
      if (resolved && resolved !== selected) {
        epoch.current++;
        for (const pending of controllers.current) pending.abort();
        hold.current = false;
        configRef.current = null;
        setSnapshot(null);
        setError("");
        setProfile(resolved);
        rememberProfile(resolved);
        cookie.current = readProfile();
        throw new DOMException("Profile changed", "AbortError");
      }
      return { data, etag: r.headers.get("ETag") };
    } finally {
      external?.removeEventListener("abort", abort);
      controllers.current.delete(c);
    }
  }, []);
  const cancel = () => {
    epoch.current++;
    for (const c of controllers.current) c.abort();
    controllers.current.clear();
  };
  const disconnect = () => {
    cancel();
    nowCredential.current = "";
    setCredential("");
    setSnapshot(null);
    setError("");
    configRef.current = null;
    hold.current = false;
  };
  const connect = (value) => {
    cancel();
    setSnapshot(null);
    configRef.current = null;
    setError("");
    setCredential(value.trim());
    setProfile(readProfile());
    cookie.current = readProfile();
  };
  const chooseProfile = (id) => {
    cancel();
    hold.current = false;
    configRef.current = null;
    setSnapshot(null);
    setError("");
    setProfile(id);
    rememberProfile(id);
    cookie.current = readProfile();
  };
  useEffect(() => {
    if (!credential) return;
    let stopped = false,
      timer;
    const refresh = async () => {
      if (readProfile() !== cookie.current) {
        chooseProfile(readProfile());
        return;
      }
      setLoading(true);
      try {
        const [state, configuration, devices, profiles] = await Promise.all(
          [
            "/api/v1/state",
            "/api/v2/configuration",
            "/api/v2/devices",
            "/api/v2/profiles",
          ].map((p) => request(p)),
        );
        if (stopped) return;
        if (!hold.current || !configRef.current)
          configRef.current = configuration;
        setSnapshot({
          state: state.data,
          configuration: configRef.current,
          devices: devices.data.devices,
          profiles: profiles.data.profiles,
          fetched: Date.now(),
        });
        setError("");
      } catch (e) {
        if (!stopped && e.name !== "AbortError") setError(e.message);
      } finally {
        if (!stopped) {
          setLoading(false);
          timer = setTimeout(refresh, document.hidden ? 15000 : 4000);
        }
      }
    };
    refresh();
    const focus = () => {
      const id = readProfile();
      if (id !== cookie.current) chooseProfile(id);
    };
    window.addEventListener("focus", focus);
    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener("focus", focus);
      cancel();
    };
  }, [credential, profile, request]);
  async function updateConfiguration(mutate, base = configRef.current) {
    if (readProfile() !== cookie.current) {
      chooseProfile(readProfile());
      throw new DOMException("Profile changed; edit discarded", "AbortError");
    }
    const body = structuredClone({
      locations: base.data.locations,
      devices: base.data.devices,
      dashboard: base.data.dashboard,
    });
    mutate(body);
    const result = await request("/api/v2/configuration", {
      method: "PUT",
      headers: { "If-Match": base.etag },
      body: JSON.stringify(body),
    });
    configRef.current = result;
    hold.current = false;
    setSnapshot((s) => (s ? { ...s, configuration: result } : s));
    return result;
  }
  async function saveGrid(settings, base, original = base) {
    return updateConfiguration((body) => {
      body.dashboard.grid_layout = mergeAllLayout(
        body.dashboard.grid_layout,
        settings,
        original?.data.dashboard.grid_layout,
      );
    }, base);
  }
  const reload = async () => {
    const result = await request("/api/v2/configuration");
    configRef.current = result;
    hold.current = false;
    setSnapshot((s) => (s ? { ...s, configuration: result } : s));
    return result;
  };
  return {
    snapshot,
    error,
    loading,
    connected: !!credential,
    profile,
    connect,
    disconnect,
    chooseProfile,
    saveGrid,
    updateConfiguration,
    reload,
    hold,
    request,
  };
}
