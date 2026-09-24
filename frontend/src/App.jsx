import { Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Dashboard from './pages/Dashboard';
import HealthAssess from './pages/HealthAssess';
import TCMConstitution from './pages/TCMConstitution';
import AxisProfile from './pages/AxisProfile';
import CheckIn from './pages/CheckIn';
import Reports from './pages/Reports';
import Knowledge from './pages/Knowledge';
import AgentChat from './pages/AgentChat';
import Login from './pages/Login';
import Profile from './pages/Profile';
import Payment from './pages/Payment';
import Upload from './pages/Upload';
import Share from './pages/Share';
import Retention from './pages/Retention';
import LanguageSwitcher from './components/LanguageSwitcher';

const NAV_ITEMS = [
  { to: '/',           key: 'nav.dashboard', icon: '🏠' },
  { to: '/assess',     key: 'nav.healthAssess', icon: '🩺' },
  { to: '/tcm',        key: 'nav.tcm', icon: '🏥' },
  { to: '/axes',       key: 'nav.axis', icon: '🧭' },
  { to: '/checkin',    key: 'nav.checkin', icon: '📅' },
  { to: '/reports',    key: 'nav.reports', icon: '📊' },
  { to: '/knowledge',  key: 'nav.knowledge', icon: '📚' },
  { to: '/agent',      key: 'nav.agent', icon: '🤖' },
  { to: '/upload',     key: 'nav.upload', icon: '📤' },
  { to: '/retention',  key: 'nav.retention', icon: '🎯' },
  { to: '/share',      key: 'nav.share', icon: '🔗' },
  { to: '/payment',    key: 'nav.payment', icon: '💎' },
  { to: '/profile',    key: 'nav.profile', icon: '👤' },
];

export default function App() {
  const { t } = useTranslation();
  const token = localStorage.getItem('token');
  const user = localStorage.getItem('user_email');
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_email');
    navigate('/login');
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm border-b border-slate-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2 font-bold text-emerald-700 text-lg">
            <span className="text-xl">🔬</span>
            <span>HealthLens</span>
          </NavLink>

          <nav className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'text-slate-600 hover:text-emerald-700 hover:bg-slate-50'
                  }`
                }
              >
                <span className="mr-1">{item.icon}</span> {t(item.key)}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            {token && user ? (
              <>
                <span className="text-xs text-slate-500 hidden sm:inline">{user}</span>
                <button
                  onClick={logout}
                  className="px-3 py-1.5 bg-slate-100 text-slate-600 text-sm rounded-lg hover:bg-slate-200 transition"
                >
                  {t('nav.logout')}
                </button>
              </>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="px-3 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 transition"
              >
                {t('nav.login')}
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Dashboard />} />
          <Route path="/assess" element={<HealthAssess />} />
          <Route path="/tcm" element={<TCMConstitution />} />
          <Route path="/axes" element={<AxisProfile />} />
          <Route path="/checkin" element={<CheckIn />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/agent" element={<AgentChat />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/share" element={<Share />} />
          <Route path="/retention" element={<Retention />} />
          <Route path="/payment" element={<Payment />} />
          <Route path="/profile" element={<Profile />} />
        </Routes>
      </main>
    </div>
  );
}
