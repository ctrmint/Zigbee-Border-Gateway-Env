import { useEffect, useRef, useState } from "react";
import {
  Accordion,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Select,
  Stack,
  Text,
} from "@mantine/core";
import { useAction, Feedback, Job, activeJob } from "./actions.jsx";
const scalarChoices = {
  startup_behavior: {
    label: "Power-loss behavior",
    values: ["off", "on", "toggle", "previous"],
  },
  network_indicator: {
    label: "Network indicator",
    values: ["enabled", "disabled"],
  },
  outlet_protection: {
    label: "Outlet protection",
    values: ["enabled", "disabled"],
  },
};
export default function PlugControls({
  device,
  online,
  gateway,
  request,
  compact = false,
  variant = "all",
}) {
  const action = useAction(request),
    [relayDebouncing, setRelayDebouncing] = useState(false),
    [relayNeedsRefresh, setRelayNeedsRefresh] = useState(false),
    [scalar, setScalar] = useState({}),
    [inching, setInching] = useState({
      enabled: false,
      mode: "off",
      seconds: 1,
    }),
    [protection, setProtection] = useState({});
  const plug = device.plug,
    job = plug?.latest_job;
  const relayRequest = useRef(false),
    lastRelayRequest = useRef(0),
    relayBaselineReceived = useRef(0),
    relayJobId = useRef(null),
    [relayQueued, setRelayQueued] = useState(false);
  const relayMeasurement = device.measurements?.find(
      (measurement) =>
        measurement.endpoint === plug?.endpoint &&
        measurement.cluster === 6 &&
        measurement.attribute === 0,
    ),
    relayOutcomeUncertain =
      job?.action === "relay" &&
      ["uncertain", "cancelled", "expired"].includes(job.state) &&
      (relayMeasurement?.received_at || 0) <= job.created_at,
    relayState =
      !relayNeedsRefresh &&
      !relayOutcomeUncertain &&
      relayMeasurement?.quality === "valid" &&
      typeof relayMeasurement.value === "boolean"
        ? relayMeasurement.value
        : null;
  useEffect(() => {
    if (relayJobId.current && job?.id === relayJobId.current) {
      relayJobId.current = null;
      setRelayQueued(false);
    }
    if (
      relayNeedsRefresh &&
      (relayMeasurement?.received_at || 0) > relayBaselineReceived.current
    )
      setRelayNeedsRefresh(false);
  }, [job?.id, relayQueued, relayNeedsRefresh, relayMeasurement?.received_at]);
  if (!plug) return null;
  const disabled =
    action.busy ||
    !online ||
    !gateway.plug_extensions ||
    !plug.controllable ||
    !!activeJob(job);
  const send = (name, settings = {}) =>
    action.run("/api/v2/plugs", {
      ieee: device.ieee,
      endpoint: plug.endpoint,
      action: name,
      settings,
    });
  const toggleRelay = async () => {
    const now = Date.now();
    if (
      relayState === null ||
      disabled ||
      relayRequest.current ||
      now - lastRelayRequest.current < 750
    )
      return;
    relayRequest.current = true;
    setRelayDebouncing(true);
    lastRelayRequest.current = now;
    relayBaselineReceived.current = relayMeasurement?.received_at || 0;
    try {
      const result = await send("relay", { state: !relayState });
      if (result?.data?.id) {
        relayJobId.current = result.data.id;
        setRelayQueued(true);
      } else setRelayNeedsRefresh(true);
    } finally {
      const remaining = Math.max(0, 750 - (Date.now() - now));
      if (remaining)
        await new Promise((resolve) => setTimeout(resolve, remaining));
      relayRequest.current = false;
      setRelayDebouncing(false);
    }
  };
  const relayJobActive = activeJob(job),
    relayDisabled =
      disabled ||
      relayDebouncing ||
      relayQueued ||
      relayState === null ||
      relayJobActive,
    relayLabel = relayState === null ? "Unknown" : relayState ? "On" : "Off",
    statusMessage =
      relayState !== null
        ? `Last confirmed relay state: ${relayLabel}.`
        : relayNeedsRefresh || relayOutcomeUncertain
          ? "The switch result is uncertain. Read plug values before switching."
          : relayMeasurement?.quality === "stale"
            ? "Relay state is stale. Read plug values before switching."
            : relayMeasurement?.quality === "invalid"
              ? "Relay state is invalid. Read plug values before switching."
              : "Relay state has not been reported. Read plug values before switching.";
  const toggleControl = (
    <div className="plug-toggle-cell" key={device.ieee}>
      <Text fw={600} className="plug-toggle-name" title={device.name}>
        {device.name}
      </Text>
      <button
        type="button"
        className="relay-rocker"
        data-state={relayState === null ? "unknown" : relayState ? "on" : "off"}
        role={relayState === null ? undefined : "switch"}
        aria-checked={relayState === null ? undefined : relayState}
        aria-label={
          relayState === null
            ? `Relay state unknown for ${device.name}`
            : `Relay for ${device.name}`
        }
        disabled={relayDisabled}
        onClick={toggleRelay}
      >
        <span>OFF</span>
        <span className="relay-rocker-track" aria-hidden="true">
          <span className="relay-rocker-thumb" />
        </span>
        <span>ON</span>
      </button>
      <Text size="xs" c="dimmed" role="status" aria-live="polite">
        {statusMessage}
      </Text>
    </div>
  );
  const operationPanel = (
    <div
      className="plug-operation-panel"
      role="group"
      aria-label={`${device.name} plug operation status`}
      key={device.ieee}
    >
      <Text fw={600} size="sm" className="plug-operation-heading">
        {device.name} operation
      </Text>
      {job ? (
        <Job
          job={job}
          title="Plug operation"
          disabled={action.busy}
          cancel={() =>
            action.run("/api/v2/plugs", {
              job_id: job.id,
              action: "cancel",
            })
          }
        />
      ) : (
        <Text size="sm" c="dimmed" role="status">
          No recent plug operation.
        </Text>
      )}
      <Feedback action={action} />
      {relayState === null && (
        <Button
          size="xs"
          variant="light"
          disabled={disabled}
          onClick={() => send("read")}
          aria-label={`Read plug values for ${device.name}`}
        >
          Read plug values to refresh state
        </Button>
      )}
    </div>
  );
  if (variant === "toggle") return toggleControl;
  if (variant === "operation") return operationPanel;
  return (
    <section
      className={`plug-actions${compact ? " plug-actions-compact" : ""}`}
      aria-label={"Plug controls for " + device.name}
    >
      <Text size="xs" c="dimmed" mb="xs">
        Gateway-reported state is authoritative.
      </Text>
      <div className="plug-toggle-board">{toggleControl}</div>
      <div className="plug-operations-grid">{operationPanel}</div>
      {!compact && (
        <>
          <div className="plug-secondary-actions">
            <Button
              variant="light"
              disabled={disabled}
              onClick={() => send("read")}
            >
              Read plug values
            </Button>
            <Button
              variant="light"
              disabled={disabled}
              onClick={() => send("commission")}
            >
              Configure plug reporting
            </Button>
          </div>
          <Accordion mt="md" variant="separated">
            <Accordion.Item value="settings">
              <Accordion.Control>
                Startup, indicator and protection enable
              </Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  {Object.entries(scalarChoices).map(([key, options]) => (
                    <form
                      key={key}
                      onSubmit={(e) => {
                        e.preventDefault();
                        send(key, {
                          value:
                            key === "startup_behavior"
                              ? scalar[key]
                              : scalar[key] === "enabled",
                        });
                      }}
                    >
                      <Group align="end">
                        <Select
                          label={options.label}
                          aria-label={options.label}
                          value={scalar[key] || null}
                          placeholder="Choose new value…"
                          data={options.values}
                          onChange={(value) =>
                            setScalar((s) => ({ ...s, [key]: value }))
                          }
                          required
                        />
                        <Button
                          type="submit"
                          disabled={disabled || !scalar[key]}
                        >
                          Apply {options.label.toLowerCase()}
                        </Button>
                      </Group>
                    </form>
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value="inching">
              <Accordion.Control>Inching</Accordion.Control>
              <Accordion.Panel>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    send("inching", inching);
                  }}
                >
                  <Stack>
                    <Checkbox
                      label="Enable inching"
                      checked={inching.enabled}
                      onChange={(e) => {
                        const enabled = e.currentTarget.checked;
                        setInching((s) => ({ ...s, enabled }));
                      }}
                    />
                    <Select
                      label="Inching target"
                      data={["off", "on"]}
                      value={inching.mode}
                      onChange={(mode) => setInching((s) => ({ ...s, mode }))}
                    />
                    <NumberInput
                      label="Inching seconds"
                      aria-label="Inching seconds"
                      min={0.5}
                      max={3599.5}
                      step={0.5}
                      value={inching.seconds}
                      required
                      onChange={(seconds) =>
                        setInching((s) => ({ ...s, seconds }))
                      }
                    />
                    <Button type="submit" disabled={disabled}>
                      Apply inching
                    </Button>
                    <Text size="sm" c="dimmed">
                      Device acknowledgement does not verify timing or
                      persistence. Schedules and OTA remain unavailable.
                    </Text>
                  </Stack>
                </form>
              </Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value="protection">
              <Accordion.Control>
                Protection thresholds · 13 A / 3250 W maximum
              </Accordion.Control>
              <Accordion.Panel>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const values = {
                      max_current: protection.max_current,
                      max_power: protection.max_power,
                    };
                    for (const key of [
                      "min_current",
                      "max_voltage",
                      "min_voltage",
                      "min_power",
                    ]) {
                      values["enable_" + key] = !!protection["enable_" + key];
                      if (values["enable_" + key])
                        values[key] = protection[key];
                    }
                    send("protection", values);
                  }}
                >
                  <Stack>
                    {[
                      ["max_current", "Maximum current (A)", 0.1, 13, 0.1],
                      ["max_power", "Maximum power (W)", 0.1, 3250, 0.1],
                      ["min_current", "Minimum current (A)", 0.1, 13, 0.1],
                      ["max_voltage", "Maximum voltage (V)", 165, 277, 1],
                      ["min_voltage", "Minimum voltage (V)", 165, 277, 1],
                      ["min_power", "Minimum power (W)", 0.1, 3250, 0.1],
                    ].map(([key, label, min, max, step], index) => (
                      <div key={key}>
                        {index > 1 && (
                          <Checkbox
                            label={"Enable " + label.toLowerCase()}
                            checked={!!protection["enable_" + key]}
                            onChange={(e) => {
                              const enabled = e.currentTarget.checked;
                              setProtection((s) => ({
                                ...s,
                                ["enable_" + key]: enabled,
                              }));
                            }}
                          />
                        )}
                        <NumberInput
                          label={label}
                          aria-label={label}
                          value={protection[key] ?? ""}
                          min={min}
                          max={max}
                          step={step}
                          required={index < 2 || !!protection["enable_" + key]}
                          disabled={index > 1 && !protection["enable_" + key]}
                          onChange={(value) =>
                            setProtection((s) => ({ ...s, [key]: value }))
                          }
                        />
                      </div>
                    ))}
                    <Button type="submit" disabled={disabled}>
                      Apply protection thresholds
                    </Button>
                    <Text size="sm" c="dimmed">
                      Replaces the complete composite, including optional flags.
                      Apply thresholds and verify the job before separately
                      enabling outlet protection. No setting is applied on page
                      load.
                    </Text>
                  </Stack>
                </form>
              </Accordion.Panel>
            </Accordion.Item>
            <Accordion.Item value="diagnostics">
              <Accordion.Control>
                Settings, energy and capability diagnostics
              </Accordion.Control>
              <Accordion.Panel>
                <pre>
                  {JSON.stringify(
                    {
                      settings: plug.settings,
                      effective_off: plug.effective_off,
                      energy_discontinuities: plug.energy_discontinuities,
                      energy_policy: plug.energy_policy,
                      routing: plug.routing,
                      capabilities: plug.capabilities,
                    },
                    null,
                    2,
                  )}
                </pre>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </>
      )}
    </section>
  );
}
