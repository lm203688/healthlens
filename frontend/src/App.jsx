import { Routes, Route, NavLink, useNavigate, Navigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import HealthAssess from './pages/HealthAssess';
import TCMConstitution from './pages/TCMConstitution';
import PulseDevice from './pages/PulseDevice';
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
  { to: '/pulse',      key: 'nav.pulse', icon: '🫀' },
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

// 移动端底部导航（5 个核心入口，其余走桌面端）
const MOBILE_NAV_ITEMS = [
  { to: '/',        key: 'nav.dashboard', icon: '🏠' },
  { to: '/assess',  key: 'nav.healthAssess', icon: '🩺' },
  { to: '/reports', key: 'nav.reports', icon: '📊' },
  { to: '/agent',   key: 'nav.agent', icon: '🤖' },
  { to: '/profile', key: 'nav.profile', icon: '👤' },
];

// P0-8：公开路由（无需登录）
const PUBLIC_ROUTES = ['/login', '/share'];

/** 路由守卫：未登录时重定向到 /login */
function RequireAuth({ children }) {
  const location = useLocation();
  const token = localStorage.getItem('token');
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

export default function App() {
  const { t } = useTranslation();
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [user, setUser] = useState(() => localStorage.getItem('user_email'));
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // P0-8：token 过期检查（每 5 分钟轮询一次）
  useEffect(() => {
    const checkExpiry = () => {
      const stored = localStorage.getItem('token_expires');
      if (stored) {
        const expires = parseInt(stored, 10);
        if (expires && Date.now() > expires) {
          // token 过期，尝试刷新
          const refreshToken = localStorage.getItem('refresh_token');
          if (refreshToken) {
            refreshAuth(refreshToken);
          } else {
            logout();
          }
        }
      }
    };
    const interval = setInterval(checkExpiry, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // 路由变化时同步 token/user 状态 + 关闭移动端菜单
  useEffect(() => {
    setToken(localStorage.getItem('token'));
    setUser(localStorage.getItem('user_email'));
    setMobileMenuOpen(false);
  }, [location.pathname]);

  function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('refresh_token_expires');
    localStorage.removeItem('token_expires');
    localStorage.removeItem('user_email');
    setToken(null);
    setUser(null);
    navigate('/login');
  }

  // P0-8：token 刷新
  async function refreshAuth(refreshToken) {
    try {
      const resp = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (resp.ok) {
        const data = await resp.json();
        const newToken = data.access_token || data.data?.access_token;
        if (newToken) {
          localStorage.setItem('token', newToken);
          setToken(newToken);
          if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token);
          }
          if (data.token_expires_in) {
            localStorage.setItem('token_expires', String(Date.now() + data.token_expires_in * 1000));
          }
        }
      } else {
        logout();
      }
    } catch {
      logout();
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm border-b border-slate-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2 font-bold text-emerald-700 text-lg">
            <span className="text-xl">🔬</span>
            <span className="hidden sm:inline">HealthLens</span>
          </NavLink>

          {/* 桌面端导航 */}
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
            {/* 移动端汉堡菜单按钮 */}
            <button
              className="md:hidden p-2 rounded-lg text-slate-600 hover:bg-slate-100"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileMenuOpen
                  ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* 移动端下拉菜单 */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-white border-b border-slate-100 shadow-lg max-h-96 overflow-y-auto">
          <nav className="px-4 py-2 space-y-1">
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'text-slate-600 hover:bg-slate-50'
                  }`
                }
              >
                <span className="text-lg">{item.icon}</span> {t(item.key)}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      <main className="max-w-6xl mx-auto px-4 py-6 pb-20 md:pb-6">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/share" element={<Share />} />
          <Route path="/" element={
            <RequireAuth><Dashboard /></RequireAuth>
          } />
          <Route path="/assess" element={
            <RequireAuth><HealthAssess /></RequireAuth>
          } />
          <Route path="/tcm" element={
            <RequireAuth><TCMConstitution /></RequireAuth>
          } />
          <Route path="/pulse" element={
            <RequireAuth><PulseDevice /></RequireAuth>
          } />
          <Route path="/axes" element={
            <RequireAuth><AxisProfile /></RequireAuth>
          } />
          <Route path="/checkin" element={
            <RequireAuth><CheckIn /></RequireAuth>
          } />
          <Route path="/reports" element={
            <RequireAuth><Reports /></RequireAuth>
          } />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/agent" element={
            <RequireAuth><AgentChat /></RequireAuth>
          } />
          <Route path="/upload" element={
            <RequireAuth><Upload /></RequireAuth>
          } />
          <Route path="/retention" element={
            <RequireAuth><Retention /></RequireAuth>
          } />
          <Route path="/payment" element={
            <RequireAuth><Payment /></RequireAuth>
          } />
          <Route path="/profile" element={
            <RequireAuth><Profile /></RequireAuth>
          } />
        </Routes>
      </main>

      {/* P0-8：移动端底部导航栏 */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-20 shadow-lg">
        <div className="flex items-center justify-around h-14">
          {MOBILE_NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center px-2 py-1 rounded-lg text-xs font-medium transition ${
                  isActive
                    ? 'text-emerald-700'
                    : 'text-slate-500'
                }`
              }
            >
              <span className="text-lg mb-0.5">{item.icon}</span>
              {t(item.key)}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
