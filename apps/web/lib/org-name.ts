/** Whether an organization still has the name it was given automatically at
 *  sign-up — "Priya's Organization" — rather than one someone chose. Only the
 *  exact suffix counts: "Acme Organization" was typed by a person. */
export function looksAutoNamed(name: string): boolean {
  return /\S['’]s organization$/i.test(name.trim());
}
