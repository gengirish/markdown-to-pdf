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

/** Millimetres of box height needed per point of font size.
 *
 *  Kept in step with MIN_HEIGHT_MM_PER_PT in
 *  apps/api/api/services/templates.py, which is where it is enforced. Applied
 *  here too so the box you drag is the box that renders: the server grows an
 *  undersized box on save, and without this the canvas would show one size and
 *  the PDF print another. Below the server's threshold the text does not
 *  overflow or wrap — it disappears. */
const MIN_HEIGHT_MM_PER_PT = 0.6;

function minHeightFor(field: TracedField) {
  return IMAGE_FIELDS.has(field.variable) ? 4 : field.font_pt * MIN_HEIGHT_MM_PER_PT;
}

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
        h_mm: clamp(
          origin.h_mm + dy,
          minHeightFor(origin),
          config.page_height_mm - origin.y_mm,
        ),
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
        className="relative w-full touch-none select-none overflow-hidden rounded-lg border border-hair bg-ground"
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
          <div className="absolute inset-0 animate-pulse bg-surface" />
        )}

        {config.fields.map((field, index) => (
          <div
            key={`${field.variable}-${index}`}
            onPointerDown={onPointerDown(index, "move")}
            className={`absolute cursor-move rounded-sm border text-center ${
              selected === index
                ? "border-accent bg-accent-wash"
                : "border-accent bg-accent-wash hover:bg-accent-wash"
            }`}
            style={{
              left: `${(field.x_mm / config.page_width_mm) * 100}%`,
              top: `${(field.y_mm / config.page_height_mm) * 100}%`,
              width: `${(field.w_mm / config.page_width_mm) * 100}%`,
              height: `${(field.h_mm / config.page_height_mm) * 100}%`,
            }}
          >
            <span className="pointer-events-none absolute -top-5 left-0 whitespace-nowrap rounded bg-surface px-1.5 py-0.5 text-[10px] text-accent">
              {field.label}
            </span>
            <span
              onPointerDown={onPointerDown(index, "resize")}
              className="absolute -bottom-1 -right-1 h-3 w-3 cursor-se-resize rounded-sm border border-accent-line bg-accent"
            />
          </div>
        ))}
      </div>

      <p className="text-xs text-faint">
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
        <p className="text-xs text-faint">Select a box to change its size or colour.</p>
      )}

      {available.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-hair pt-4">
          <span className="text-xs text-faint">Add a field:</span>
          {available.map((b) => (
            <button
              key={b.variable}
              type="button"
              disabled={disabled}
              onClick={() => {
                onChange({ ...config, fields: [...config.fields, newField(b.variable, config)] });
                setSelected(config.fields.length);
              }}
              className="rounded-lg border border-hair px-2.5 py-1 text-xs text-ink transition-colors hover:border-accent hover:text-ink disabled:opacity-50"
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
    <div className="flex flex-wrap items-end gap-4 rounded-lg border border-hair px-4 py-3">
      <span className="text-sm font-medium text-ink">{field.label}</span>

      {/* A QR code and a logo are drawn as images, so type controls would claim
          to do something they cannot. */}
      {!isImage ? (
        <>
          <label className="text-xs text-muted">
            <span className="mb-1 block">Size (pt)</span>
            <input
              type="number"
              min={4}
              max={96}
              value={field.font_pt}
              onChange={(e) => {
                const font_pt = Number(e.target.value);
                // Grown with the font, not left behind by it: typing 30 into a
                // box sized for 10 is the same trap approached from the other
                // side, and the server would silently grow it on save anyway.
                onChange({
                  font_pt,
                  h_mm: Math.max(field.h_mm, font_pt * MIN_HEIGHT_MM_PER_PT),
                });
              }}
              className="w-20 rounded border border-hair bg-surface px-2 py-1 text-sm text-ink"
            />
          </label>

          <label className="text-xs text-muted">
            <span className="mb-1 block">Colour</span>
            <input
              type="color"
              value={field.color}
              onChange={(e) => onChange({ color: e.target.value })}
              className="h-8 w-12 cursor-pointer rounded border border-hair bg-surface"
            />
          </label>

          <label className="text-xs text-muted">
            <span className="mb-1 block">Align</span>
            <select
              value={field.align}
              onChange={(e) => onChange({ align: e.target.value as TracedField["align"] })}
              className="rounded border border-hair bg-surface px-2 py-1 text-sm text-ink"
            >
              <option value="left">Left</option>
              <option value="center">Centre</option>
              <option value="right">Right</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={field.bold}
              onChange={(e) => onChange({ bold: e.target.checked })}
              className="h-4 w-4 rounded border-hair-strong bg-surface"
            />
            Bold
          </label>
        </>
      ) : null}

      <button
        type="button"
        onClick={onRemove}
        className="ml-auto text-xs text-faint hover:text-danger"
      >
        Remove
      </button>
    </div>
  );
}

function clamp(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}
