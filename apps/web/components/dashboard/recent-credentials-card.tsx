"use client";

import { useEffect, useState } from "react";

import {
  publicApi,
  toApiError,
  type CredentialPage,
  type DeliveryStatus,
} from "@/lib/api";
import { useCertForge } from "@/lib/use-api";
import { EmptyNote, ErrorNote, Skeleton, formatDate } from "./ui";

const PAGE_SIZE = 6;

export function RecentCredentialsCard({
  slug,
  refreshToken,
}: {
  slug: string;
  /** Bumped by the issuance card so a finished batch shows up here. */
  refreshToken: number;
}) {
  const api = useCertForge();
  const [page, setPage] = useState<CredentialPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .listOrgCredentials(slug, { limit: PAGE_SIZE }, controller.signal)
      .then((result) => {
        setPage(result);
        setError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setPage(null);
        setError(toApiError(err).message);
      });
    return () => controller.abort();
  }, [api, slug, refreshToken]);

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm font-medium uppercase tracking-wider text-zinc-400">
          Recent credentials
        </h3>
        {page ? <span className="text-sm text-zinc-500">{page.total} total</span> : null}
      </div>

      {error ? (
        <ErrorNote>{error}</ErrorNote>
      ) : page === null ? (
        <Skeleton rows={3} />
      ) : page.items.length === 0 ? (
        <EmptyNote>Nothing issued yet.</EmptyNote>
      ) : (
        <ul className="space-y-4">
          {page.items.map((credential) => (
            <li key={credential.id} className="flex items-start gap-3">
              <span
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                  credential.status === "issued"
                    ? "bg-emerald-500"
                    : credential.status === "failed"
                      ? "bg-red-500"
                      : "bg-zinc-600"
                }`}
                title={credential.status}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-zinc-200">
                  {credential.recipient_name}
                </p>
                <p className="truncate text-xs text-zinc-500">{credential.title}</p>
                <p className="mt-1 text-xs text-zinc-600">
                  {formatDate(credential.issued_at)} · {credential.status}
                  <DeliveryTag status={credential.delivery_status} />
                </p>
              </div>
              {credential.status === "issued" ? (
                <a
                  href={publicApi.verificationPageUrl(credential.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 text-xs text-indigo-400 transition-colors hover:text-indigo-300"
                >
                  Verify
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Flags the rows worth looking at. Deliberately silent for `sent` and
 *  `not_requested`: a list that tags every row tags nothing, and only a failure
 *  needs someone to act. `unknown` is silent too — those rows predate delivery
 *  tracking, and labelling them would assert something we do not know. */
function DeliveryTag({ status }: { status: DeliveryStatus | undefined }) {
  if (status !== "failed") return null;
  return (
    <>
      {" · "}
      <span className="text-amber-500/90" title="The credential issued, but its email did not send">
        email failed
      </span>
    </>
  );
}
