"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { toApiError, type TracedConfig, type TracedField } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { ErrorNote } from "./ui";

/** Fields a traced template can bind to, and what to call them on screen.
 *
 *  Kept in step with TRACED_VARIABLES in apps/api/api/services/templates.py.
 *  The server refuses anything outside that set, so offering a name here that
 *  it does not accept produces a save that fails for a reason the person
 *  cannot see. Adding one means adding it in both places. */
const BINDABLE: { variable: string; label: string }[] = [
  { variable: "name", label: "Recipient name" },
  { variable: "title", label: "Achievement / course" },
  { variable: "date", label: "Issue date" },
  { variable: "credential_id", label: "Credential ID" },
  { variable: "issuer_name", label: "Issuing organization" },
  { variable: "qr", label: "Verification QR code" },
  { variable: "logo_url", label: "Organization logo" },
  { variable: "footer_text", label: "Footer line" },
];

const IMAGE_FIELDS = new Set(["qr", "logo_url"]);

/** Placed at the middle of the page rather than at the origin: a new box in the
 *  top-left corner usually lands on the artwork's border and has to be dragged
 *  before it can even be seen. */
function newField(variable: string, config: TracedConfig): TracedField {
  const label = BINDABLE.find((b) => b.variable === variable)?.label ?? variable;
  const square = IMAGE_FIELDS.has(variable);
  const w = square ? 26 : Math.min(120, config.page_width_mm * 0.5);
  const h = square ? 26 : 12;
  return {
    variable,
    label,
    x_mm: Math.max(0, config.page_width_mm / 2 - w / 2),
    y_mm: Math.max(0, config.page_height_mm / 2 - h / 2),
    w_mm: w,
    h_mm: h,
    font_pt: 14,
    color: "#1a202c",
    align: "center",
    bold: false,
  };
}

type Drag = {
  index: number;
  mode: "move" | "resize";
  startX: number;
  startY: number;
  origin: TracedField;
};

export function TemplateCanvas({
  slug,
  assetId,
  config,
  onChange,
  disabled,
}: {
  slug: string;
  assetId: string;
  config: TracedConfig;
  onChange: (next: TracedConfig) => void;
  disabled?: boolean;
}) {
  const api = useCertForge();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  const frameRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<Drag | null>(null);

  /** The artwork is behind an authenticated route, so it cannot be an <img src>
   *  the browser fetches on its own — no Authorization header would go with it.
   *  Fetched as a blob and revoked on unmount; the preview path's 60-second
   *  timeout is right for a new tab and wrong for a canvas that stays open. */
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;

    void (async () => {
      try {
        const blob = await api.templateAssetImage(slug, assetId);
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setImageUrl(url);
        setImageError(null);
      } catch (err) {
        if (!cancelled) setImageError(toApiError(err).message);
      }
    })();

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [api, slug, assetId]);

  const setField = useCallback(
    (index: number, patch: Partial<TracedField>) => {
      onChange({
        ...config,
        fields: config.fields.map((f, i) => (i === index ? { ...f, ...patch } : f)),
      });
    },
    [config, onChange],
  );

  /** Millimetres per rendered pixel, recomputed on every pointer event.
   *
   *  Not cached on mount: this card sits in a responsive grid, so the rendered
   *  width changes with the window. A stale ratio leaves the layout correct and
   *  the drag maths correct while the mapping between them is wrong, which is
   *  the most confusing kind of broken. */
  const mmPerPx = useCallback(() => {
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    return config.page_width_mm / rect.width;
  }, [config.page_width_mm]);

  const onPointerDown = (index: number, mode: "move" | "resize") => (
    event: React.PointerEvent<HTMLElement>,
  ) => {
    if (disabled) return;
    event.preventDefault();
    event.stopPropagation();
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
    setSelected(index);
    dragRef.current = {
      index,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      origin: { ...config.fields[index] },
    };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const scale = mmPerPx();
    if (scale === 0) return;

    const dx = (event.clientX - drag.startX) * scale;
    const dy = (event.clientY - drag.startY) * scale;
    const { origin } = drag;

    if (drag.mode === "move") {
      setField(drag.index, {
        x_mm: clamp(origin.x_mm + dx, 0, config.page_width_mm - origin.w_mm),
        y_mm: clamp(origin.y_mm + dy, 0, config.page_height_mm - origin.h_mm),
      });
    } else {
      setField(drag.index, {
        w_mm: clamp(origin.w_mm + dx, 5, config.page_width_mm - origin.x_mm),
        h_mm: clamp(origin.h_mm + dy, 4, config.page_height_mm - origin.y_mm),
      });
    }
  };

  const endDrag = (event: React.PointerEvent<HTMLElement>) => {
    if (!dragRef.current) return;
    const target = event.target as HTMLElement;
    if (target.hasPointerCapture?.(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
  };

  const used = new Set(config.fields.map((f) => f.variable));
  const available = BINDABLE.filter((b) => !used.has(b.variable));

  return (
    <div className="space-y-4">
      {imageError ? <ErrorNote>{imageError}</ErrorNote> : null}

      <div
        ref={frameRef}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="relative w-full touch-none select-none overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950"
        style={{ aspectRatio: `${config.page_width_mm} / ${config.page_height_mm}` }}
      >
        {imageUrl ? (
          // A blob: URL from an authenticated fetch. next/image cannot load one
          // and there is no remote host to optimise against, so the rule does
          // not apply here.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Your certificate design"
            draggable={false}
            className="pointer-events-none absolute inset-0 h-full w-full object-fill"
          />
        ) : (
          <div className="absolute inset-0 animate-pulse bg-zinc-900" />
        )}

        {config.fields.map((field, index) => (
          <div
            key={`${field.variable}-${index}`}
            onPointerDown={onPointerDown(index, "move")}
            className={`absolute cursor-move rounded-sm border text-center ${
              selected === index
                ? "border-indigo-400 bg-indigo-500/25"
                : "border-indigo-500/50 bg-indigo-500/10 hover:bg-indigo-500/20"
            }`}
            style={{
              left: `${(field.x_mm / config.page_width_mm) * 100}%`,
              top: `${(field.y_mm / config.page_height_mm) * 100}%`,
              width: `${(field.w_mm / config.page_width_mm) * 100}%`,
              height: `${(field.h_mm / config.page_height_mm) * 100}%`,
            }}
          >
            <span className="pointer-events-none absolute -top-5 left-0 whitespace-nowrap rounded bg-zinc-900/90 px-1.5 py-0.5 text-[10px] text-indigo-200">
              {field.label}
            </span>
            <span
              onPointerDown={onPointerDown(index, "resize")}
              className="absolute -bottom-1 -right-1 h-3 w-3 cursor-se-resize rounded-sm border border-indigo-300 bg-indigo-500"
            />
          </div>
        ))}
      </div>

      <p className="text-xs text-zinc-500">
        Drag a box onto the part of your design it belongs on; drag its corner to
        resize. Positions are stored in millimetres, so the certificate prints exactly
        where you put them.
      </p>

      {selected !== null && config.fields[selected] ? (
        <FieldControls
          field={config.fields[selected]}
          onChange={(patch) => setField(selected, patch)}
          onRemove={() => {
            onChange({
              ...config,
              fields: config.fields.filter((_, i) => i !== selected),
            });
            setSelected(null);
          }}
        />
      ) : (
        <p className="text-xs text-zinc-500">Select a box to change its size or colour.</p>
      )}

      {available.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-4">
          <span className="text-xs text-zinc-500">Add a field:</span>
          {available.map((b) => (
            <button
              key={b.variable}
              type="button"
              disabled={disabled}
              onClick={() => {
                onChange({ ...config, fields: [...config.fields, newField(b.variable, config)] });
                setSelected(config.fields.length);
              }}
              className="rounded-lg border border-zinc-800 px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:border-indigo-500/60 hover:text-white disabled:opacity-50"
            >
              + {b.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FieldControls({
  field,
  onChange,
  onRemove,
}: {
  field: TracedField;
  onChange: (patch: Partial<TracedField>) => void;
  onRemove: () => void;
}) {
  const isImage = IMAGE_FIELDS.has(field.variable);

  return (
    <div className="flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 px-4 py-3">
      <span className="text-sm font-medium text-zinc-200">{field.label}</span>

      {/* A QR code and a logo are drawn as images, so type controls would claim
          to do something they cannot. */}
      {!isImage ? (
        <>
          <label className="text-xs text-zinc-400">
            <span className="mb-1 block">Size (pt)</span>
            <input
              type="number"
              min={4}
              max={96}
              value={field.font_pt}
              onChange={(e) => onChange({ font_pt: Number(e.target.value) })}
              className="w-20 rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
            />
          </label>

          <label className="text-xs text-zinc-400">
            <span className="mb-1 block">Colour</span>
            <input
              type="color"
              value={field.color}
              onChange={(e) => onChange({ color: e.target.value })}
              className="h-8 w-12 cursor-pointer rounded border border-zinc-800 bg-zinc-900"
            />
          </label>

          <label className="text-xs text-zinc-400">
            <span className="mb-1 block">Align</span>
            <select
              value={field.align}
              onChange={(e) => onChange({ align: e.target.value as TracedField["align"] })}
              className="rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
            >
              <option value="left">Left</option>
              <option value="center">Centre</option>
              <option value="right">Right</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={field.bold}
              onChange={(e) => onChange({ bold: e.target.checked })}
              className="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
            />
            Bold
          </label>
        </>
      ) : null}

      <button
        type="button"
        onClick={onRemove}
        className="ml-auto text-xs text-zinc-500 hover:text-red-400"
      >
        Remove
      </button>
    </div>
  );
}

function clamp(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}
