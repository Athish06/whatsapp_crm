import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  LayoutDashboard, 
  Send, 
  Activity, 
  FileText, 
  History, 
  Settings, 
  LogOut,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const Sidebar = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { logout } = useAuth();

  const menuItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
    { icon: Send, label: 'Campaign', path: '/campaign' },
    { icon: Activity, label: 'Monitor', path: '/monitor' },
    { icon: FileText, label: 'Templates', path: '/templates' },
    { icon: History, label: 'History', path: '/history' },
    { icon: Settings, label: 'Settings', path: '/settings' },
  ];

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div 
      className={`bg-[#1C1C1C] border-r border-[#2E2E2E] flex flex-col transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-64'
      }`}
      data-testid="sidebar"
    >
      {/* Header */}
      <div className="p-4 border-b border-[#2E2E2E] flex items-center justify-between">
        {!collapsed && (
          <h2 className="font-bold text-lg" style={{ fontFamily: 'Chivo, sans-serif' }}>
            WA CRM Pro
          </h2>
        )}
        <button
          data-testid="toggle-sidebar-btn"
          onClick={() => setCollapsed(!collapsed)}
          className="p-1 hover:bg-[#2E2E2E] rounded transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <ChevronLeft className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Menu Items */}
      <nav className="flex-1 p-2">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          
          return (
            <button
              key={item.path}
              data-testid={`nav-${item.label.toLowerCase()}`}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-all mb-1 ${
                isActive 
                  ? 'bg-[#3ECF8E]/10 text-[#3ECF8E] border border-[#3ECF8E]/20' 
                  : 'hover:bg-[#2E2E2E] text-muted-foreground hover:text-white'
              }`}
            >
              <Icon className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
              {!collapsed && (
                <span className="text-sm font-medium">{item.label}</span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-2 border-t border-[#2E2E2E]">
        <button
          data-testid="logout-btn"
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-all"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
          {!collapsed && (
            <span className="text-sm font-medium">Logout</span>
          )}
        </button>
      </div>
    </div>
  );
};

export default Sidebar;
