import { Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import HealthAssess from './pages/HealthAssess';
import TCMConstitution from './pages/TCMConstitution';
import CheckIn from './pages/CheckIn';
import Reports from './pages/Reports';
import Knowledge from './pages/Knowledge';
import AgentChat from './pages/AgentChat';
import Login from './pages/Login';
import Profile from './pages/Profile';

const NAV_ITEMS = [
  { to: '/',           label: '首页',        icon: '🏠' },
  { to: '/assess',     label: '健康评估',    icon: '🩺' },
  { to: '/tcm',        label: '体质辨识',    icon: '🏥' },
  { to: '/checkin',    label: '每日打卡',    icon: '📅' },
  { to: '/reports',    label: '健康报告',    icon: '📊' },
  { to: '/knowledge',  label: '知识探索',    icon: '📚' },
  { to: '/agent',      label: 'AI 对话',     icon: '🤖' },
  { to: '/profile',    label: '个人档案',    icon: '👤' },
];

export default function App() {
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
                <span className="mr-1">{item.icon}</span> {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {token && user ? (
              <>
                <span className="text-xs text-slate-500 hidden sm:inline">{user}</span>
                <button
                  onClick={logout}
                  className="px-3 py-1.5 bg-slate-100 text-slate-600 text-sm rounded-lg hover:bg-slate-200 transition"
                >
                  退出
                </button>
              </>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="px-3 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 transition"
              >
                登录
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
          <Route path="/checkin" element={<CheckIn />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/agent" element={<AgentChat />} />
          <Route path="/profile" element={<Profile />} />
        </Routes>
      </main>
    </div>
  );
}
