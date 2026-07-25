import {
  Brain,
  Globe,
  Shield,
  Activity,
  Zap,
  Database,
  TrendingUp,
  Clock,
  ArrowUpRight,
} from 'lucide-react';
import { MainLayout } from '@/components/layout/main-layout';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

/* ── Stat Cards Data ────────────────────────────────── */
const stats = [
  {
    label: 'Active Agents',
    value: '12',
    change: '+3 this week',
    icon: Brain,
    gradient: 'from-primary to-primary-dark',
    badge: 'Live',
    badgeVariant: 'success' as const,
  },
  {
    label: 'Total Missions',
    value: '847',
    change: '+24 today',
    icon: Activity,
    gradient: 'from-accent to-cyan-600',
    badge: 'Active',
    badgeVariant: 'info' as const,
  },
  {
    label: 'Success Rate',
    value: '99.7%',
    change: '+0.2% vs last month',
    icon: TrendingUp,
    gradient: 'from-success to-emerald-600',
    badge: 'Excellent',
    badgeVariant: 'success' as const,
  },
  {
    label: 'Uptime',
    value: '99.99%',
    change: '365 days',
    icon: Clock,
    gradient: 'from-warning to-amber-600',
    badge: 'Stable',
    badgeVariant: 'warning' as const,
  },
];

/* ── Feature Cards Data ─────────────────────────────── */
const features = [
  {
    title: 'AI Orchestration',
    description:
      'Deploy, monitor, and manage intelligent agents across distributed environments with real-time coordination and adaptive task allocation.',
    icon: Zap,
    gradient: 'from-primary/10 to-accent/5',
    iconColor: 'text-primary',
    metrics: ['12 Active Agents', '3 Clusters', '< 50ms Latency'],
  },
  {
    title: 'Knowledge Federation',
    description:
      'Unified knowledge graph spanning petabytes of structured and unstructured data with federated learning capabilities across regions.',
    icon: Database,
    gradient: 'from-accent/10 to-success/5',
    iconColor: 'text-accent',
    metrics: ['2.4 PB Data', '15 Sources', '99.9% Sync'],
  },
  {
    title: 'Global Operations',
    description:
      'Enterprise-grade security, compliance, and auditability with zero-trust architecture and end-to-end encrypted communications.',
    icon: Globe,
    gradient: 'from-success/10 to-primary/5',
    iconColor: 'text-success',
    metrics: ['6 Regions', 'SOC2 Type II', 'Zero Breaches'],
  },
];

/* ── Page ────────────────────────────────────────────── */
export default function DashboardPage() {
  return (
    <MainLayout>
      {/* Page Header */}
      <div className="mb-8 animate-fade-in">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-text lg:text-4xl">
              Welcome to{' '}
              <span className="gradient-text">AIRA</span>
            </h1>
            <p className="mt-2 text-text-secondary max-w-xl">
              Your advanced intelligent resource allocation platform. Monitor agents,
              orchestrate missions, and manage knowledge — all in one place.
            </p>
          </div>
          <Badge variant="success" className="self-start sm:self-auto h-fit">
            <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-success animate-pulse" />
            All Systems Operational
          </Badge>
        </div>
      </div>

      {/* ── Stats Grid ──────────────────────────────── */}
      <div className="mb-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat, i) => {
          const Icon = stat.icon;
          return (
            <Card
              key={stat.label}
              hover
              className={`animate-fade-in delay-${(i + 1) * 100} relative overflow-hidden`}
              id={`stat-${stat.label.toLowerCase().replace(/\s+/g, '-')}`}
            >
              {/* Decorative gradient blob */}
              <div
                className={`absolute -top-6 -right-6 h-24 w-24 rounded-full bg-gradient-to-br ${stat.gradient} opacity-20 blur-2xl`}
              />
              <CardContent className="p-5 relative">
                <div className="flex items-start justify-between mb-3">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${stat.gradient} shadow-md`}
                  >
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <Badge variant={stat.badgeVariant}>{stat.badge}</Badge>
                </div>
                <p className="text-3xl font-bold text-text tracking-tight">{stat.value}</p>
                <p className="text-sm text-text-muted mt-0.5">{stat.label}</p>
                <div className="mt-3 flex items-center gap-1 text-xs text-success font-medium">
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  {stat.change}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ── Feature Cards ───────────────────────────── */}
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text mb-1">Core Capabilities</h2>
        <p className="text-sm text-text-muted mb-5">
          Enterprise-grade AI infrastructure powering your operations
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {features.map((feature, i) => {
          const Icon = feature.icon;
          return (
            <Card
              key={feature.title}
              hover
              className={`animate-fade-in delay-${(i + 1) * 100} group`}
              id={`feature-${feature.title.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <CardHeader>
                <div className={`mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${feature.gradient} border border-border/50`}>
                  <Icon className={`h-6 w-6 ${feature.iconColor} transition-transform duration-300 group-hover:scale-110`} />
                </div>
                <CardTitle>{feature.title}</CardTitle>
                <CardDescription>{feature.description}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex flex-wrap gap-2">
                  {feature.metrics.map((metric) => (
                    <Badge key={metric} variant="default">
                      {metric}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ── Quick Actions ───────────────────────────── */}
      <div className="mt-10 rounded-xl border border-border bg-gradient-to-r from-primary/5 via-transparent to-accent/5 p-6 animate-fade-in">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-text flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Quick Actions
            </h3>
            <p className="text-sm text-text-muted mt-1">
              Deploy a new agent, create a mission, or explore the knowledge graph.
            </p>
          </div>
          <div className="flex gap-3">
            <button className="focus-ring transition-base rounded-lg bg-gradient-to-r from-primary to-primary-dark px-4 py-2.5 text-sm font-medium text-white shadow-md hover:shadow-glow">
              Deploy Agent
            </button>
            <button className="focus-ring transition-base rounded-lg border border-border bg-surface px-4 py-2.5 text-sm font-medium text-text hover:bg-surface-secondary">
              New Mission
            </button>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
