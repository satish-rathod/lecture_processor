import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Home, Clock, Settings } from 'lucide-react';
import HomePage from './pages/HomePage';
import QueuePage from './pages/QueuePage';
import RecordingPage from './pages/RecordingPage';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-background">
        {/* Sidebar */}
        <aside className="w-60 border-r border-border p-4 fixed h-screen bg-[#1e1e1e]">
          <div className="mb-8">
            <h1 className="text-lg font-semibold text-foreground">
              Lecture Companion
            </h1>
            <p className="text-xs text-muted-foreground mt-1">
              AI-powered study assistant
            </p>
          </div>

          <nav className="space-y-1">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${isActive
                  ? 'bg-accent text-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                }`
              }
            >
              <Home size={18} />
              <span>Library</span>
            </NavLink>

            <NavLink
              to="/queue"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${isActive
                  ? 'bg-accent text-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                }`
              }
            >
              <Clock size={18} />
              <span>Processing</span>
            </NavLink>
          </nav>

          <div className="absolute bottom-4 left-4 right-4">
            <div className="text-xs text-muted-foreground">
              v1.0.0
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 ml-60 p-8 min-h-screen">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="/recording/:id" element={<RecordingPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
