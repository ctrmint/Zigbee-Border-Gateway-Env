import { useState } from "react";
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
}) {
  const action = useAction(request),
    [scalar, setScalar] = useState({}),
    [inching, setInching] = useState({
      enabled: false,
      mode: "off",
      seconds: 1,
    }),
    [protection, setProtection] = useState({});
  const plug = device.plug,
    job = plug?.latest_job;
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
  return (
    <section
      className="plug-actions"
      aria-label={"Plug controls for " + device.name}
    >
      <Group justify="space-between">
        <Text fw={600}>{device.name}</Text>
        <Text size="xs" c="dimmed">
          Reported relay state remains authoritative
        </Text>
      </Group>
      <Group mt="sm">
        <Button
          disabled={disabled}
          onClick={() => send("relay", { state: true })}
        >
          Request On
        </Button>
        <Button
          variant="default"
          disabled={disabled}
          onClick={() => send("relay", { state: false })}
        >
          Request Off
        </Button>
      </Group>
      <Job
        job={job}
        title="Plug operation"
        disabled={action.busy}
        cancel={() =>
          action.run("/api/v2/plugs", { job_id: job.id, action: "cancel" })
        }
      />
      <Feedback action={action} />
      {!compact && (
        <>
          <Group mt="md">
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
          </Group>
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
