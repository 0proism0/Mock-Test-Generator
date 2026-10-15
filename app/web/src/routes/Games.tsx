import { useState } from 'react'
import { ArrowRight, Target, TrendingUp } from '../components/icons'
import { useI18n } from '../lib/i18n'
import { FunctionChess } from './games/FunctionChess'
import { GraphWar } from './games/GraphWar'

/** Legacy "Games" tab: a small game list that swaps to the selected game. */
export function Games() {
  const { t, tip } = useI18n()
  const [view, setView] = useState<'list' | 'fc' | 'gw'>('list')

  if (view === 'fc') return <FunctionChess onBack={() => setView('list')} />
  if (view === 'gw') return <GraphWar onBack={() => setView('list')} />

  return (
    <div className="card">
      <h3>{t('tabGames')}</h3>
      <div className="game-list">
        <div className="card compact game-card" onClick={() => setView('fc')}>
          <h3>
            <Target size={18} /> {tip('gChess')}
          </h3>
          <p style={{ color: '#666', fontSize: 13.5, margin: '6px 0 10px' }}>{t('gChessDesc')}</p>
          <button className="btn sm" type="button">
            {t('gPlay')} <ArrowRight size={13} />
          </button>
        </div>
        <div className="card compact game-card" onClick={() => setView('gw')}>
          <h3>
            <TrendingUp size={18} /> {tip('gGraph')}
          </h3>
          <p style={{ color: '#666', fontSize: 13.5, margin: '6px 0 10px' }}>{t('gGraphDesc')}</p>
          <button className="btn sm" type="button">
            {t('gPlay')} <ArrowRight size={13} />
          </button>
        </div>
      </div>
    </div>
  )
}
