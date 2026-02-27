import { Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import BuildPage from './pages/BuildPage';
import ResourcesPage from './pages/ResourcesPage';
import Header from './components/Header';
import Footer from './components/Footer';
import { LeagueProvider } from './contexts/league-context';

/**
 * Application root with route definitions, header/footer shell, and
 * the LeagueProvider so all pages can read the selected league.
 */
export default function App() {
  return (
    <LeagueProvider>
      <div className="min-h-screen bg-gray-950 flex flex-col">
        <Header />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/build" element={<BuildPage />} />
            <Route path="/resources" element={<ResourcesPage />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </LeagueProvider>
  );
}
