"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  toApiError,
  type OrgProfile,
  type TemplateConfig,
  type TemplateDetail,
  type TemplateSummary,
  type TracedConfig,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { LAYOUT_WORDING, switchLayout } from "@/lib/template-presets";
import { CertificateSketch, type SketchPart } from "./certificate-sketch";
import { TemplateCanvas } from "./template-canvas";
import { Card, EmptyNote, ErrorNote, Skeleton } from "./ui";

const INPUT =
  "w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm text-ink focus:border-accent focus:outline-none";

const STARTER_HTML = `<html>
  <body style="font-family:Helvetica,Arial,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px;">
      <tr><td align="center" style="font-size:22pt;">CERTIFICATE</td></tr>
      <tr><td align="center" style="font-size:26pt;">{{name}}</td></tr>
      <tr><td align="center" style="font-size:14pt;">{{title}}</td></tr>
      <tr><td align="center"><img src="{{qr}}" style="width:96px;"/></td></tr>
    </table>
  </body>
</html>`;

const DEFAULT_CONFIG: TemplateConfig = {
  layout: "participation",
  ...LAYOUT_WORDING.participation,
  signature_name: "",
  signature_title: "",
  show_qr: true,
  show_logo: true,
  show_footer: true,
};

/** Where the fields start on a freshly uploaded design: A4 landscape with the
 *  boxes roughly where a certificate usually puts them. Mirrors
 *  DEFAULT_TRACED_CONFIG on the server, which is what a save is normalised
 *  against — the two drifting means the canvas shows one layout and the PDF
 *  prints another. */
const DEFAULT_TRACED: TracedConfig = {
  kind: "traced",
  page_width_mm: 297,
  page_height_mm: 210,
  fields: [
    { variable: "name", label: "Recipient name", x_mm: 40, y_mm: 88, w_mm: 217, h_mm: 18, font_pt: 30, color: "#1a202c", align: "center", bold: false },
    { variable: "title", label: "Achievement / course", x_mm: 50, y_mm: 112, w_mm: 197, h_mm: 12, font_pt: 15, color: "#2d3748", align: "center", bold: false },
    { variable: "date", label: "Issue date", x_mm: 40, y_mm: 168, w_mm: 70, h_mm: 8, font_pt: 10, color: "#4a5568", align: "left", bold: false },
    { variable: "credential_id", label: "Credential ID", x_mm: 40, y_mm: 178, w_mm: 70, h_mm: 6, font_pt: 8, color: "#718096", align: "left", bold: false },
    { variable: "qr", label: "Verification QR code", x_mm: 242, y_mm: 158, w_mm: 26, h_mm: 26, font_pt: 8, color: "#000000", align: "center", bold: false },
  ],
};

function isTraced(config: TemplateDetail["config"]): config is TracedConfig {
  return !!config && (config as TracedConfig).kind === "traced";
}

/** The page shape follows the artwork, not A4. A portrait design laid out on a
 *  landscape page prints with the fields in the wrong half of it. */
function pageForAspect(ratio: number): { page_width_mm: number; page_height_mm: number } {
  return ratio >= 1
    ? { page_width_mm: 297, page_height_mm: Math.round((297 / ratio) * 100) / 100 }
    : { page_width_mm: Math.round(297 * ratio * 100) / 100, page_height_mm: 297 };
}

type Editor =
  | { mode: "closed" }
  | { mode: "guided"; id: string | null; name: string; config: TemplateConfig }
  | { mode: "html"; id: string | null; name: string; html: string }
  | {
      mode: "traced";
      id: string | null;
      name: string;
      config: TracedConfig;
      assetId: string;
    };

export function TemplatesCard({
  slug,
  org,
  onChanged,
}: {
  slug: string;
  org: OrgProfile | null;
  /** Called after the list reloads, so the setup checklist can tick "Choose a
   *  design" the moment one exists rather than on the next tab change. */
  onChanged?: () => void;
}) {
  const api = useCertForge();
  const onChangedRef = useRef(onChanged);
  useEffect(() => {
    onChangedRef.current = onChanged;
  }, [onChanged]);

  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [globals, setGlobals] = useState<TemplateSummary[]>([]);
  const [listError, setListError] = useState<string | null>(null);

  const [editor, setEditor] = useState<Editor>({ mode: "closed" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** What the model said about its own reading. Cleared whenever the editor
   *  changes shape, so it can never describe a template it did not produce. */
  const [reading, setReading] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [mine, global] = await Promise.all([
        api.listOrgTemplates(slug),
        api.listGlobalTemplates(),
      ]);
      setTemplates(mine);
      setGlobals(global);
      setListError(null);
      onChangedRef.current?.();
    } catch (err) {
      setTemplates(null);
      setListError(toApiError(err).message);
    }
  }, [api, slug]);

  useEffect(() => {
    void reload();
  }, [reload]);

  /** Opening an existing template needs the detail route — the list omits
   *  html_source, which can be 256 KB a row. */
  const open = useCallback(
    async (id: string) => {
      setError(null);
      setBusy(true);
      try {
        const detail: TemplateDetail = await api.getOrgTemplate(slug, id);
        if (isTraced(detail.config) && detail.background_asset_id) {
          setEditor({
            mode: "traced",
            id: detail.id,
            name: detail.name,
            config: detail.config,
            assetId: detail.background_asset_id,
          });
        } else if (detail.config) {
          setEditor({
            mode: "guided",
            id: detail.id,
            name: detail.name,
            config: detail.config as TemplateConfig,
          });
        } else {
          setEditor({
            mode: "html",
            id: detail.id,
            name: detail.name,
            html: detail.html_source,
          });
        }
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [api, slug],
  );

  const save = useCallback(async () => {
    if (editor.mode === "closed") return;
    setBusy(true);
    setError(null);
    try {
      const payload =
        editor.mode === "guided"
          ? { name: editor.name, config: editor.config }
          : editor.mode === "traced"
            ? {
                name: editor.name,
                config: editor.config,
                backgroundAssetId: editor.assetId,
              }
            : { name: editor.name, htmlSource: editor.html };

      if (editor.id) await api.updateTemplate(slug, editor.id, payload);
      else await api.createTemplate(slug, payload);

      setEditor({ mode: "closed" });
      await reload();
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, slug, editor, reload]);

  /** The preview arrives as a PDF. Opened in a new tab rather than embedded,
   *  so the dashboard never has to host customer-authored content.
   *
   *  The tab is opened synchronously, inside the click, and navigated once the
   *  render comes back. Opening it after the await is the obvious way to write
   *  this and it is broken: the user gesture is spent by then, so Safari and
   *  Firefox block the popup by default. Nothing throws — a blocked popup is
   *  not a rejected promise — so the button spun, cleared, and did nothing,
   *  with no error to show for it. The one failure this feature must not have
   *  is a silent one.
   *
   *  `noopener` cannot be passed to window.open here: per spec it makes the
   *  call return null, and the handle is the whole point. Clearing `opener` on
   *  the new tab is the same protection applied a line later.
   *
   *  If the popup is blocked outright, the PDF is downloaded instead — the
   *  author still gets the artefact rather than an instruction to go change a
   *  browser setting. */
  const preview = useCallback(async () => {
    if (editor.mode === "closed") return;

    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;

    setBusy(true);
    setError(null);
    try {
      const blob = await api.previewTemplate(
        slug,
        editor.mode === "guided"
          ? { config: editor.config }
          : editor.mode === "traced"
            ? { config: editor.config, backgroundAssetId: editor.assetId }
            : { htmlSource: editor.html },
      );
      const url = URL.createObjectURL(blob);
      if (tab) {
        tab.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = "template-preview.pdf";
        link.click();
      }
      // Revoked on a delay: revoking immediately can beat the new tab to the
      // blob and leave it blank.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      // The tab was opened before we knew the render would succeed, so a
      // failure has to close it. Leaving it is a blank about:blank the author
      // has to work out is unrelated to the error under the editor.
      tab?.close();
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, slug, editor]);

  /** Have the model place the fields, then hand the result to the canvas.
   *
   *  It replaces the boxes and nothing else — the artwork and the template name
   *  stay as they are, so a reading that comes back badly costs one click to
   *  undo by dragging rather than a re-upload. */
  const readDesign = useCallback(async () => {
    if (editor.mode !== "traced") return;
    setBusy(true);
    setError(null);
    setReading(null);
    try {
      const result = await api.createTemplateFromImage(slug, {
        assetId: editor.assetId,
        name: editor.name || "Imported design",
      });
      setEditor({
        mode: "traced",
        id: result.id,
        name: result.name,
        assetId: editor.assetId,
        config: result.config as TracedConfig,
      });
      setReading(
        result.needs_review
          ? `Read with ${result.confidence} confidence — check every box before issuing.${
              result.notes ? ` ${result.notes}` : ""
            }`
          : `Fields placed. ${result.imports_remaining} design readings left this month.`,
      );
      await reload();
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, slug, editor, reload]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
        await reload();
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [reload],
  );

  return (
    <Card
      title="Certificate templates"
      description="Build one with the guided form, or write the HTML yourself. Preview renders a real PDF before anything is saved."
      action={
        editor.mode === "closed" ? (
          <div className="flex gap-2">
            <button
              onClick={() =>
                setEditor({ mode: "guided", id: null, name: "", config: DEFAULT_CONFIG })
              }
              className="rounded-lg border border-hair-strong px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent hover:text-ink"
            >
              New
            </button>
            <UploadDesignButton
              slug={slug}
              disabled={busy}
              onUploaded={(asset) => {
                setReading(null);
                setEditor({
                  mode: "traced",
                  id: null,
                  name: "",
                  assetId: asset.id,
                  config: { ...DEFAULT_TRACED, ...pageForAspect(asset.aspect_ratio) },
                });
              }}
              onError={setError}
            />
            <button
              onClick={() =>
                setEditor({ mode: "html", id: null, name: "", html: STARTER_HTML })
              }
              className="rounded-lg border border-hair-strong px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent hover:text-ink"
            >
              Write HTML
            </button>
          </div>
        ) : null
      }
    >
      {editor.mode === "closed" ? (
        <>
          {listError ? (
            <ErrorNote>{listError}</ErrorNote>
          ) : templates === null ? (
            <Skeleton rows={3} />
          ) : templates.length === 0 ? (
            <EmptyNote>
              No templates of your own yet. Issuance falls back to the platform default.
            </EmptyNote>
          ) : (
            <ul className="space-y-2">
              {templates.map((t) => (
                <TemplateRow
                  key={t.id}
                  template={t}
                  busy={busy}
                  onEdit={() => open(t.id)}
                  onDefault={() => act(() => api.setDefaultTemplate(slug, t.id))}
                  onDelete={() => act(() => api.deleteTemplate(slug, t.id))}
                />
              ))}
            </ul>
          )}

          {globals.length > 0 ? (
            <div className="mt-6 border-t border-hair pt-5">
              <p className="mb-3 text-sm text-muted">
                Start from a platform template — it is copied, so your edits stay yours.
              </p>
              <div className="flex flex-wrap gap-2">
                {globals.map((g) => (
                  <button
                    key={g.id}
                    disabled={busy}
                    onClick={() => act(() => api.importTemplate(slug, g.id))}
                    className="rounded-lg border border-hair px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent hover:text-ink disabled:opacity-50"
                  >
                    Import “{g.name}”
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <TemplateEditor
          slug={slug}
          org={org}
          editor={editor}
          busy={busy}
          reading={reading}
          onChange={setEditor}
          onSave={save}
          onPreview={preview}
          onReadDesign={readDesign}
          onCancel={() => {
            setEditor({ mode: "closed" });
            setError(null);
            setReading(null);
          }}
        />
      )}

      {error ? (
        <div className="mt-6">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
    </Card>
  );
}

function TemplateRow({
  template,
  busy,
  onEdit,
  onDefault,
  onDelete,
}: {
  template: TemplateSummary;
  busy: boolean;
  onEdit: () => void;
  onDefault: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-hair px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">
          {template.name}
          {template.is_default ? (
            <span className="ml-2 rounded bg-accent-wash px-2 py-0.5 text-xs text-accent">
              default
            </span>
          ) : null}
        </p>
        <p className="mt-0.5 text-xs text-faint">
          {template.is_guided ? "Guided" : "Custom HTML"}
          {/* Named because a row without this key renders the field blank, and
              a blank line on a certificate is not obviously a data problem. */}
          {template.variables.length > 0
            ? ` · needs ${template.variables.join(", ")} from your CSV`
            : ""}
        </p>
      </div>
      <div className="flex shrink-0 gap-3 text-xs">
        <button onClick={onEdit} disabled={busy} className="text-accent hover:text-accent disabled:opacity-50">
          Edit
        </button>
        {!template.is_default ? (
          <button onClick={onDefault} disabled={busy} className="text-muted hover:text-ink disabled:opacity-50">
            Make default
          </button>
        ) : null}
        <button onClick={onDelete} disabled={busy} className="text-faint hover:text-danger disabled:opacity-50">
          Delete
        </button>
      </div>
    </li>
  );
}

function TemplateEditor({
  slug,
  org,
  editor,
  busy,
  reading,
  onChange,
  onSave,
  onPreview,
  onReadDesign,
  onCancel,
}: {
  slug: string;
  org: OrgProfile | null;
  editor: Exclude<Editor, { mode: "closed" }>;
  busy: boolean;
  reading: string | null;
  onChange: (next: Editor) => void;
  onSave: () => void;
  onPreview: () => void;
  onReadDesign: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <span className="mb-2 block text-sm font-medium text-ink">Template name</span>
        <input
          type="text"
          value={editor.name}
          onChange={(e) => onChange({ ...editor, name: e.target.value })}
          className={INPUT}
        />
      </label>

      {editor.mode === "guided" ? (
        <GuidedFields
          slug={slug}
          org={org}
          config={editor.config}
          onChange={(config) => onChange({ ...editor, config })}
        />
      ) : editor.mode === "traced" ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onReadDesign}
              disabled={busy}
              className="rounded-lg border border-hair-strong px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent disabled:opacity-50"
            >
              {busy ? "Reading…" : "Place the fields for me"}
            </button>
            <span className="text-xs text-faint">
              Reads your design and guesses where each field goes. You can drag them
              afterwards — and you always could.
            </span>
          </div>
          {reading ? (
            <p className="rounded-lg border border-warn-line bg-warn-wash px-3 py-2 text-xs text-warn-ink">
              {reading}
            </p>
          ) : null}
        <TemplateCanvas
          slug={slug}
          assetId={editor.assetId}
          config={editor.config}
          disabled={busy}
          onChange={(config) => onChange({ ...editor, config })}
        />
        </>
      ) : (
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">
            HTML source
          </span>
          <textarea
            value={editor.html}
            spellCheck={false}
            rows={16}
            onChange={(e) => onChange({ ...editor, html: e.target.value })}
            className={`${INPUT} resize-y font-mono text-xs leading-relaxed`}
          />
          <span className="mt-2 block text-xs text-faint">
            Placeholders: {"{{name}}"}, {"{{title}}"}, {"{{date}}"}, {"{{qr}}"},{" "}
            {"{{credential_id}}"}, {"{{issuer_name}}"}, {"{{logo_url}}"},{" "}
            {"{{primary_color}}"}, {"{{accent_color}}"}, {"{{footer_text}}"}. Any other
            name comes from a CSV column. Images must be a data: URI or a placeholder —
            external URLs are refused.
          </span>
        </label>
      )}

      {editor.mode !== "html" && editor.id ? (
        <button
          onClick={() =>
            onChange({
              mode: "html",
              id: editor.id,
              name: editor.name,
              // Nothing is generated client-side: switching starts from the
              // starter markup, and saving replaces the stored HTML. The server
              // then drops the config, which is what detaches this template
              // from the guided form for good.
              html: STARTER_HTML,
            })
          }
          className="text-xs text-muted underline underline-offset-2 hover:text-ink"
        >
          Switch to hand-written HTML — this is one-way, the editor will no longer apply
          to this template
        </button>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
        <button
          onClick={onCancel}
          disabled={busy}
          className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={onPreview}
          disabled={busy}
          className="rounded-lg border border-hair-strong px-4 py-2.5 text-sm text-ink transition-colors hover:border-accent disabled:opacity-50"
        >
          Preview PDF
        </button>
        <button
          onClick={onSave}
          disabled={busy || !editor.name}
          className="rounded-lg bg-accent px-6 py-2.5 text-sm font-medium text-ground transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {busy ? "Working…" : "Save template"}
        </button>
      </div>
    </div>
  );
}

function GuidedFields({
  slug,
  org,
  config,
  onChange,
}: {
  slug: string;
  org: OrgProfile | null;
  config: TemplateConfig;
  onChange: (next: TemplateConfig) => void;
}) {
  const api = useCertForge();
  const set = <K extends keyof TemplateConfig>(key: K, value: TemplateConfig[K]) =>
    onChange({ ...config, [key]: value });
  /** The field with focus, outlined on the sketch. */
  const [focused, setFocused] = useState<SketchPart | null>(null);

  return (
    <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div
        className="space-y-4"
        onFocus={(event) => {
          const part = (event.target as HTMLElement).closest<HTMLElement>("[data-sketch]")?.dataset.sketch;
          setFocused((part as SketchPart | undefined) ?? null);
        }}
        onBlur={() => setFocused(null)}
      >
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-ink">Base layout</span>
          <select
            value={config.layout}
            // A layout carries its own wording. Only stock text is replaced, so
            // a heading someone wrote survives a change of layout.
            onChange={(e) => onChange(switchLayout(config, e.target.value as TemplateConfig["layout"]))}
            className={INPUT}
          >
            <option value="participation">Participation</option>
            <option value="internship">Internship (adds USN and duration)</option>
            <option value="appreciation">Appreciation</option>
          </select>
          <span className="mt-1.5 block text-xs text-faint">
            Sets the heading and wording below. Anything you have typed yourself is kept.
          </span>
        </label>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Heading"
            sketch="heading"
            value={config.heading}
            onChange={(v) => set("heading", v)}
          />
          <TextField
            label="Opening line"
            sketch="body"
            value={config.body}
            onChange={(v) => set("body", v)}
          />
          <TextField
            label="Line before the title"
            sketch="closing"
            value={config.closing}
            onChange={(v) => set("closing", v)}
          />
          <TextField
            label="Signature name"
            sketch="signature"
            value={config.signature_name}
            onChange={(v) => set("signature_name", v)}
            hint="Leave empty for no signature block."
          />
          <TextField
            label="Signature title"
            sketch="signature"
            value={config.signature_title}
            onChange={(v) => set("signature_title", v)}
          />
        </div>

        <div className="flex flex-wrap gap-5">
          <Toggle label="QR code" sketch="qr" checked={config.show_qr} onChange={(v) => set("show_qr", v)} />
          <Toggle
            label="Organization logo"
            sketch="logo"
            checked={config.show_logo}
            onChange={(v) => set("show_logo", v)}
          />
          <Toggle
            label="Footer line"
            sketch="footer"
            checked={config.show_footer}
            onChange={(v) => set("show_footer", v)}
          />
        </div>

        <p className="text-xs text-faint">
          The recipient name, title and date come from each credential; colours, logo and
          footer text come from Branding. The sketch shows a sample person.
        </p>
      </div>

      <div className="xl:sticky xl:top-8 xl:self-start">
        <CertificateSketch
          issuerName={org?.name ?? ""}
          primaryColor={org?.primary_color ?? ""}
          accentColor={org?.accent_color ?? ""}
          footerText={org?.footer_text ?? ""}
          logoSrc={org?.logo_asset_id ? `${api.orgLogoUrl(slug)}?v=${org.logo_asset_id}` : null}
          config={config}
          highlight={focused}
        />
      </div>
    </div>
  );
}

function TextField({
  label,
  sketch,
  hint,
  value,
  onChange,
}: {
  label: string;
  sketch?: SketchPart;
  hint?: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="block" data-sketch={sketch}>
      <span className="mb-2 block text-sm font-medium text-ink">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT} />
      {hint ? <span className="mt-1.5 block text-xs text-faint">{hint}</span> : null}
    </label>
  );
}

function Toggle({
  label,
  sketch,
  checked,
  onChange,
}: {
  label: string;
  sketch?: SketchPart;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink" data-sketch={sketch}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-hair-strong bg-surface text-accent focus:ring-accent"
      />
      {label}
    </label>
  );
}

/** Upload artwork and open the canvas on it.
 *
 *  A hidden file input behind a button, rather than the invisible-overlay drop
 *  zone the CSV card uses: this sits in a row of small header buttons, and an
 *  absolutely positioned input would cover its neighbours. */
function UploadDesignButton({
  slug,
  disabled,
  onUploaded,
  onError,
}: {
  slug: string;
  disabled: boolean;
  onUploaded: (asset: { id: string; aspect_ratio: number }) => void;
  onError: (message: string) => void;
}) {
  const api = useCertForge();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={async (event) => {
          const file = event.target.files?.[0];
          // Cleared immediately so choosing the same file twice still fires a
          // change event — otherwise a failed upload cannot be retried without
          // picking a different file first.
          event.target.value = "";
          if (!file) return;

          setUploading(true);
          try {
            onUploaded(await api.uploadTemplateAsset(slug, file));
          } catch (err) {
            onError(toApiError(err).message);
          } finally {
            setUploading(false);
          }
        }}
      />
      <button
        type="button"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        className="rounded-lg border border-hair-strong px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent hover:text-ink disabled:opacity-50"
      >
        {uploading ? "Uploading…" : "Upload a design"}
      </button>
    </>
  );
}
