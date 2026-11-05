/**
 * Single source of truth for UI icons.
 *
 * The icon language is Feather: `react-feather` supplies the set, and where Feather
 * has no glyph for a concept (games, PK swords, school, maths operators used by the
 * practice drills) we fall back to `lucide-react` — a maintained continuation of
 * Feather with the same 24px stroked style — so the look stays consistent. Import
 * icons from here, never from the packages directly, and never hand-write <svg> or
 * use emoji as an icon.
 */

import type { ComponentType } from 'react'

/** Common shape of every icon re-exported below, for data-driven icon maps. */
export type IconComponent = ComponentType<{
  size?: string | number
  className?: string
  strokeWidth?: number
  'aria-hidden'?: boolean | 'true' | 'false'
}>

// Feather (react-feather)
export {
  Activity,
  AlertTriangle,
  Archive,
  ArrowLeft,
  ArrowRight,
  BarChart2,
  BookOpen,
  Box,
  Check,
  Circle,
  Clock,
  Compass,
  Cpu,
  Crosshair,
  Divide,
  DollarSign,
  Edit3,
  EyeOff,
  FileText,
  Folder,
  Grid,
  Hash,
  Key,
  Layers,
  Link2,
  LogIn,
  LogOut,
  MapPin,
  Minus,
  Percent,
  Plus,
  PlusSquare,
  Printer,
  Repeat,
  RotateCcw,
  Search,
  Shuffle,
  Slash,
  Tag,
  Target,
  TrendingUp,
  Triangle,
  User,
  Users,
  X,
  XCircle,
} from 'react-feather'

// lucide-react — fills the gaps Feather doesn't cover (same Feather style)
export {
  Asterisk,
  Atom,
  Binary,
  Blocks,
  Brackets,
  Calculator,
  Car,
  CircleDot,
  Dice5,
  Dices,
  Dna,
  Dot,
  Dumbbell,
  Equal,
  Flag,
  Flame,
  FlaskConical,
  FolderOpen,
  FunctionSquare,
  Gamepad2,
  Grid3x3,
  Hammer,
  Keyboard,
  Landmark,
  Languages,
  LineChart,
  ListOrdered,
  Moon,
  MoveRight,
  Puzzle,
  Radical,
  Recycle,
  Ruler,
  Scale,
  School,
  Spline,
  Sun,
  Superscript,
  Swords,
  Telescope,
  Trophy,
  Waves,
  Waypoints,
} from 'lucide-react'
