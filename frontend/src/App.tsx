import { Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import BuildPage from './pages/BuildPage';

/**
 * Application root with route definitions.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/build" element={<BuildPage />} />
    </Routes>
  );
}
