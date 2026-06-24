import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity, CheckCircle, XCircle, Square, RefreshCw, Clock, Users, Zap, Crown,
  AlertTriangle, Package, User, TrendingUp, RotateCcw, Store, Pause, Play,
  Ban, ChevronDown, ChevronUp, Shield, MessageCircle, Eye, EyeOff, ShoppingBag, Star
} from 'lucide-react';
import { batchesAPI, shopsAPI } from '../lib/api';
import { toast } from 'sonner';

/* ── Segment config ── */
const SEG = {
  vip:            { label: 'VIP Champions',    color: '#F59E0B', Icon: Crown },
  at_risk:        { label: 'At-Risk',           color: '#EF4444', Icon: AlertTriangle },
  potential_bulk: { label: 'Potential (Bulk)',  color: '#8B5CF6', Icon: ShoppingBag },
  loyal_frequent: { label: 'Loyal (Frequent)',  color: '#3B82F6', Icon: Star },
  boring:         { label: 'Occasional',        color: '#6B7280', Icon: User },
  new_customer:   { label: 'New Customer',      color: '#10B981', Icon: User },
};

const STATUS_COLORS = {
  pending:     { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', dot: '#F59E0B' },
  sending:     { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/30',   dot: '#3B82F6' },
  in_progress: { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/30',   dot: '#3B82F6' },
  completed:   { bg: 'bg-green-500/10',  text: 'text-green-400',  border: 'border-green-500/30',  dot: '#3ECF8E' },
  failed:      { bg: 'bg-red-500/10',    text: 'text-red-400',    border: 'border-red-500/30',    dot: '#EF4444' },
  paused:      { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', dot: '#FB923C' },
  stopped:     { bg: 'bg-red-900/20',    text: 'text-red-300',    border: 'border-red-500/20',    dot: '#F87171' },
  cancelled:   { bg: 'bg-gray-500/10',   text: 'text-gray-400',   border: 'border-gray-500/30',   dot: '#6B7280' },
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

/* ── Stat Counter Card ── */
const StatCard = ({ label, value, icon: Icon, color, pulse }) => (
  <div className={`bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-4 transition-all ${pulse ? 'ring-1 ring-inset' : ''}`}
       style={pulse ? { '--tw-ring-color': color + '30' } : {}}>
    <div className="flex items-center gap-2 mb-1">
      <Icon className={`w-4 h-4 ${pulse ? 'animate-pulse' : ''}`} style={{ color }} />
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
    <p className="text-2xl font-bold font-mono">{value}</p>
  </div>
);


/* ══════════════════════════════════════════════════════════════════════
   DLQ (Dead Letter Queue) — Failure Resolution Desk
   ══════════════════════════════════════════════════════════════════════ */
const DLQDesk = ({ campaignId, onRefresh }) => {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const loadDLQ = useCallback(async () => {
    try {
      const res = await batchesAPI.getDLQ(campaignId);
      setItems(res.data.dlq_items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [campaignId]);

  useEffect(() => { loadDLQ(); }, [loadDLQ]);

  const handleRequeue = async (itemId) => {
    try {
      await batchesAPI.requeueItem(itemId);
      toast.success('Item re-queued');
      loadDLQ();
      onRefresh?.();
    } catch { toast.error('Requeue failed'); }
  };

  const handleResolve = async (itemId) => {
    try {
      await batchesAPI.resolveItem(itemId);
      toast.success('Marked as resolved');
      loadDLQ();
      onRefresh?.();
    } catch { toast.error('Resolve failed'); }
  };

  const toggleExpand = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  if (loading) return <div className="text-center py-8 text-muted-foreground animate-pulse">Loading DLQ…</div>;
  if (items.length === 0) return null;

  return (
    <div className="bg-[#1C1C1C] border border-red-500/20 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[#2E2E2E] bg-red-500/5">
        <Shield className="w-4 h-4 text-red-400" />
        <span className="font-semibold text-sm text-red-400">Failure Resolution Desk</span>
        <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full border border-red-500/30 ml-auto">
          {items.length} failed
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted-foreground text-xs border-b border-[#2E2E2E] bg-[#121212]">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">Customer</th>
              <th className="px-4 py-2.5 text-left font-medium">Phone</th>
              <th className="px-4 py-2.5 text-left font-medium">Segment</th>
              <th className="px-4 py-2.5 text-left font-medium">Attempts</th>
              <th className="px-4 py-2.5 text-left font-medium">Last Error</th>
              <th className="px-4 py-2.5 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2E2E2E]">
            {items.map(item => {
              const seg = SEG[item.customer_segment] || SEG.boring;
              const SegIcon = seg.Icon;
              const errorLog = item.error_log || [];
              const lastError = errorLog.length > 0 ? errorLog[errorLog.length - 1] : null;
              const isExpanded = expanded[item.id];

              return (
                <React.Fragment key={item.id}>
                  <tr className="hover:bg-[#252525] transition-colors">
                    <td className="px-4 py-3 text-white font-medium text-xs">
                      {item.customer_name || 'Unknown'}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {item.phone_number}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <SegIcon className="w-3 h-3" style={{ color: seg.color }} />
                        <span className="text-xs text-muted-foreground">{seg.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-red-400">
                      {item.retry_count || 0}/3
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground max-w-[200px] truncate">
                      <button onClick={() => toggleExpand(item.id)} className="flex items-center gap-1 hover:text-white transition-colors">
                        {isExpanded ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        {lastError ? lastError.error?.substring(0, 40) + '…' : 'No error logged'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button onClick={() => handleRequeue(item.id)} title="Re-Queue"
                          className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors">
                          <RotateCcw className="w-3 h-3" />
                        </button>
                        <button title="Manual SMS (coming soon)" disabled
                          className="p-1.5 rounded-lg bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 opacity-40 cursor-not-allowed">
                          <MessageCircle className="w-3 h-3" />
                        </button>
                        <button onClick={() => handleResolve(item.id)} title="Mark Resolved"
                          className="p-1.5 rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors">
                          <CheckCircle className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {/* Expandable error log */}
                  {isExpanded && errorLog.length > 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-3 bg-[#181818]">
                        <div className="space-y-1">
                          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">Error History</p>
                          {errorLog.map((e, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs">
                              <span className="text-red-500 font-mono flex-shrink-0">#{e.attempt}</span>
                              <span className="text-muted-foreground">{e.error}</span>
                              <span className="text-muted-foreground/50 ml-auto flex-shrink-0">
                                {new Date(e.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};


/* ══════════════════════════════════════════════════════════════════════
   Campaign Card — Real-Time Progress + Controls
   ══════════════════════════════════════════════════════════════════════ */
const CampaignCard = ({ campaign, onRefresh }) => {
  const [stats, setStats]     = useState(null);
  const [actionLoading, setActionLoading] = useState('');
  const [showDLQ, setShowDLQ] = useState(false);
  const intervalRef = useRef(null);

  const campaignId = campaign._id;
  const isActive = ['pending', 'sending', 'in_progress'].includes(campaign.status);
  const isPaused = campaign.status === 'paused';
  const isDone   = ['completed', 'failed', 'stopped', 'cancelled'].includes(campaign.status);

  // Poll live stats every 3s for active/paused campaigns
  const pollStats = useCallback(async () => {
    try {
      const res = await batchesAPI.getLiveStats(campaignId);
      setStats(res.data);
    } catch { /* ignore */ }
  }, [campaignId]);

  useEffect(() => {
    pollStats();
    if (isActive || isPaused) {
      intervalRef.current = setInterval(pollStats, 3000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [pollStats, isActive, isPaused]);

  const s = stats || {};
  const total     = s.total_targeted || campaign.total_customers || 1;
  const delivered = s.delivered ?? campaign.live_sent ?? campaign.messages_sent ?? 0;
  const pending   = s.pending ?? campaign.live_pending ?? 0;
  const retryWait = s.retry_wait ?? 0;
  const failedFinal = s.failed_final ?? campaign.live_failed ?? campaign.messages_failed ?? 0;
  const pct = s.progress_pct ?? Math.round((delivered / total) * 100);

  const status = s.status || campaign.status || 'pending';
  const sc = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const segStats = s.segment_stats || campaign.segment_stats || {};

  // ── Actions ──
  const doAction = async (action, fn) => {
    setActionLoading(action);
    try {
      await fn();
      toast.success(`Campaign ${action}`);
      onRefresh();
      pollStats();
    } catch { toast.error(`Failed to ${action}`); }
    finally { setActionLoading(''); }
  };

  const handlePause  = () => doAction('paused',    () => batchesAPI.pauseCampaign(campaignId));
  const handleResume = () => doAction('resumed',   () => batchesAPI.resumeCampaign(campaignId));
  const handleCancel = () => {
    if (!window.confirm('Cancel this campaign? Remaining pending items will be purged.')) return;
    doAction('cancelled', () => batchesAPI.cancelCampaign(campaignId));
  };
  const handleStop = () => {
    if (!window.confirm('Emergency stop? Current batch finishes; all future batches cancelled.')) return;
    doAction('stopped', () => batchesAPI.stopCampaign(campaignId));
  };

  const handleResend = async (mode) => {
    setActionLoading('resend');
    try {
      const res = await shopsAPI.resendCampaign(campaign.shop_id, campaignId, mode);
      toast.success(res.data.message || `Re-queued ${res.data.requeued} messages`);
      onRefresh();
    } catch { toast.error('Resend failed'); }
    finally { setActionLoading(''); }
  };

  return (
    <div className={`bg-[#1C1C1C] border rounded-xl transition-all ${
      isActive ? 'border-[#3ECF8E]/30 shadow-[0_0_20px_rgba(62,207,142,0.05)]' :
      isPaused ? 'border-orange-500/30' : 'border-[#2E2E2E]'
    }`}>

      {/* ── Header ── */}
      <div className="flex items-start justify-between p-5 pb-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {(isActive || isPaused) && <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: sc.dot }} />}
            <h3 className="font-bold text-white truncate">{campaign.campaign_name || 'Unnamed Campaign'}</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            {new Date(campaign.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        </div>
        <div className="flex items-center gap-2 ml-3 flex-shrink-0">
          <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${sc.bg} ${sc.text} ${sc.border}`}>
            {status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* ── Control Buttons ── */}
      <div className="flex items-center gap-2 px-5 py-3 flex-wrap">
        {isActive && (
          <>
            <button onClick={handlePause} disabled={!!actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-orange-400 border border-orange-500/30 bg-orange-500/10 hover:bg-orange-500/20 rounded-lg transition-colors disabled:opacity-50">
              <Pause className="w-3 h-3" />{actionLoading === 'paused' ? '…' : 'Pause'}
            </button>
            <button onClick={handleStop} disabled={!!actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-red-400 border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 rounded-lg transition-colors disabled:opacity-50">
              <Square className="w-3 h-3" />{actionLoading === 'stopped' ? '…' : 'Stop'}
            </button>
            <button onClick={handleCancel} disabled={!!actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-gray-400 border border-gray-500/30 bg-gray-500/10 hover:bg-gray-500/20 rounded-lg transition-colors disabled:opacity-50">
              <Ban className="w-3 h-3" />{actionLoading === 'cancelled' ? '…' : 'Cancel'}
            </button>
          </>
        )}
        {isPaused && (
          <>
            <button onClick={handleResume} disabled={!!actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-[#3ECF8E] border border-[#3ECF8E]/30 bg-[#3ECF8E]/10 hover:bg-[#3ECF8E]/20 rounded-lg transition-colors disabled:opacity-50">
              <Play className="w-3 h-3" />{actionLoading === 'resumed' ? '…' : 'Resume'}
            </button>
            <button onClick={handleCancel} disabled={!!actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-gray-400 border border-gray-500/30 bg-gray-500/10 hover:bg-gray-500/20 rounded-lg transition-colors disabled:opacity-50">
              <Ban className="w-3 h-3" />Cancel
            </button>
          </>
        )}
      </div>

      {/* ── Real-Time Counters ── */}
      <div className="grid grid-cols-4 gap-2 px-5 pb-3">
        <div className="bg-[#121212] rounded-lg p-2.5 text-center">
          <p className="text-[10px] text-muted-foreground mb-0.5">Targeted</p>
          <p className="text-lg font-bold font-mono text-white">{total}</p>
        </div>
        <div className="bg-[#121212] rounded-lg p-2.5 text-center">
          <p className="text-[10px] text-[#3ECF8E] mb-0.5">Delivered ✓</p>
          <p className="text-lg font-bold font-mono text-[#3ECF8E]">{delivered}</p>
        </div>
        <div className="bg-[#121212] rounded-lg p-2.5 text-center">
          <p className="text-[10px] text-yellow-400 mb-0.5">Retry ⏳</p>
          <p className="text-lg font-bold font-mono text-yellow-400">{retryWait}</p>
        </div>
        <div className="bg-[#121212] rounded-lg p-2.5 text-center">
          <p className="text-[10px] text-red-400 mb-0.5">Failed ❌</p>
          <p className="text-lg font-bold font-mono text-red-400">{failedFinal}</p>
        </div>
      </div>

      {/* ── Overall Progress ── */}
      <div className="px-5 pb-4">
        <div className="flex justify-between text-sm mb-1.5">
          <span className="text-muted-foreground">Delivery Progress</span>
          <span className="font-mono font-semibold">{delivered}/{total} <span className="text-muted-foreground text-xs">({pct}%)</span></span>
        </div>
        <Bar value={pct} color={isActive ? '#3B82F6' : isPaused ? '#FB923C' : '#3ECF8E'} animated={isActive} />
        <div className="flex gap-4 mt-2 text-xs text-muted-foreground flex-wrap">
          <span className="flex items-center gap-1"><Clock className="w-3 h-3 text-yellow-400" />{pending} pending</span>
          <span className="ml-auto"><strong>{s.completed_batches ?? campaign.completed_batches ?? 0}</strong>/{s.total_batches ?? campaign.total_batches ?? '?'} batches</span>
        </div>
      </div>

      {/* ── Per-Segment Breakdown ── */}
      {Object.keys(segStats).length > 0 && (
        <div className="border-t border-[#2E2E2E] px-5 py-3 space-y-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">Segment Breakdown</p>
          {Object.entries(segStats).map(([seg, st]) => {
            const cfg = SEG[seg] || { label: seg, color: '#6B7280', Icon: Users };
            const { Icon } = cfg;
            return (
              <div key={seg} className="flex items-center gap-2 text-xs">
                <Icon className="w-3 h-3 flex-shrink-0" style={{ color: cfg.color }} />
                <span className="w-28 truncate text-muted-foreground">{cfg.label}</span>
                <div className="flex-1"><Bar value={st.pct} color={cfg.color} animated={isActive} /></div>
                <span className="w-20 text-right font-mono text-muted-foreground">{st.sent}/{st.total}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* ── DLQ Toggle + Resend ── */}
      {(failedFinal > 0 || (isDone && (campaign.live_failed > 0 || campaign.messages_failed > 0))) && (
        <div className="border-t border-[#2E2E2E] px-5 py-3">
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setShowDLQ(!showDLQ)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/20 transition-colors">
              {showDLQ ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {showDLQ ? 'Hide' : 'Show'} DLQ ({failedFinal})
            </button>
            {isDone && (
              <>
                {(campaign.live_failed > 0 || failedFinal > 0) && (
                  <button onClick={() => handleResend('failed')} disabled={!!actionLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/20 transition-colors disabled:opacity-50">
                    <RotateCcw className="w-3 h-3" />Resend Failed
                  </button>
                )}
                {campaign.status === 'stopped' && (
                  <button onClick={() => handleResend('unsent')} disabled={!!actionLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/30 rounded-lg hover:bg-yellow-500/20 transition-colors disabled:opacity-50">
                    <RotateCcw className="w-3 h-3" />Resend Unsent
                  </button>
                )}
                <button onClick={() => handleResend('all')} disabled={!!actionLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[#3ECF8E]/10 text-[#3ECF8E] border border-[#3ECF8E]/30 rounded-lg hover:bg-[#3ECF8E]/20 transition-colors disabled:opacity-50">
                  <RotateCcw className="w-3 h-3" />Resend All
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── DLQ Table (expandable) ── */}
      {showDLQ && (
        <div className="border-t border-[#2E2E2E]">
          <DLQDesk campaignId={campaignId} onRefresh={() => { onRefresh(); pollStats(); }} />
        </div>
      )}
    </div>
  );
};


/* ══════════════════════════════════════════════════════════════════════
   Main Monitor Page
   ══════════════════════════════════════════════════════════════════════ */
const BatchMonitorPage = () => {
  const [shops,        setShops]        = useState([]);
  const [selectedShop, setSelectedShop] = useState('');
  const [campaigns,    setCampaigns]    = useState([]);
  const [batches,      setBatches]      = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [filter,       setFilter]       = useState('all');
  const [lastRefresh,  setLastRefresh]  = useState(null);
  const [spinning,     setSpinning]     = useState(false);

  // Load shops once
  useEffect(() => {
    const loadShops = async () => {
      try {
        const res = await shopsAPI.list();
        const list = res.data.shops || [];
        setShops(list);
        if (list.length > 0 && !selectedShop) setSelectedShop(list[0].id);
      } catch { /* ignore */ }
    };
    loadShops();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    try {
      const [cRes, bRes] = await Promise.all([
        batchesAPI.campaignsList(),
        batchesAPI.list(),
      ]);
      setCampaigns(cRes.data.campaigns || []);
      setBatches(bRes.data.batches || []);
      setLastRefresh(new Date());
    } catch (err) { console.error('Monitor load error:', err); }
    finally { setLoading(false); }
  }, []);

  // Poll every 8s
  useEffect(() => {
    load();
    const iv = setInterval(load, 8000);
    return () => clearInterval(iv);
  }, [load]);

  const handleRefresh = async () => {
    setSpinning(true);
    await load();
    setTimeout(() => setSpinning(false), 600);
    toast.success('Refreshed');
  };

  // Filter by shop + status tab
  const shopCampaigns = selectedShop
    ? campaigns.filter(c => c.shop_id === selectedShop)
    : campaigns;

  const shopBatches = selectedShop
    ? batches.filter(b => b.shop_id === selectedShop)
    : batches;

  const filtered = shopCampaigns.filter(c => {
    if (filter === 'active')    return ['pending','sending','in_progress','paused'].includes(c.status);
    if (filter === 'completed') return ['completed','failed','stopped','cancelled'].includes(c.status);
    return true;
  });

  const activeBatches = shopBatches.filter(b => ['pending','scheduled','sending'].includes(b.status));
  const totalSent   = shopCampaigns.reduce((a, c) => a + (c.live_sent   ?? c.messages_sent   ?? 0), 0);
  const totalFailed = shopCampaigns.reduce((a, c) => a + (c.live_failed ?? c.messages_failed ?? 0), 0);
  const totalPaused = shopCampaigns.filter(c => c.status === 'paused').length;

  return (
    <div className="p-8 space-y-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold mb-1" style={{ fontFamily: 'Chivo, sans-serif' }}>Monitor &amp; History</h1>
          <p className="text-muted-foreground text-sm">
            Real-time delivery logs · scheduler engine · auto-refresh 8s
            {lastRefresh && <span className="ml-2 text-[#3ECF8E]/60">· {lastRefresh.toLocaleTimeString()}</span>}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Shop Selector */}
          <div className="flex items-center gap-2 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg px-3 py-2">
            <Store className="w-4 h-4 text-muted-foreground" />
            <select value={selectedShop} onChange={e => setSelectedShop(e.target.value)}
              className="bg-transparent text-white text-sm font-medium outline-none min-w-[120px]">
              <option value="">All Shops</option>
              {shops.map(s => <option key={s.id} value={s.id}>{s.shop_name}</option>)}
            </select>
          </div>

          {/* Refresh */}
          <button onClick={handleRefresh}
            className="flex items-center gap-2 px-4 py-2 border border-[#2E2E2E] rounded-lg text-sm hover:border-[#3ECF8E] transition-colors">
            <RefreshCw className={`w-4 h-4 transition-transform duration-500 ${spinning ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Campaigns" value={shopCampaigns.length} icon={TrendingUp} color="#3ECF8E" />
        <StatCard label="Active Now" value={shopCampaigns.filter(c => ['pending','sending','in_progress'].includes(c.status)).length} icon={Activity} color="#3B82F6" pulse={shopCampaigns.some(c => c.status === 'sending')} />
        <StatCard label="Paused" value={totalPaused} icon={Pause} color="#FB923C" />
        <StatCard label="Delivered" value={totalSent} icon={CheckCircle} color="#3ECF8E" />
        <StatCard label="Failed" value={totalFailed} icon={XCircle} color="#EF4444" />
      </div>

      {/* Live Batch Ticker */}
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
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2E2E2E]">
                {activeBatches.map(b => {
                  const t = b.customer_count || 1;
                  const s = b.success_count || 0;
                  const p = Math.round((s / t) * 100);
                  return (
                    <tr key={b.id} className="hover:bg-[#252525] transition-colors">
                      <td className="px-4 py-3 font-mono text-xs">#{b.batch_number}/{b.total_batches}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs truncate max-w-[150px]">{b.campaign_name || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Bar value={p} color="#3B82F6" animated />
                          <span className="text-xs font-mono w-8 text-right">{p}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs capitalize">{b.status === 'sending' ? '🚀 ' : '⏳ '}{b.status}</td>
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
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Campaigns <span className="text-muted-foreground font-normal text-base ml-2">({filtered.length})</span>
          </h2>
          <div className="flex gap-2">
            {[['all','All'],['active','Active'],['completed','Completed']].map(([v, l]) => (
              <button key={v} onClick={() => setFilter(v)}
                className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                  filter === v ? 'bg-[#3ECF8E]/10 border-[#3ECF8E]/50 text-[#3ECF8E]' : 'border-[#2E2E2E] text-muted-foreground hover:border-[#3E3E3E]'
                }`}>{l}</button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-muted-foreground animate-pulse">Loading campaigns…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl">
            <Activity className="w-12 h-12 text-[#2E2E2E] mx-auto mb-3" />
            <p className="text-muted-foreground">No {filter !== 'all' ? filter : ''} campaigns{selectedShop ? ' for this shop' : ''}.</p>
            <p className="text-xs text-muted-foreground mt-1">Launch a campaign from a shop dashboard to see it here.</p>
          </div>
        ) : (
          <div className="space-y-5">
            {filtered.map(c => <CampaignCard key={c._id} campaign={c} onRefresh={load} />)}
          </div>
        )}
      </div>
    </div>
  );
};

export default BatchMonitorPage;
