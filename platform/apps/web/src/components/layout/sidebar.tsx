'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  LayoutDashboard,
  BarChart3,
  Bot,
  Target,
  GitBranch,
  BookOpen,
  Network,
  Settings,
  Shield,
  FileText,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface SidebarItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

const sections: SidebarSection[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', href: '/', icon: LayoutDashboard },
      { label: 'Analytics', href: '/analytics', icon: BarChart3 },
    ],
  },
  {
    title: 'AI Operations',
    items: [
      { label: 'Agents', href: '/agents', icon: Bot },
      { label: 'Missions', href: '/missions', icon: Target },
      { label: 'Workflows', href: '/workflows', icon: GitBranch },
    ],
  },
  {
    title: 'Data',
    items: [
      { label: 'Knowledge Base', href: '/knowledge', icon: BookOpen },
      { label: 'Federation', href: '/federation', icon: Network },
    ],
  },
  {
    title: 'System',
    items: [
      { label: 'Settings', href: '/settings', icon: Settings },
      { label: 'Security', href: '/security', icon: Shield },
      { label: 'Audit Log', href: '/audit', icon: FileText },
    ],
  },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [activeHref, setActiveHref] = useState('/');

  return (
    <aside
      className={`hidden lg:flex flex-col border-r border-border bg-surface-secondary/50 transition-all duration-300 ${
        collapsed ? 'w-[68px]' : 'w-60'
      }`}
      id="sidebar"
    >
      {/* Collapse toggle */}
      <div className="flex justify-end p-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="focus-ring transition-base flex h-7 w-7 items-center justify-center rounded-md hover:bg-surface-tertiary text-text-muted"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          id="sidebar-toggle"
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Sections */}
      <nav className="flex-1 overflow-y-auto px-2 pb-4 space-y-5">
        {sections.map((section) => (
          <div key={section.title}>
            {!collapsed && (
              <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeHref === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={() => setActiveHref(item.href)}
                      title={collapsed ? item.label : undefined}
                      className={`focus-ring transition-base flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${
                        isActive
                          ? 'bg-primary/10 text-primary shadow-sm'
                          : 'text-text-secondary hover:text-text hover:bg-surface-tertiary'
                      } ${collapsed ? 'justify-center' : ''}`}
                    >
                      <Icon className={`h-[18px] w-[18px] shrink-0 ${isActive ? 'text-primary' : ''}`} />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Bottom branding */}
      {!collapsed && (
        <div className="border-t border-border p-4">
          <p className="text-[11px] text-text-muted text-center">AIRA Platform v1.5</p>
        </div>
      )}
    </aside>
  );
}
