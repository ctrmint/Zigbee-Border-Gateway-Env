import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Text } from "@mantine/core";
export default function ConfigForm({
  api,
  configuration,
  initial,
  apply,
  label = "Save changes",
  children,
  onSaved,
}) {
  const [values, setValues] = useState(() => initial(configuration.data)),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [conflict, setConflict] = useState(false),
    [notice, setNotice] = useState("");
  const base = useRef(configuration),
    locked = useRef(false);
  useEffect(() => {
    if (!dirty) {
      base.current = configuration;
      setValues(initial(configuration.data));
    }
  }, [configuration.data.revision]);
  const set = (key, value) => {
    setDirty(true);
    setNotice("");
    setValues((v) => ({ ...v, [key]: value }));
  };
  const reset = (latest) => {
    base.current = latest;
    setValues(initial(latest.data));
    setDirty(false);
    setError("");
    setConflict(false);
  };
  async function save(reapply = false) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    try {
      const latest = reapply ? await api.reload() : base.current;
      const result = await api.updateConfiguration(
        (body) => apply(body, values),
        latest,
      );
      reset(result);
      setNotice("Saved.");
      onSaved?.();
    } catch (e) {
      if (e.name !== "AbortError") {
        setError(e.message);
        setConflict(e.status === 412);
      }
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      {children(values, set)}
      <Group mt="md">
        <Button type="submit" disabled={busy} loading={busy}>
          {label}
        </Button>
        {dirty && (
          <Button
            variant="default"
            disabled={busy}
            onClick={() => reset(configuration)}
          >
            Discard changes
          </Button>
        )}
      </Group>
      {notice && (
        <Text size="sm" role="status" mt="sm">
          {notice}
        </Text>
      )}
      {error && (
        <Alert color="orange" mt="md" role="alert">
          {error}
          {conflict && (
            <Group mt="sm">
              <Button
                variant="default"
                onClick={async () => {
                  try {
                    reset(await api.reload());
                  } catch (e) {
                    setError(e.message);
                  }
                }}
              >
                Reload and discard edit
              </Button>
              <Button loading={busy} onClick={() => save(true)}>
                Reapply edit to latest configuration
              </Button>
            </Group>
          )}
        </Alert>
      )}
    </form>
  );
}
