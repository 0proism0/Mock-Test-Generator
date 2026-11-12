import { useEffect, useState } from 'react'
import { Download, FileText } from '../components/icons'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

type ShsidData = Awaited<ReturnType<typeof api.shsid>>

function fmtSize(n: number): string {
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${Math.round(n / 1024)} KB`
}

/** Crawled SHSID LinkedClassroom papers (scraper/shsid_crawler.py), browse + download. */
export function SHSID() {
  const { t } = useI18n()
  const [data, setData] = useState<ShsidData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .shsid()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <section className="card"><p className="status err">{error}</p></section>
  if (!data) return <section className="card"><p className="muted">{t('loading')}</p></section>

  const totalFiles = data.courses.reduce(
    (n, c) =>
      n +
      c.sections.reduce(
        (m, s) => m + s.activities.reduce((k, a) => k + (a.files?.length ?? 0), 0),
        0,
      ),
    0,
  )

  return (
    <>
      <section className="card">
        <h3>{t('tabSHSID')}</h3>
        <p className="muted">{t('shsidDesc')}</p>
        {data.courses.length === 0 || totalFiles === 0 ? (
          <p className="muted">{t('shsidEmpty')}</p>
        ) : (
          <p className="muted">
            {data.courses.length} {t('shsidCourses')} · {totalFiles} {t('shsidFiles')}
          </p>
        )}
      </section>
      {data.courses.map((c) => {
        const courseFiles = c.sections.reduce(
          (n, s) => n + s.activities.reduce((m, a) => m + (a.files?.length ?? 0), 0),
          0,
        )
        if (courseFiles === 0) return null
        return (
          <section key={c.course_id} className="card">
            <h3>
              <FileText size={16} /> {c.course_title}
            </h3>
            {c.sections.map((s, i) => {
              const secFiles = s.activities.flatMap((a) => a.files ?? [])
              if (secFiles.length === 0) return null
              return (
                <div key={i} className="shsid-sec">
                  <h4 className="shsid-sec-head">{s.section_title}</h4>
                  <ul className="shsid-files">
                    {secFiles.map((f) => (
                      <li key={f.path}>
                        <a className="link" href={`/shsid-files/${f.path.slice('raw/shsid/'.length)}`}>
                          <Download size={13} /> {f.name}
                        </a>
                        <span className="meta">
                          {' '}
                          · {f.ext.toUpperCase()} · {fmtSize(f.size)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </section>
        )
      })}
    </>
  )
}
