import React, { useState, useEffect, useCallback } from 'react';
import { Activity, CheckCircle, XCircle, Pause, Play, Square, RefreshCw, Filter, Clock, Users, Zap, Crown, AlertTriangle, Package, User, TrendingUp } from 'lucide-react';
import { batchesAPI } from '../lib/api';
import { toast } from 'sonner';

/* ── Segment config ── */
const SEG = {
  vip:            { label: 'VIP Champions',   color: '#F59E0B', Icon: Crown },
  at_risk:        { label: 'At-Risk',          color: '#EF4444', Icon: AlertTriangle },
  potential_bulk: { label: 'Potential (Bulk)', color: '#8B5CF6', Icon: Package },
  loyal_frequent: { label: 'Loyal (Frequent)', color: '#3B82F6', Icon: Zap },
  boring:         { label: 'Boring / New',     color: '#6B7280', Icon: User },
};

const STATUS_COLORS = {
  pending:    { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', dot: '#F59E0B' },
  sending:    { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/30',   dot: '#3B82F6' },
  in_progress:{ bg: 'bg-blue-500/10',  text: 'text-blue-400',   border: 'border-blue-500/30',   dot: '#3B82F6' },
  completed:  { bg: 'bg-green-500/10', text: 'text-green-400',  border: 'border-green-500/30',  dot: '#3ECF8E' },
  failed:     { bg: 'bg-red-500/10',   text: 'text-red-400',    border: 'border-red-500/30',    dot: '#EF4444' },
  paused:     { bg: 'bg-gray-500/10',  text: 'text-gray-400',   border: 'border-gray-500/30',   dot: '#6B7280' },
  stopped:    { bg: 'bg-red-900/20',   text: 'text-red-300',    border: 'border-red-500/20',    dot: '#F87171' },
};

/* ── Progress Bar ── */
const Bar = ({ value, color, animated }) => (
  <div className="w-full bg-[#2E2E2E] rounded-full h-2 overflow-hidden">
    <div
      className={`h-2 rounded-full transition-all duration-700 ${animated ? 'animate-pulse' : ''}`}
      style={{ width: `${Math.min(value, 100)}%`, backgroundColor: color }}
    />
  </div>
);

/* ── Campaign Card ── */
const CampaignCard = ({ campaign, onStop, onRefresh }) => {
  const [stopping, setStopping] = useState(false);
  const total = campaign.total_customers || 1;
  const sent  = campaign.live_sent ?? campaign.messages_sent ?? 0;
  const failed= campaign.live_failed ?? campaign.messages_failed ?? 0;
  const pct   = Math.round((sent / total) * 100);

  const status  = campaign.status || 'pending';
  const sc      = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const isActive= ['pending', 'sending', 'in_progress'].includes(status);
  const segStats= campaign.segment_stats || {};

  const handleStop = async () => {
    if (!window.confirm('Emergency stop? Current batch finishes; all future batches will be cancelled.')) return;
    setStopping(true);
    try {
      await batchesAPI.stopCampaign(campaign._id);
      toast.success('Campaign stopped');
      onRefresh();
    } catch { toast.error('Failed to stop campaign'); }
    finally { setStopping(false); }
  };

  return (
    <div className={`bg-[#1C1C1C] border rounded-xl p-5 transition-all ${isActive ? 'border-[#3ECF8E]/30 shadow-[0_0_20px_rgba(62,207,142,0.05)]' : 'border-[#2E2E2E]'}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {isActive && <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: sc.dot }} />}
            <h3 className="font-bold text-white truncate">{campaign.campaign_name || 'Unnamed Campaign'}</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date(campaign.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
            {campaign.shop_id && <span className="ml-2 text-[#3ECF8E]/60">· Shop</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 ml-3">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${sc.bg} ${sc.text} ${sc.border}`}>
            {status.replace('_', ' ')}
          </span>
          {isActive && (
            <button onClick={handleStop} disabled={stopping}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-red-400 border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 rounded-lg transition-colors disabled:opacity-50"
              title="Emergency Stop">
              <Square className="w-3 h-3" />{stopping ? '…' : 'Stop'}
            </button>
          )}
        </div>
      </div>

      {/* Overall progress */}
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-1.5">
          <span className="text-muted-foreground">Overall Progress</span>
          <span className="font-mono font-semibold">{sent} / {total} <span className="text-muted-foreground text-xs">({pct}%)</span></span>
        </div>
        <Bar value={pct} color={isActive ? '#3B82F6' : '#3ECF8E'} animated={isActive} />
        <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-[#3ECF8E]" />{sent} sent</span>
          <span className="flex items-center gap-1"><XCircle className="w-3 h-3 text-red-400" />{failed} failed</span>
          <span className="flex items-center gap-1"><Clock className="w-3 h-3 text-yellow-400" />{(campaign.live_pending ?? 0)} pending</span>
          <span className="ml-auto"><strong>{campaign.completed_batches ?? 0}</strong>/{campaign.total_batches ?? '?'} batches</span>
        </div>
      </div>

      {/* Per-segment breakdown */}
      {Object.keys(segStats).length > 0 && (
        <div className="border-t border-[#2E2E2E] pt-3 space-y-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Segment Breakdown</p>
          {Object.entries(segStats).map(([seg, stats]) => {
            const cfg = SEG[seg] || { label: seg, color: '#6B7280', Icon: Users };
            const { Icon } = cfg;
            return (
              <div key={seg} className="flex items-center gap-2 text-xs">
                <Icon className="w-3 h-3 flex-shrink-0" style={{ color: cfg.color }} />
                <span className="w-28 truncate text-muted-foreground">{cfg.label}</span>
                <div className="flex-1">
                  <Bar value={stats.pct} color={cfg.color} animated={isActive} />
                </div>
                <span className="w-20 text-right font-mono text-muted-foreground">
                  {stats.sent}/{stats.total} ({stats.pct}%)
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/* ── Main Monitor Page ── */
const BatchMonitorPage = () => {
  const [campaigns, setCampaigns] = useState([]);
  const [batches,   setBatches]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [filter,    setFilter]    = useState('all'); // all | active | completed
  const [lastRefresh, setLastRefresh] = useState(null);

  const load = useCallback(async () => {
    try {
      const [cRes, bRes] = await Promise.all([
        batchesAPI.campaignsList(),
        batchesAPI.list(),
      ]);
      setCampaigns(cRes.data.campaigns || []);
      setBatches(bRes.data.batches || []);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Monitor load error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll every 8 seconds while active campaigns exist
  useEffect(() => {
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [load]);

  const filtered = campaigns.filter(c => {
    if (filter === 'active')    return ['pending','sending','in_progress'].includes(c.status);
    if (filter === 'completed') return ['completed','failed','stopped'].includes(c.status);
    return true;
  });

  const activeBatches = batches.filter(b => ['pending','scheduled','sending'].includes(b.status));

  const totalSent  = campaigns.reduce((a, c) => a + (c.live_sent  ?? c.messages_sent  ?? 0), 0);
  const totalFailed= campaigns.reduce((a, c) => a + (c.live_failed?? c.messages_failed?? 0), 0);

  return (
    <div className="p-8 space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold mb-1" style={{ fontFamily: 'Chivo, sans-serif' }}>Monitor &amp; History</h1>
          <p className="text-muted-foreground text-sm">
            Real-time delivery logs · auto-refresh every 8s
            {lastRefresh && <span className="ml-2 text-[#3ECF8E]/60">· Last: {lastRefresh.toLocaleTimeString()}</span>}
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-2 border border-[#2E2E2E] rounded-lg text-sm hover:border-[#3ECF8E] transition-colors">
          <RefreshCw className="w-4 h-4" />Refresh
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Campaigns', value: campaigns.length,  icon: TrendingUp, color: '#3ECF8E' },
          { label: 'Active Now',      value: campaigns.filter(c => ['pending','sending','in_progress'].includes(c.status)).length, icon: Activity, color: '#3B82F6' },
          { label: 'Messages Sent',   value: totalSent,         icon: CheckCircle, color: '#3ECF8E' },
          { label: 'Failed',          value: totalFailed,        icon: XCircle,    color: '#EF4444' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              <Icon className="w-4 h-4" style={{ color }} />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <p className="text-2xl font-bold font-mono">{value}</p>
          </div>
        ))}
      </div>

      {/* Live Batch Ticker (raw batches currently sending) */}
      {activeBatches.length > 0 && (
        <div className="bg-[#1C1C1C] border border-[#3B82F6]/30 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[#2E2E2E] bg-[#3B82F6]/5">
            <Activity className="w-4 h-4 text-[#3B82F6]" />
            <span className="font-semibold text-sm">Live Batch Ticker</span>
            <span className="text-xs bg-[#3B82F6]/20 text-[#3B82F6] px-2 py-0.5 rounded-full border border-[#3B82F6]/30 ml-auto">
              {activeBatches.length} active
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-muted-foreground text-xs border-b border-[#2E2E2E] bg-[#121212]">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Batch</th>
                  <th className="px-4 py-2 text-left font-medium">Campaign</th>
                  <th className="px-4 py-2 text-left font-medium w-40">Progress</th>
                  <th className="px-4 py-2 text-left font-medium">Status</th>
                  <th className="px-4 py-2 text-left font-medium">Priority</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2E2E2E]">
                {activeBatches.map(b => {
                  const total = b.customer_count || b.batch_size || 1;
                  const sent  = b.success_count || 0;
                  const pct   = Math.round((sent / total) * 100);
                  const priorityLabels = {1:'VIP First',2:'High',3:'Normal',4:'Low'};
                  return (
                    <tr key={b.id} className="hover:bg-[#252525] transition-colors">
                      <td className="px-4 py-3 font-mono text-xs">#{b.batch_number}/{b.total_batches}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs truncate max-w-[150px]">{b.campaign_name || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Bar value={pct} color="#3B82F6" animated />
                          <span className="text-xs font-mono w-8 text-right">{pct}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1 text-xs">
                          {b.status === 'sending' ? '🚀' : '⏳'}
                          <span className="capitalize">{b.status}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{priorityLabels[b.priority] || b.priority}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Campaign Cards */}
      <div>
        {/* Filter tabs */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Campaigns <span className="text-muted-foreground font-normal text-base ml-2">({filtered.length})</span>
          </h2>
          <div className="flex gap-2">
            {[['all','All'],['active','Active'],['completed','Completed']].map(([val, label]) => (
              <button key={val} onClick={() => setFilter(val)}
                className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                  filter === val
                    ? 'bg-[#3ECF8E]/10 border-[#3ECF8E]/50 text-[#3ECF8E]'
                    : 'border-[#2E2E2E] text-muted-foreground hover:border-[#3E3E3E]'
                }`}>{label}</button>
            ))}
            <button onClick={() => { if(window.confirm('Clear ALL batch data?')) batchesAPI.clearAll().then(load); }}
              className="px-3 py-1.5 rounded-lg border border-red-500/20 text-xs text-red-400 hover:bg-red-500/10 transition-colors ml-2">
              Clear All
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-muted-foreground animate-pulse">Loading campaigns…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl">
            <Activity className="w-12 h-12 text-[#2E2E2E] mx-auto mb-3" />
            <p className="text-muted-foreground">No {filter !== 'all' ? filter : ''} campaigns yet.</p>
            <p className="text-xs text-muted-foreground mt-1">Launch a campaign from a shop dashboard to see it here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            {filtered.map(c => (
              <CampaignCard key={c._id} campaign={c} onStop={() => {}} onRefresh={load} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default BatchMonitorPage;
