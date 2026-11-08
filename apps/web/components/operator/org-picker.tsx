"use client";

import { useEffect, useId, useRef, useState } from "react";

import { toApiError, type OperatorOrg } from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { inputClass } from "@/components/dashboard/ui";

/**
 * A searchable org select (WAI-ARIA combobox with a listbox popup). Searches
 * through the operator org list as the operator types, so it never loads
 * every org into the browser.
 *
 * Keyboard: ↓/↑ move, Enter picks, Esc closes the list.
 */
export function OrgPicker({ onPick }: { onPick: (org: { slug: string; name: string }) => void }) {
  const api = useCertForge();
  const inputId = useId();
  const listId = useId();
  const container = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<OperatorOrg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), 200);
    return () => clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    api
      .listOperatorOrgs({ q: query, limit: 8 }, controller.signal)
      .then((page) => {
        setError(null);
        setResults(page.orgs);
        setActive(0);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, query, open]);

  // Clicking anywhere else closes the list.
  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function pick(org: OperatorOrg) {
    onPick({ slug: org.slug, name: org.name });
    setText("");
    setOpen(false);
  }

  const options = results ?? [];
  const optionId = (index: number) => `${listId}-${index}`;

  return (
    <div ref={container} className="relative w-full sm:w-64">
      <label htmlFor={inputId} className="sr-only">
        Filter by organization
      </label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && options.length > 0 ? optionId(active) : undefined}
        value={text}
        placeholder="Filter by organization…"
        maxLength={100}
        autoComplete="off"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((index) => Math.min(index + 1, Math.max(options.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === "Enter") {
            if (open && options[active]) {
              event.preventDefault();
              pick(options[active]);
            }
          } else if (event.key === "Escape") {
            if (open) {
              // Keep Esc from also closing anything behind the picker.
              event.stopPropagation();
              setOpen(false);
            }
          }
        }}
        className={inputClass}
      />
      {open ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Organizations"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-lg border border-hair bg-surface py-1 text-sm shadow-[var(--cf-shadow-lift)]"
        >
          {error ? (
            <li className="px-3 py-2 text-danger">{error}</li>
          ) : results === null ? (
            <li className="px-3 py-2 text-faint">Searching…</li>
          ) : options.length === 0 ? (
            <li className="px-3 py-2 text-faint">No organization matches.</li>
          ) : (
            options.map((org, index) => (
              <li
                key={org.slug}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => pick(org)}
                onMouseEnter={() => setActive(index)}
                className={`cursor-pointer px-3 py-2 ${index === active ? "bg-well" : ""}`}
              >
                <span className="block truncate text-ink">{org.name}</span>
                <span className="block truncate font-mono text-xs text-faint">{org.slug}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
