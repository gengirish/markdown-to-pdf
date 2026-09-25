"use client";

import { useCallback, useEffect, useState } from "react";

import { toApiError, type TemplateSummary } from "./api";
import { defaultTemplateFor } from "./template-default";
import { useCertForge } from "./use-api";

/** How long a template load may take before it is reported as failed.
 *
 *  The cohort selector used to sit on a grey placeholder bar indefinitely:
 *  requests carry no timeout, and one that never settles — the API machine
 *  scales to zero, and a cold start or a dropped connection can hang — left
 *  the form with neither a list nor an error. Twenty seconds is well past a
 *  cold start and well short of someone giving up on the page. */
const LOAD_TIMEOUT_MS = 20_000;

export type IssuableTemplates =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      /** The org's own templates, then the global ones. */
      templates: TemplateSummary[];
      /** Ids of the org's own templates — the only ones whose source this
       *  viewer can read, and so the only ones the preview can render. */
      ownIds: Set<string>;
      /** What the API picks when no template_id is sent
       *  (`resolve_template_id`): the org's default, else the global one. */
      defaultTemplate: TemplateSummary | undefined;
    };

/** The templates a credential can be issued with, shared by the single and
 *  cohort cards so the two cannot load, fail or default differently.
 *
 *  Org templates need a role the viewer may not have, and that failure must
 *  not hide the global list, which every member can see. Only when both fail
 *  is it an error. */
export function useIssuableTemplates(slug: string): IssuableTemplates & { retry: () => void } {
  const api = useCertForge();
  const [state, setState] = useState<IssuableTemplates>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timedOut = false;
    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, LOAD_TIMEOUT_MS);

    Promise.allSettled([
      api.listOrgTemplates(slug, controller.signal),
      api.listGlobalTemplates(controller.signal),
    ]).then(([own, global]) => {
      window.clearTimeout(timer);
      if (controller.signal.aborted && !timedOut) return;
      if (timedOut) {
        setState({
          status: "error",
          message: "Templates took too long to load. The API may be waking up.",
        });
        return;
      }
      if (own.status === "rejected" && global.status === "rejected") {
        setState({ status: "error", message: toApiError(own.reason).message });
        return;
      }
      const ownList = own.status === "fulfilled" ? own.value : [];
      const globalList = global.status === "fulfilled" ? global.value : [];
      const ownIds = new Set(ownList.map((tpl) => tpl.id));
      setState({
        status: "ready",
        templates: [...ownList, ...globalList.filter((tpl) => !ownIds.has(tpl.id))],
        ownIds,
        defaultTemplate: defaultTemplateFor(ownList, globalList),
      });
    });

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [api, slug, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((current) => current + 1);
  }, []);

  return { ...state, retry };
}
