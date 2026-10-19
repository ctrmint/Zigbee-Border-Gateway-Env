import {
  Alert,
  Button,
  ColorInput,
  Group,
  NumberInput,
  Paper,
  Select,
  Text,
} from "@mantine/core";
import { useEffect, useState } from "react";
import {
  contrast,
  emptyPresentation,
  fonts,
  metricStyle,
  presentationCSS,
} from "./presentation.js";

export default function AppearanceEditor({ layout, kind, id, onChange }) {
  const [scope, setScope] = useState("tile");
  const p = layout.presentation || emptyPresentation();
  const defaults = scope === "profile";
  const own = defaults ? p.defaults : p[kind]?.[id] || {};
  const effective = defaults
    ? metricStyle({ presentation: { ...p, [kind]: {} } }, kind, id)
    : metricStyle(layout, kind, id);
  function change(patch) {
    const next = structuredClone(p);
    if (defaults) next.defaults = { ...own, ...patch };
    else next[kind][id] = { ...own, ...patch };
    onChange(next);
  }
  const [colorDraft, setColorDraft] = useState(
    effective.color === "auto" ? "" : effective.color,
  );
  useEffect(() => {
    setColorDraft(effective.color === "auto" ? "" : effective.color);
  }, [effective.color, id, scope]);
  const background = layout.theme === "dark" ? "#152538" : "#ffffff";
  const lowContrast =
    effective.color !== "auto" && contrast(effective.color, background) < 4.5;
  return (
    <Paper withBorder p="md" className="appearance-editor">
      <Group justify="space-between" mb="sm">
        <Text fw={600}>Typography & content scale</Text>
        <Select
          aria-label="Appearance scope"
          value={scope}
          onChange={setScope}
          data={[
            { value: "tile", label: "Selected tile override" },
            { value: "profile", label: "Profile defaults" },
          ]}
        />
      </Group>
      <Text size="xs" c="dimmed" mb="md">
        {defaults
          ? "Defaults apply to every tile without its own override."
          : Object.keys(own).length
            ? "This tile overrides the profile defaults for the edited fields."
            : "This tile inherits profile defaults."}{" "}
        Applies to all screen sizes; grid dimensions remain independent.
      </Text>
      <div className="appearance-fields">
        <NumberInput
          label="Content scale (%)"
          min={75}
          max={150}
          value={effective.scale}
          onChange={(v) => typeof v === "number" && change({ scale: v })}
        />
        <NumberInput
          label="Metric font size (px)"
          min={24}
          max={96}
          value={effective.size}
          onChange={(v) => typeof v === "number" && change({ size: v })}
        />
        <Select
          label="Metric typeface"
          value={effective.font}
          onChange={(font) => change({ font })}
          data={Object.keys(fonts).map((value) => ({
            value,
            label: {
              system: "System sans",
              mono: "Monospace",
              serif: "Serif",
              rounded: "Rounded (system fallback)",
            }[value],
          }))}
        />
        <ColorInput
          label="Metric colour (hex)"
          format="hex"
          value={colorDraft}
          placeholder="Automatic metric colour"
          onChange={(color) => {
            setColorDraft(color);
            if (/^#[0-9a-f]{6}$/i.test(color)) change({ color });
          }}
          swatches={[
            "#38cdec",
            "#fbbf64",
            "#b29aff",
            "#68d6a6",
            "#f3f6fc",
            "#152538",
          ]}
        />
      </div>
      {kind === "all" && (
        <Select
          mt="sm"
          label="Recorded trend sparkline"
          value={String(effective.trend)}
          data={[
            { value: "true", label: "Show" },
            { value: "false", label: "Hide" },
          ]}
          onChange={(v) => change({ trend: v === "true" })}
        />
      )}
      {colorDraft && !/^#[0-9a-f]{6}$/i.test(colorDraft) && (
        <Text size="xs" c="orange" mt="xs">
          Enter a complete six-digit hex colour to apply it.
        </Text>
      )}
      {lowContrast && (
        <Alert color="orange" mt="sm">
          Low contrast against the panel background. Choose a more readable
          colour (aim for 4.5:1).
        </Alert>
      )}
      <div
        className="typography-preview"
        style={presentationCSS(layout, kind, id)}
        aria-label="Metric typography preview"
      >
        <span className="metric-reading">21.6</span>
        <small> °C</small>
        <Text size="xs" c="dimmed">
          Typography sample · not a sensor reading
        </Text>
      </div>
      <Group mt="sm">
        <Button
          variant="default"
          size="xs"
          onClick={() => change({ color: "auto" })}
        >
          Automatic colour
        </Button>
        <Button
          variant="default"
          size="xs"
          onClick={() => {
            const next = structuredClone(p);
            if (defaults) next.defaults = {};
            else delete next[kind][id];
            onChange(next);
          }}
        >
          {defaults ? "Reset profile defaults" : "Use profile defaults"}
        </Button>
      </Group>
    </Paper>
  );
}
