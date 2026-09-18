export function UnsafeInnerHtml({ html }: { html: string }) {
  return <article dangerouslySetInnerHTML={{ __html: html }} />; // nosemgrep: javascript-no-dangerously-set-inner-html
}
