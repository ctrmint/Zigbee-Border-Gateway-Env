import { useRef, useState } from "react";
import { Alert, Button, Group, Text } from "@mantine/core";
export function useAction(request) {
  const pending = useRef(false),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState("");
  async function perform(task, message = "Saved.") {
    if (pending.current) return null;
    pending.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await task();
      setNotice(message);
      return result;
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
      return null;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  async function run(path, body, method = body ? "POST" : "GET") {
    return perform(
      () =>
        request(path, {
          method,
          ...(body ? { body: JSON.stringify(body) } : {}),
        }),
      method === "GET"
        ? "Loaded."
        : /commands|commissioning|plugs|display/.test(path)
          ? "Request accepted. Device actions require acknowledgement/readback."
          : "Saved.",
    );
  }

  return { run, perform, busy, notice, error, setNotice };
}
export function Feedback({ action }) {
  return (
    <>
      {action.error && (
        <Alert color="red" mt="sm" role="alert">
          {action.error}
        </Alert>
      )}
      {action.notice && (
        <Text size="sm" mt="sm" role="status">
          {action.notice}
        </Text>
      )}
    </>
  );
}
export function Job({ job, title = "Operation", cancel, disabled }) {
  if (!job) return null;
  return (
    <div className="job-status">
      <Group justify="space-between">
        <Text fw={600} size="sm">
          {title} · {job.state.replaceAll("_", " ")}
        </Text>
        {cancel && ["queued", "sending", "waiting"].includes(job.state) && (
          <Button
            size="xs"
            variant="default"
            disabled={disabled}
            onClick={cancel}
          >
            Cancel {title.toLowerCase()}
          </Button>
        )}
      </Group>
      <Text size="sm">{job.message}</Text>
      {job.steps && (
        <Text size="xs" c="dimmed">
          Step {Math.min((job.step || 0) + 1, job.steps.length)}/
          {job.steps.length} · Attempt {job.attempt || 0}/3
        </Text>
      )}
      <details>
        <summary>Acknowledgements and readback</summary>
        <pre>{JSON.stringify(job.results || job, null, 2)}</pre>
      </details>
    </div>
  );
}
export const activeJob = (job) =>
  job && ["queued", "waiting", "sending"].includes(job.state);
