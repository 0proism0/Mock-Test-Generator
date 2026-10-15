import type { ComponentType } from 'react'
import {
  Atom,
  BookOpen,
  Compass,
  Cpu,
  Dna,
  DollarSign,
  FlaskConical,
  Languages,
  Telescope,
} from './icons'

type IconType = ComponentType<{ size?: number | string }>

// Category → icon, replacing the legacy catIcon() emoji map. Subjects without a
// Feather glyph come from lucide (FlaskConical, Dna, Telescope, Languages, Atom).
const CATEGORY_ICONS: Record<string, IconType> = {
  Math: Compass,
  Physics: Atom,
  Chemistry: FlaskConical,
  Biology: Dna,
  Informatics: Cpu,
  'Astronomy & Earth': Telescope,
  Economics: DollarSign,
  Linguistics: Languages,
  Other: BookOpen,
}

export function CategoryIcon({ category, size = 18 }: { category: string; size?: number }) {
  const Icon = CATEGORY_ICONS[category] ?? BookOpen
  return <Icon size={size} />
}
