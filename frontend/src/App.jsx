import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";
import OnboardingModal from "./components/OnboardingModal";
import DashboardPage from "./pages/DashboardPage";
import ResultDetailPage from "./pages/ResultDetailPage";
import ResultsListPage from "./pages/ResultsListPage";
import { ToastContainer } from "./toast";

const navLinkClass = ({ isActive }) =>
  `text-sm px-3 py-1.5 rounded-md transition-colors ${
    isActive ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:text-gray-900"
  }`;

function PageRoutes() {
  const location = useLocation();
  return (
    // keyed by pathname so every navigation plays the fade-slide transition
    <div key={location.pathname} className="page-enter">
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/results" element={<ResultsListPage />} />
        <Route path="/results/:id" element={<ResultDetailPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    // Django serves the SPA at the site root, so the router sees plain paths.
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100 text-gray-900 flex flex-col">
        <nav className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center gap-2">
            <span className="font-semibold text-gray-800 mr-2">🏷️ Shopify Product Classifier</span>
            <NavLink to="/dashboard" className={navLinkClass} end>
              Dashboard
            </NavLink>
            <NavLink to="/results" className={navLinkClass}>
              Results
            </NavLink>
            <a
              href="/admin/"
              className="ml-auto text-sm text-gray-600 hover:text-gray-900 px-3 py-1.5"
            >
              Admin
            </a>
          </div>
        </nav>

        <main className="max-w-7xl mx-auto px-4 py-6 flex-1 w-full">
          <PageRoutes />
        </main>

        <footer className="border-t border-gray-200 bg-white">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between text-xs text-gray-400">
            <span>Shopify Product Classifier · local prototype</span>
            <span>
              Text + image classification · taxonomy from Shopify Product Taxonomy
            </span>
          </div>
        </footer>

        <OnboardingModal />
        <ToastContainer />
      </div>
    </BrowserRouter>
  );
}