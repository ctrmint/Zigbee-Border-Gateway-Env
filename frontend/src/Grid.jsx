import { useEffect, useLayoutEffect, useRef } from "react";
import { GridStack } from "gridstack";
import { createPortal } from "react-dom";
import { useState } from "react";
import "gridstack/dist/gridstack.min.css";

// GridStack owns empty tile shells and geometry; React owns their contents via portals.
// No createRoot per widget, innerHTML data injection or DOM ownership shared with React.
export default function Grid({
  items,
  columns,
  editing = false,
  onChange,
  renderTile,
}) {
  const host = useRef(null),
    grid = useRef(null),
    callback = useRef(onChange),
    applying = useRef(false);
  const [targets, setTargets] = useState([]);
  callback.current = onChange;
  useLayoutEffect(() => {
    const g = GridStack.init(
      {
        column: columns,
        cellHeight: 72,
        margin: 8,
        float: true,
        animate: false,
        staticGrid: !editing,
        handle: ".tile-handle",
        resizable: { handles: "se" },
        draggable: { scroll: false },
        minRow: 1,
      },
      host.current,
    );
    grid.current = g;
    g.on("change", () => {
      if (applying.current || !editing) return;
      callback.current?.(
        g.save(false).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })),
      );
    });
    return () => {
      g.offAll();
      g.destroy(false);
      grid.current = null;
    };
  }, [columns, editing]);
  const signature = JSON.stringify(items);
  useLayoutEffect(() => {
    const g = grid.current;
    if (!g) return;
    applying.current = true;
    const wanted = new Set(items.map((n) => n.id));
    g.batchUpdate();
    for (const shell of g.getGridItems())
      if (!wanted.has(shell.gridstackNode.id)) g.removeWidget(shell);
    const portals = [];
    for (const item of items) {
      let shell = g.getGridItems().find((n) => n.gridstackNode.id === item.id);
      if (!shell) {
        shell = document.createElement("div");
        shell.className = "grid-stack-item";
        shell.dataset.sensorId = item.id;
        const content = document.createElement("div");
        content.className = "grid-stack-item-content";
        shell.append(content);
        host.current.append(shell);
        g.makeWidget(shell, { ...item, minH: 3, maxH: 20 });
      } else g.update(shell, { ...item, minH: 3, maxH: 20 });
      portals.push({
        id: item.id,
        node: shell.querySelector(".grid-stack-item-content"),
      });
    }
    g.batchUpdate(false);
    setTargets(portals);
    applying.current = false;
  }, [signature, columns, editing]);
  // Make init changes available once on user interaction, not when viewing or resizing the browser.
  useEffect(() => {
    const g = grid.current;
    if (!g) return;
    const done = () =>
      callback.current?.(
        g.save(false).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })),
      );
    if (editing) g.on("dragstop resizestop", done);
    return () => {
      if (editing) g.off("dragstop resizestop");
    };
  }, [editing, columns]);
  return (
    <div
      className={`grid-stack ${editing ? "editing-grid" : ""}`}
      ref={host}
      data-columns={columns}
    >
      {targets.map((t) => createPortal(renderTile(t.id), t.node, t.id))}
    </div>
  );
}
