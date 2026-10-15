/** Scaffold placeholder for a not-yet-ported legacy tab. */
export function Placeholder({ title }: { title: string }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      <p className="muted">
        Scaffold placeholder — this view will port the matching tab from the legacy{' '}
        <code>app/static/index.html</code>.
      </p>
    </section>
  )
}
