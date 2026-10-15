import renderMathInElement from 'katex/contrib/auto-render'
import { useEffect, useMemo, useRef } from 'react'
import { sanitizeLatex } from '../lib/latex'
import 'katex/dist/katex.min.css'

const DELIMITERS = [
  { left: '$$', right: '$$', display: true },
  { left: '$', right: '$', display: false },
]

const MACROS = {
  '\\textsc': '\\text{#1}',
  '\\overarc': '\\widehat{#1}',
  '\\ds': '',
}

interface AutoMathProps {
  /** Text/HTML that may contain `$…$` or `$$…$$` math. Rendered as raw HTML (parity with legacy innerHTML). */
  html?: string
  children?: string
  className?: string
}

/**
 * Renders mixed text + LaTeX with KaTeX's auto-render, replacing the legacy renderMath().
 * Mirrors the legacy delimiters (`$$`, `$`) and macros exactly.
 */
export function AutoMath({ html, children, className }: AutoMathProps) {
  const ref = useRef<HTMLDivElement>(null)
  const content = useMemo(() => sanitizeLatex(html ?? children ?? ''), [html, children])

  useEffect(() => {
    if (ref.current) {
      renderMathInElement(ref.current, {
        throwOnError: false,
        trust: true,
        macros: MACROS,
        delimiters: DELIMITERS,
      })
    }
  }, [content])

  return <div ref={ref} className={className} dangerouslySetInnerHTML={{ __html: content }} />
}
