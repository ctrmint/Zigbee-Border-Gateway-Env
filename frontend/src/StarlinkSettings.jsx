import { useEffect, useState } from "react";
import { Alert, Button, Group, NumberInput, Paper, Stack, Switch, Text, TextInput } from "@mantine/core";

export default function StarlinkSettings({ api }) {
  const request = api.request;
  const [saved, setSaved] = useState(null),
    [draft, setDraft] = useState(null),
    [etag, setEtag] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");

  async function load(signal) {
    const result = await request("/api/v2/starlink/config", { signal });
    setSaved(result.data);
    setDraft({ ...result.data });
    setEtag(result.etag);
    setError("");
  }
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((e) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => controller.abort();
  }, [request]);

  async function save(event) {
    event.preventDefault();
    if (busy || !draft || !etag) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await request("/api/v2/starlink/config", {
        method: "PUT",
        headers: { "If-Match": etag },
        body: JSON.stringify({
          enabled: draft.enabled,
          host: draft.host,
          port: Number(draft.port),
          dish_enabled: draft.dish_enabled,
          dish_host: draft.dish_host,
          dish_port: Number(draft.dish_port),
        }),
      });
      setSaved(result.data);
      setDraft({ ...result.data });
      setEtag(result.etag);
      setNotice(result.data.enabled || result.data.dish_enabled
        ? "Saved. Read-only Starlink polling will begin shortly."
        : "Saved. Starlink polling is disabled.");
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Connect to the Starlink router’s local read-only gRPC diagnostics API.
        The dish endpoint is separate and is not queried by this integration.
      </Text>
      {error && (
        <Alert color="red" title="Starlink settings unavailable" role="alert">
          {error}
          <Button variant="subtle" size="xs" onClick={() => load().catch((e) => setError(e.message))}>
            Reload settings
          </Button>
        </Alert>
      )}
      {draft && (
        <Paper withBorder p="lg" component="form" onSubmit={save}>
          <Stack>
            <Switch
              label="Enable Starlink router monitoring"
              checked={draft.enabled}
              onChange={(event) => setDraft({ ...draft, enabled: event.currentTarget.checked })}
            />
            <div className="settings-fields">
              <TextInput
                label="Router private IPv4 address"
                aria-label="Router private IPv4 address"
                value={draft.host}
                required
                disabled={!draft.enabled}
                onChange={(event) => setDraft({ ...draft, host: event.currentTarget.value })}
              />
              <NumberInput
                label="gRPC port"
                aria-label="gRPC port"
                value={draft.port}
                min={1}
                max={65535}
                step={1}
                allowDecimal={false}
                allowNegative={false}
                required
                disabled={!draft.enabled}
                onChange={(value) => setDraft({ ...draft, port: value })}
              />
            </div>
            <Switch
              label="Enable dish satellite-link telemetry"
              checked={draft.dish_enabled}
              onChange={(event) => setDraft({ ...draft, dish_enabled: event.currentTarget.checked })}
            />
            <div className="settings-fields">
              <TextInput
                label="Dish private IPv4 address"
                aria-label="Dish private IPv4 address"
                value={draft.dish_host}
                required
                disabled={!draft.dish_enabled}
                onChange={(event) => setDraft({ ...draft, dish_host: event.currentTarget.value })}
              />
              <NumberInput
                label="Dish gRPC port"
                aria-label="Dish gRPC port"
                value={draft.dish_port}
                min={1}
                max={65535}
                step={1}
                allowDecimal={false}
                allowNegative={false}
                required
                disabled={!draft.dish_enabled}
                onChange={(value) => setDraft({ ...draft, dish_port: value })}
              />
            </div>
            <Text size="xs" c="dimmed">
              Router default is 192.168.1.1:9000; dish default is 192.168.100.1:9200.
              Only private IPv4 targets are accepted. Both use bounded read-only requests.
            </Text>
            <Group>
              <Button type="submit" loading={busy} disabled={busy || !saved}>
                Save Starlink settings
              </Button>
              {saved && (
                <Button variant="default" disabled={busy} onClick={() => setDraft({ ...saved })}>
                  Discard changes
                </Button>
              )}
            </Group>
            {notice && <Text size="sm" role="status">{notice}</Text>}
          </Stack>
        </Paper>
      )}
      {!draft && !error && <Text size="sm">Loading Starlink settings…</Text>}
    </Stack>
  );
}
