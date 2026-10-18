import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { EmptyState, Loading } from './components/ui'
import Overview from './pages/Overview'

const Suppliers = lazy(() => import('./pages/Suppliers'))
const SupplierDetail = lazy(() => import('./pages/SupplierDetail'))
const News = lazy(() => import('./pages/News'))
const ArticleDetail = lazy(() => import('./pages/ArticleDetail'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Sources = lazy(() => import('./pages/Sources'))
const Presenter = lazy(() => import('./pages/Presenter'))

export default function App() {
  return (
    <Shell>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/proveedores" element={<Suppliers />} />
          <Route path="/proveedores/:id" element={<SupplierDetail />} />
          <Route path="/noticias" element={<News />} />
          <Route path="/noticias/:id" element={<ArticleDetail />} />
          <Route path="/alertas" element={<Alerts />} />
          <Route path="/fuentes" element={<Sources />} />
          <Route path="/presentador" element={<Presenter />} />
          <Route
            path="*"
            element={
              <EmptyState title="Página no encontrada" action={<Link className="font-semibold text-accent-strong underline" to="/">Volver al resumen</Link>} />
            }
          />
        </Routes>
      </Suspense>
    </Shell>
  )
}
