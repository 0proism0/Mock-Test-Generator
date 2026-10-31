/**
 * Single source of truth for UI icons.
 *
 * The icon language is Feather: `react-feather` supplies the set, and where Feather
 * has no glyph for a concept (games, PK swords, school, category subjects) we fall
 * back to `lucide-react` — a maintained continuation of Feather with the same 24px
 * stroked style — so the look stays consistent. Import icons from here, never from
 * the packages directly, and never hand-write <svg> or use emoji as an icon.
 */

// Feather (react-feather)
export {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart2,
  BookOpen,
  Check,
  Clock,
  Compass,
  Cpu,
  DollarSign,
  Edit3,
  FileText,
  Grid,
  LogIn,
  LogOut,
  Plus,
  PlusSquare,
  RotateCcw,
  Target,
  TrendingUp,
  User,
  Users,
  X,
} from 'react-feather'

// lucide-react — fills the gaps Feather doesn't cover (same Feather style)
export {
  Atom,
  Dna,
  Flag,
  Flame,
  FlaskConical,
  Gamepad2,
  Keyboard,
  Languages,
  Moon,
  School,
  Sun,
  Swords,
  Telescope,
} from 'lucide-react'
