import React, { useState, useEffect } from 'react';
import { dashboardAPI } from '../lib/api';
import { Users, Send, AlertCircle, Activity, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';

const DashboardPage = () => {
  const [stats, setStats] = useState({
    total_customers: 0,
    messages_sent: 0,
    messages_failed: 0,
    active_batches: 0,
    templates_count: 0
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const response = await dashboardAPI.getStats();
      setStats(response.data);
    } catch (error) {
      toast.error('Failed to load dashboard stats');
    } finally {
      setLoading(false);
    }
  };

  const metrics = [
    {
      title: 'Total Customers',
      value: stats.total_customers,
      icon: Users,
      color: '#3ECF8E',
      bgGlow: 'rgba(62, 207, 142, 0.1)'
    },
    {
      title: 'Messages Sent',
      value: stats.messages_sent,
      icon: Send,
      color: '#3B82F6',
      bgGlow: 'rgba(59, 130, 246, 0.1)'
    },
    {
      title: 'Failed Messages',
      value: stats.messages_failed,
      icon: AlertCircle,
      color: '#EF4444',
      bgGlow: 'rgba(239, 68, 68, 0.1)'
    },
    {
      title: 'Active Batches',
      value: stats.active_batches,
      icon: Activity,
      color: '#F59E0B',
      bgGlow: 'rgba(245, 158, 11, 0.1)'
    }
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-muted-foreground">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Dashboard Overview
        </h1>
        <p className="text-muted-foreground">
          Monitor your WhatsApp marketing campaigns in real-time
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="metrics-grid">
        {metrics.map((metric, index) => {
          const Icon = metric.icon;
          return (
            <div
              key={index}
              data-testid={`metric-card-${metric.title.toLowerCase().replace(/\s+/g, '-')}`}
              className="relative bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 hover:border-[#3E3E3E] transition-all overflow-hidden group"
            >
              {/* Glow effect */}
              <div 
                className="absolute top-1/2 left-1/2 w-48 h-48 -translate-x-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                style={{ 
                  background: `radial-gradient(circle, ${metric.bgGlow} 0%, transparent 70%)`,
                  pointerEvents: 'none'
                }}
              />
              
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-4">
                  <Icon className="w-5 h-5" style={{ color: metric.color }} strokeWidth={1.5} />
                  <TrendingUp className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                </div>
                
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">{metric.title}</p>
                  <p 
                    className="text-3xl font-semibold" 
                    style={{ fontFamily: 'JetBrains Mono, monospace' }}
                  >
                    {metric.value.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick Actions */}
      <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="/campaign"
            data-testid="create-campaign-btn"
            className="p-4 bg-[#121212] border border-[#2E2E2E] rounded-md hover:border-[#3ECF8E] transition-all group"
          >
            <h3 className="font-medium mb-1 group-hover:text-[#3ECF8E] transition-colors">
              Create Campaign
            </h3>
            <p className="text-sm text-muted-foreground">
              Upload customers and start a new messaging campaign
            </p>
          </a>
          
          <a
            href="/monitor"
            data-testid="monitor-batches-btn"
            className="p-4 bg-[#121212] border border-[#2E2E2E] rounded-md hover:border-[#3ECF8E] transition-all group"
          >
            <h3 className="font-medium mb-1 group-hover:text-[#3ECF8E] transition-colors">
              Monitor Batches
            </h3>
            <p className="text-sm text-muted-foreground">
              Track active and completed message batches
            </p>
          </a>
          
          <a
            href="/templates"
            data-testid="manage-templates-btn"
            className="p-4 bg-[#121212] border border-[#2E2E2E] rounded-md hover:border-[#3ECF8E] transition-all group"
          >
            <h3 className="font-medium mb-1 group-hover:text-[#3ECF8E] transition-colors">
              Manage Templates
            </h3>
            <p className="text-sm text-muted-foreground">
              Create and manage message templates
            </p>
          </a>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
