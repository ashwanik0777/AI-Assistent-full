'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Menu, X, Bell } from 'lucide-react';
import { ThemeToggle } from '@/components/theme/theme-toggle';

const navLinks = [
  { label: 'Dashboard', href: '/' },
  { label: 'Agents', href: '/agents' },
  { label: 'Missions', href: '/missions' },
  { label: 'Knowledge', href: '/knowledge' },
];

export function Header() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="glass sticky top-0 z-50 border-b border-border/60">
      <div className="flex h-16 items-center justify-between px-4 lg:px-6">
        {/* Left — Logo */}
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group" id="header-logo">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent shadow-md group-hover:shadow-glow transition-shadow duration-300">
              <span className="text-sm font-bold text-white tracking-tight">A</span>
            </div>
            <span className="gradient-text text-xl font-bold tracking-tight hidden sm:inline">
              AIRA
            </span>
          </Link>
        </div>

        {/* Center — Desktop Nav */}
        <nav className="hidden md:flex items-center gap-1" id="main-nav">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="focus-ring transition-base rounded-lg px-3.5 py-2 text-sm font-medium text-text-secondary hover:text-text hover:bg-surface-secondary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Right — Actions */}
        <div className="flex items-center gap-2">
          <button
            className="focus-ring transition-base relative flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface-secondary hover:bg-surface-tertiary"
            aria-label="Notifications"
            id="notifications-btn"
          >
            <Bell className="h-[18px] w-[18px] text-text-secondary" />
            <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-error text-[9px] font-bold text-white">
              3
            </span>
          </button>
          <ThemeToggle />
          <div
            className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-primary to-accent text-xs font-bold text-white cursor-pointer"
            id="user-avatar"
            title="User"
          >
            AK
          </div>

          {/* Mobile toggle */}
          <button
            className="focus-ring transition-base flex h-9 w-9 items-center justify-center rounded-lg md:hidden"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle navigation"
            id="mobile-menu-btn"
          >
            {mobileOpen ? (
              <X className="h-5 w-5 text-text" />
            ) : (
              <Menu className="h-5 w-5 text-text" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile Nav */}
      {mobileOpen && (
        <nav className="border-t border-border/60 px-4 py-3 md:hidden animate-fade-in" id="mobile-nav">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="block rounded-lg px-3 py-2.5 text-sm font-medium text-text-secondary hover:text-text hover:bg-surface-secondary transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
