"use client";
import { CSSProperties, PointerEvent, ReactNode, useRef, useState } from "react";
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from "lucide-react";

export default function ResizablePanel({ side, userId, children, className = "" }: {
  side: "left" | "right"; userId: string; children: ReactNode; className?: string;
}) {
  const initial = side === "left" ? 240 : 320;
  const minimum = side === "left" ? 180 : 240;
  const key = `rag-panel:${userId}:${side}`;
  const [width, setWidth] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(key) ?? "null");
      return typeof saved === "number" && Number.isFinite(saved) ? saved === 40 ? 40 : Math.max(minimum, Math.min(520, saved)) : initial;
    } catch { return initial; }
  });
  const previous = useRef(width === 40 ? initial : width);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const collapsed = width === 40;
  const save = (value: number) => {
    const next = value < 96 ? 40 : Math.max(minimum, Math.min(520, Math.floor(window.innerWidth * .32), value));
    setWidth(next);
    if (next !== 40) previous.current = next;
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* Preferences are optional. */ }
  };
  const toggle = () => save(collapsed ? previous.current : 40);
  const start = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, width };
  };
  const Close = side === "left" ? PanelLeftClose : PanelRightClose;
  const Open = side === "left" ? PanelLeftOpen : PanelRightOpen;
  return <aside className={`resizable-panel resizable-${side} ${className}`} style={{ "--panel-width": `${width}px` } as CSSProperties}>
    <button type="button" className="panel-toggle" aria-label={`${collapsed ? "Expand" : "Collapse"} ${side === "left" ? "conversations" : "documents"} panel`} aria-expanded={!collapsed} onClick={toggle}>
      {collapsed ? <Open className="h-4 w-4" /> : <Close className="h-4 w-4" />}
    </button>
    <div className={`panel-content ${collapsed ? "panel-collapsed" : ""}`}>{children}</div>
    <div role="separator" tabIndex={0} aria-label={`Resize ${side === "left" ? "conversations" : "documents"} panel`} aria-orientation="vertical" aria-valuemin={40} aria-valuemax={520} aria-valuenow={width}
      className="panel-resizer" onPointerDown={start}
      onPointerMove={(e) => { if (drag.current) save(drag.current.width + (e.clientX - drag.current.x) * (side === "left" ? 1 : -1)); }}
      onPointerUp={(e) => { drag.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}
      onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }}
      onDoubleClick={() => save(initial)} onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End", "Enter"].includes(e.key)) {
          e.preventDefault();
          if (e.key === "Enter") toggle();
          else if (e.key === "Home") save(40);
          else if (e.key === "End") save(initial);
          else save(width + (e.key === "ArrowRight" ? 24 : -24) * (side === "left" ? 1 : -1));
        }
      }} />
  </aside>;
}
