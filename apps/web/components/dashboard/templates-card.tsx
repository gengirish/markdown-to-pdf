"use client";

import { useCallback, useEffect, useState } from "react";

import {
  toApiError,
  type TemplateConfig,
  type TemplateDetail,
  type TemplateSummary,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { Card, EmptyNote, ErrorNote, Skeleton } from "./ui";

const INPUT =
  "w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-100 focus:border-indigo-500/60 focus:outline-none";

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
  heading: "CERTIFICATE OF PARTICIPATION",
  body: "This is to certify that",
  closing: "has successfully participated in",
  signature_name: "",
  signature_title: "",
  show_qr: true,
  show_logo: true,
  show_footer: true,
};

type Editor =
  | { mode: "closed" }
  | { mode: "guided"; id: string | null; name: string; config: TemplateConfig }
  | { mode: "html"; id: string | null; name: string; html: string };

export function TemplatesCard({ slug }: { slug: string }) {
  const api = useCertForge();

  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [globals, setGlobals] = useState<TemplateSummary[]>([]);
  const [listError, setListError] = useState<string | null>(null);

  const [editor, setEditor] = useState<Editor>({ mode: "closed" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [mine, global] = await Promise.all([
        api.listOrgTemplates(slug),
        api.listGlobalTemplates(),
      ]);
      setTemplates(mine);
      setGlobals(global);
      setListError(null);
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
        setEditor(
          detail.config
            ? { mode: "guided", id: detail.id, name: detail.name, config: detail.config }
            : { mode: "html", id: detail.id, name: detail.name, html: detail.html_source },
        );
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
   *  so the dashboard never has to host customer-authored content. */
  const preview = useCallback(async () => {
    if (editor.mode === "closed") return;
    setBusy(true);
    setError(null);
    try {
      const blob = await api.previewTemplate(
        slug,
        editor.mode === "guided" ? { config: editor.config } : { htmlSource: editor.html },
      );
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      // Revoked on a delay: revoking immediately can beat the new tab to the
      // blob and leave it blank.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  }, [api, slug, editor]);

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
              className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-indigo-500/60 hover:text-white"
            >
              New
            </button>
            <button
              onClick={() =>
                setEditor({ mode: "html", id: null, name: "", html: STARTER_HTML })
              }
              className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-indigo-500/60 hover:text-white"
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
            <div className="mt-6 border-t border-zinc-800 pt-5">
              <p className="mb-3 text-sm text-zinc-400">
                Start from a platform template — it is copied, so your edits stay yours.
              </p>
              <div className="flex flex-wrap gap-2">
                {globals.map((g) => (
                  <button
                    key={g.id}
                    disabled={busy}
                    onClick={() => act(() => api.importTemplate(slug, g.id))}
                    className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-indigo-500/60 hover:text-white disabled:opacity-50"
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
          editor={editor}
          busy={busy}
          onChange={setEditor}
          onSave={save}
          onPreview={preview}
          onCancel={() => {
            setEditor({ mode: "closed" });
            setError(null);
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
    <li className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-200">
          {template.name}
          {template.is_default ? (
            <span className="ml-2 rounded bg-indigo-500/15 px-2 py-0.5 text-xs text-indigo-300">
              default
            </span>
          ) : null}
        </p>
        <p className="mt-0.5 text-xs text-zinc-500">
          {template.is_guided ? "Guided" : "Custom HTML"}
          {/* Named because a row without this key renders the field blank, and
              a blank line on a certificate is not obviously a data problem. */}
          {template.variables.length > 0
            ? ` · needs ${template.variables.join(", ")} from your CSV`
            : ""}
        </p>
      </div>
      <div className="flex shrink-0 gap-3 text-xs">
        <button onClick={onEdit} disabled={busy} className="text-indigo-400 hover:text-indigo-300 disabled:opacity-50">
          Edit
        </button>
        {!template.is_default ? (
          <button onClick={onDefault} disabled={busy} className="text-zinc-400 hover:text-zinc-200 disabled:opacity-50">
            Make default
          </button>
        ) : null}
        <button onClick={onDelete} disabled={busy} className="text-zinc-500 hover:text-red-400 disabled:opacity-50">
          Delete
        </button>
      </div>
    </li>
  );
}

function TemplateEditor({
  editor,
  busy,
  onChange,
  onSave,
  onPreview,
  onCancel,
}: {
  editor: Exclude<Editor, { mode: "closed" }>;
  busy: boolean;
  onChange: (next: Editor) => void;
  onSave: () => void;
  onPreview: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4">
      <label className="block">
        <span className="mb-2 block text-sm font-medium text-zinc-300">Template name</span>
        <input
          type="text"
          value={editor.name}
          onChange={(e) => onChange({ ...editor, name: e.target.value })}
          className={INPUT}
        />
      </label>

      {editor.mode === "guided" ? (
        <GuidedFields
          config={editor.config}
          onChange={(config) => onChange({ ...editor, config })}
        />
      ) : (
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-zinc-300">
            HTML source
          </span>
          <textarea
            value={editor.html}
            spellCheck={false}
            rows={16}
            onChange={(e) => onChange({ ...editor, html: e.target.value })}
            className={`${INPUT} resize-y font-mono text-xs leading-relaxed`}
          />
          <span className="mt-2 block text-xs text-zinc-500">
            Placeholders: {"{{name}}"}, {"{{title}}"}, {"{{date}}"}, {"{{qr}}"},{" "}
            {"{{credential_id}}"}, {"{{issuer_name}}"}, {"{{logo_url}}"},{" "}
            {"{{primary_color}}"}, {"{{accent_color}}"}, {"{{footer_text}}"}. Any other
            name comes from a CSV column. Images must be a data: URI or a placeholder —
            external URLs are refused.
          </span>
        </label>
      )}

      {editor.mode === "guided" && editor.id ? (
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
          className="text-xs text-zinc-400 underline underline-offset-2 hover:text-zinc-200"
        >
          Switch to hand-written HTML — this is one-way, the guided form will no longer
          apply to this template
        </button>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
        <button
          onClick={onCancel}
          disabled={busy}
          className="rounded-lg px-4 py-2.5 text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={onPreview}
          disabled={busy}
          className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-200 transition-colors hover:border-indigo-500/60 disabled:opacity-50"
        >
          Preview PDF
        </button>
        <button
          onClick={onSave}
          disabled={busy || !editor.name}
          className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-500"
        >
          {busy ? "Working…" : "Save template"}
        </button>
      </div>
    </div>
  );
}

function GuidedFields({
  config,
  onChange,
}: {
  config: TemplateConfig;
  onChange: (next: TemplateConfig) => void;
}) {
  const set = <K extends keyof TemplateConfig>(key: K, value: TemplateConfig[K]) =>
    onChange({ ...config, [key]: value });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-zinc-300">Base layout</span>
          <select
            value={config.layout}
            onChange={(e) => set("layout", e.target.value as TemplateConfig["layout"])}
            className={INPUT}
          >
            <option value="participation">Participation</option>
            <option value="internship">Internship (adds USN and duration)</option>
            <option value="appreciation">Appreciation</option>
          </select>
        </label>

        <TextField
          label="Heading"
          value={config.heading}
          onChange={(v) => set("heading", v)}
        />
        <TextField label="Opening line" value={config.body} onChange={(v) => set("body", v)} />
        <TextField
          label="Line before the title"
          value={config.closing}
          onChange={(v) => set("closing", v)}
        />
        <TextField
          label="Signature name"
          value={config.signature_name}
          onChange={(v) => set("signature_name", v)}
        />
        <TextField
          label="Signature title"
          value={config.signature_title}
          onChange={(v) => set("signature_title", v)}
        />
      </div>

      <div className="flex flex-wrap gap-5">
        <Toggle label="QR code" checked={config.show_qr} onChange={(v) => set("show_qr", v)} />
        <Toggle
          label="Organization logo"
          checked={config.show_logo}
          onChange={(v) => set("show_logo", v)}
        />
        <Toggle
          label="Footer line"
          checked={config.show_footer}
          onChange={(v) => set("show_footer", v)}
        />
      </div>

      <p className="text-xs text-zinc-500">
        The recipient name, credential title, date and colours come from the credential and
        your branding — they are not set here.
      </p>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-zinc-300">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} className={INPUT} />
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-indigo-500/60"
      />
      {label}
    </label>
  );
}
