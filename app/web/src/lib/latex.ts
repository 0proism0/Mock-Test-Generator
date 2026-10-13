/**
 * Legacy sanitizeLatex(): normalise unsupported math environments, drop labels/tags,
 * and escape a trailing unpaired `$` so it can't swallow the following text.
 */
export function sanitizeLatex(s: string): string {
  let out = s
    .replace(/\\begin\{(align|align\*|split|eqnarray|gather)\}/g, '\\begin{aligned}')
    .replace(/\\end\{(align|align\*|split|eqnarray|gather)\}/g, '\\end{aligned}')
    .replace(/\\label\{[^}]*\}/g, '')
    .replace(/\\tag\{[^}]*\}/g, '')
    .replace(/\\notag/g, '')
  const dollars = out.match(/(?<!\\)\$/g)
  if (dollars && dollars.length % 2 === 1) {
    const i = out.lastIndexOf('$')
    out = out.slice(0, i) + '\\$' + out.slice(i + 1)
  }
  return out
}
