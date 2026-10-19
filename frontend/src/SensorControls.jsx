import { useState, useEffect } from "react";
import {
  Accordion,
  Button,
  Group,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useAction, Feedback, Job, activeJob } from "./actions.jsx";
function Reporting({ device, view, job, profiles, api, online, gateway }) {
  const endpoints = Object.entries(device.endpoints).filter(([, ep]) =>
    ep.input_clusters.some((c) => c === 1026 || c === 1029),
  );
  const defaults = profiles?.profiles.find((p) => p.model === view?.profile)
    ?.defaults || {
    min_interval: 5,
    max_interval: 3600,
    temperature_change: 0.2,
    humidity_change: 1,
  };
  const [edited, setEdited] = useState(false);
  const [policy, setPolicy] = useState(() => ({
      ...defaults,
      model_hint: view?.profile || "",
      ...job?.policy,
    })),
    action = useAction(api.request);
  useEffect(() => {
    if (!edited)
      setPolicy({
        ...defaults,
        model_hint: view?.profile || "",
        ...job?.policy,
      });
  }, [JSON.stringify(job?.policy || defaults), view?.profile]);
  if (!endpoints.length) return null;
  const endpoint =
    endpoints.find(([ep]) => Number(ep) === policy.endpoint) || endpoints[0];
  const disabled =
    action.busy ||
    !online ||
    !device.active ||
    !gateway.reporting_commissioning ||
    !!activeJob(job) ||
    (policy.model_hint === "SONOFF SNZB-02UL" && !gateway.sensor_extensions);
  const change = (key, value) => {
    setEdited(true);
    setPolicy((p) => ({ ...p, [key]: value }));
  };
  return (
    <section>
      <Text fw={600} mb="sm">
        Sensor reporting setup
      </Text>
      <Text size="sm" c="dimmed" mb="md">
        Wake a sleepy sensor with a brief button press. Verified settings
        require acknowledgement/readback; they do not prove recurring reports.
      </Text>
      <Job
        job={job}
        title="Reporting setup"
        disabled={action.busy}
        cancel={() =>
          action.run("/api/v2/commissioning", {
            ieee: device.ieee,
            action: "cancel",
          })
        }
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const body = {
            ieee: device.ieee,
            endpoint: Number(endpoint[0]),
            model_hint: policy.model_hint,
            min_interval: policy.min_interval,
            max_interval: policy.max_interval,
          };
          if (endpoint[1].input_clusters.includes(1026))
            body.temperature_change = policy.temperature_change;
          if (endpoint[1].input_clusters.includes(1029))
            body.humidity_change = policy.humidity_change;
          action.run("/api/v2/commissioning", body);
        }}
      >
        <div className="settings-fields">
          <Select
            label="Reporting endpoint"
            value={endpoint[0]}
            data={endpoints.map(([ep]) => ({
              value: ep,
              label: "Endpoint " + ep,
            }))}
            onChange={(v) => change("endpoint", Number(v))}
          />
          <Select
            label="User-reported sensor model"
            value={policy.model_hint}
            data={[
              { value: "", label: "Standard / unspecified sensor" },
              ...[
                "SONOFF SNZB-02WD",
                "SONOFF SNZB-02LD",
                "SONOFF SNZB-02UL",
              ].map((value) => ({ value, label: value })),
            ]}
            onChange={(value) => {
              setEdited(true);
              const d = profiles?.profiles.find(
                (p) => p.model === value,
              )?.defaults;
              setPolicy((p) => ({
                ...p,
                ...(!job ? d : {}),
                model_hint: value,
              }));
            }}
          />
          {[
            ["min_interval", "Minimum report interval (seconds)", 0, 65534, 1],
            ["max_interval", "Maximum report interval (seconds)", 1, 65534, 1],
            [
              "temperature_change",
              "Temperature change (°C)",
              0.01,
              327.67,
              0.01,
            ],
            ["humidity_change", "Humidity change (% RH)", 0.01, 100, 0.01],
          ]
            .filter(
              ([key]) =>
                (key !== "temperature_change" && key !== "humidity_change") ||
                endpoint[1].input_clusters.includes(
                  key === "temperature_change" ? 1026 : 1029,
                ),
            )
            .map(([key, label, min, max, step]) => (
              <NumberInput
                key={key}
                label={label}
                aria-label={label}
                required
                min={min}
                max={max}
                step={step}
                value={policy[key]}
                onChange={(value) => change(key, value)}
              />
            ))}
        </div>
        <Button mt="md" type="submit" disabled={disabled}>
          {job ? "Retry / apply reporting settings" : "Configure reporting"}
        </Button>
      </form>
      {job?.state === "verified" &&
        api.snapshot.configuration.data.devices[device.ieee]
          ?.freshness_seconds <= job.policy.max_interval && (
          <Button
            mt="sm"
            variant="light"
            onClick={async () => {
              try {
                await api.updateConfiguration((c) => {
                  c.devices[device.ieee].freshness_seconds = Math.min(
                    604800,
                    Math.ceil(job.policy.max_interval * 1.25),
                  );
                });
                action.setNotice("Freshness saved.");
              } catch (e) {
                action.setNotice(e.message);
              }
            }}
          >
            Use recommended freshness (
            {Math.ceil(job.policy.max_interval * 1.25)}s)
          </Button>
        )}
      <Feedback action={action} />
    </section>
  );
}
const displayFields = [
  ["temperature_units", "Display units", "celsius"],
  ["comfort_temperature_min", "Comfort temperature minimum (°C)", "18"],
  ["comfort_temperature_max", "Comfort temperature maximum (°C)", "26"],
  ["comfort_humidity_min", "Comfort humidity minimum (%)", "30"],
  ["comfort_humidity_max", "Comfort humidity maximum (%)", "60"],
  ["temperature_calibration", "Temperature calibration target (°C)", "0"],
  ["humidity_calibration", "Humidity calibration target (%)", "0"],
];
function Display({ device, job, api, online, gateway }) {
  const [setting, setSetting] = useState("temperature_units"),
    [value, setValue] = useState("celsius"),
    action = useAction(api.request);
  const ep = Object.entries(device.endpoints).find(([, v]) =>
    v.input_clusters.includes(64529),
  );
  if (!ep)
    return (
      <Text size="sm">
        Vendor settings unavailable on discovered endpoints. Core measurements
        remain supported.
      </Text>
    );
  return (
    <section>
      <Text size="sm" mb="md">
        {gateway.time_server_valid
          ? "Coordinator time is synchronized; screen synchronization still requires verification."
          : "Coordinator has no current time lease."}
      </Text>
      <Job
        job={job}
        title="Display setup"
        disabled={action.busy}
        cancel={() =>
          action.run("/api/v2/display", { ieee: device.ieee, action: "cancel" })
        }
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.run("/api/v2/display", {
            ieee: device.ieee,
            endpoint: Number(ep[0]),
            settings: {
              [setting]:
                setting === "temperature_units" ? value.trim() : Number(value),
            },
          });
        }}
      >
        <Stack>
          <Select
            label="Display setting"
            value={setting}
            data={displayFields.map(([value, label]) => ({ value, label }))}
            onChange={(key) => {
              setSetting(key);
              setValue(displayFields.find((f) => f[0] === key)[2]);
            }}
          />
          {setting === "temperature_units" ? (
            <Select
              label="Display setting value"
              aria-label="Display setting value"
              data={["celsius", "fahrenheit"]}
              value={value}
              onChange={setValue}
            />
          ) : (
            <TextInput
              label="Display setting value"
              aria-label="Display setting value"
              value={value}
              onChange={(e) => setValue(e.currentTarget.value)}
              required
            />
          )}
          <Button
            type="submit"
            disabled={
              action.busy ||
              !online ||
              !device.active ||
              !gateway.sensor_extensions ||
              !!activeJob(job)
            }
          >
            Apply display setting
          </Button>
          <Text size="sm" c="dimmed">
            Remote-display transport, weather sources and OTA remain
            unavailable.
          </Text>
        </Stack>
      </form>
      <Feedback action={action} />
    </section>
  );
}
export default function SensorControls(props) {
  return (
    <Accordion variant="separated" mt="md">
      <Accordion.Item value="reporting">
        <Accordion.Control>Reporting configuration</Accordion.Control>
        <Accordion.Panel>
          <Reporting
            {...props}
            job={props.jobs?.find((j) => j.ieee === props.device.ieee)}
          />
        </Accordion.Panel>
      </Accordion.Item>
      {props.view?.profile === "SONOFF SNZB-02UL" && (
        <Accordion.Item value="display">
          <Accordion.Control>SNZB-02UL E-Ink settings</Accordion.Control>
          <Accordion.Panel>
            <Display
              {...props}
              job={props.displayJobs?.find((j) => j.ieee === props.device.ieee)}
            />
          </Accordion.Panel>
        </Accordion.Item>
      )}
    </Accordion>
  );
}
