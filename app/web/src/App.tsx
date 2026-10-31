import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { Placeholder } from './routes/Placeholder'

// Routes are lazy-loaded so the heavy KaTeX/Whiteboard/Games code only ships when visited.
const NewTest = lazy(() => import('./routes/NewTest').then((m) => ({ default: m.NewTest })))
const Worksheet = lazy(() => import('./routes/Worksheet').then((m) => ({ default: m.Worksheet })))
const Practice = lazy(() => import('./routes/Practice').then((m) => ({ default: m.Practice })))
const MyTests = lazy(() => import('./routes/MyTests').then((m) => ({ default: m.MyTests })))
const TestRunner = lazy(() => import('./routes/TestRunner').then((m) => ({ default: m.TestRunner })))
const Stats = lazy(() => import('./routes/Stats').then((m) => ({ default: m.Stats })))
const Whiteboard = lazy(() => import('./routes/Whiteboard').then((m) => ({ default: m.Whiteboard })))
const Games = lazy(() => import('./routes/Games').then((m) => ({ default: m.Games })))
const Friends = lazy(() => import('./routes/Friends').then((m) => ({ default: m.Friends })))
const Pk = lazy(() => import('./routes/Pk').then((m) => ({ default: m.Pk })))
const Classes = lazy(() => import('./routes/Classes').then((m) => ({ default: m.Classes })))
const Login = lazy(() => import('./routes/Login').then((m) => ({ default: m.Login })))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<NewTest />} />
        <Route path="worksheet" element={<Worksheet />} />
        <Route path="practice" element={<Practice />} />
        <Route path="tests" element={<MyTests />} />
        <Route path="stats" element={<Stats />} />
        <Route path="whiteboard" element={<Whiteboard />} />
        <Route path="games" element={<Games />} />
        <Route
          path="friends"
          element={
            <RequireAuth>
              <Friends />
            </RequireAuth>
          }
        />
        <Route
          path="pk"
          element={
            <RequireAuth>
              <Pk />
            </RequireAuth>
          }
        />
        <Route
          path="classes"
          element={
            <RequireAuth>
              <Classes />
            </RequireAuth>
          }
        />
        <Route path="login" element={<Login />} />
        <Route path="test/:id" element={<TestRunner />} />
        <Route path="*" element={<Placeholder title="Not found" />} />
      </Route>
    </Routes>
  )
}
