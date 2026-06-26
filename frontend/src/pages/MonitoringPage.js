import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Activity, ArrowLeft, RefreshCw, AlertTriangle, CheckCircle, Clock, Search, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { monitoringAPI } from '../lib/api';

const MonitoringPage = () => {
  const { id: shopId } = useParams();
  const [campaigns, setCampaigns] = useState([]);
  const [periodSummary, setPeriodSummary] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Drill-down states
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [campaignDetail, setCampaignDetail] = useState(null);
  
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [batchDetail, setBatchDetail] = useState(null);

  const [failedPanelOpen, setFailedPanelOpen] = useState(false);
  const [failedDetails, setFailedDetails] = useState(null);

  const fetchData = async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);

      const [campaignsRes] = await Promise.all([
        monitoringAPI.getCampaignOverview(shopId)
      ]);
      setCampaigns(campaignsRes.data.campaigns || []);
      
      if (selectedPeriod) {
        const periodRes = await monitoringAPI.getPeriodSummary(shopId, selectedPeriod);
        setPeriodSummary(periodRes.data);
      }

      // If viewing a campaign, refresh it
      if (selectedCampaign) {
        loadCampaignDetail(selectedCampaign.id);
      }
      
      // If viewing a batch, refresh it
      if (selectedBatch) {
        loadBatchDetail(selectedBatch.id);
      }

      // If viewing failed panel, refresh it
      if (failedPanelOpen && selectedCampaign) {
        loadFailedDetails(selectedCampaign.id);
      }

    } catch (err) {
      if (!isRefresh) toast.error('Failed to load monitoring data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh every 30s
    const interval = setInterval(() => {
      fetchData(true);
    }, 30000);
    return () => clearInterval(interval);
  }, [shopId, selectedPeriod, selectedCampaign, selectedBatch, failedPanelOpen]);

  const loadCampaignDetail = async (campaignId) => {
    try {
      const res = await monitoringAPI.getCampaignDetail(shopId, campaignId);
      setCampaignDetail(res.data);
    } catch (e) {
      toast.error("Failed to load campaign details");
    }
  };

  const loadBatchDetail = async (batchId) => {
    try {
      const res = await monitoringAPI.getBatchDetail(shopId, batchId);
      setBatchDetail(res.data);
    } catch (e) {
      toast.error("Failed to load batch details");
    }
  };

  const loadFailedDetails = async (campaignId) => {
    try {
      const res = await monitoringAPI.getFailedMessages(shopId, campaignId);
      setFailedDetails(res.data);
    } catch (e) {
      toast.error("Failed to load failed messages");
    }
  };

  const handleReschedule = async (mode) => {
    if (!selectedCampaign) return;
    try {
      const res = await monitoringAPI.rescheduleFailed(shopId, selectedCampaign.id, mode);
      toast.success(`Rescheduled ${res.data.rescheduled} messages. Skipped ${res.data.skipped} invalid numbers.`);
      fetchData(true);
    } catch (e) {
      toast.error("Failed to reschedule messages");
    }
  };

  const renderProgressBar = (sent, failed, pending, total) => {
    const totalDiv = total || 1;
    const sentPct = (sent / totalDiv) * 100;
    const failedPct = (failed / totalDiv) * 100;
    const pendingPct = (pending / totalDiv) * 100;

    return (
      <div className="w-full h-2 flex rounded-full overflow-hidden bg-[#2E2E2E]">
        <div style={{ width: `${sentPct}%` }} className="bg-[#3ECF8E]" />
        <div style={{ width: `${failedPct}%` }} className="bg-[#EF4444]" />
        <div style={{ width: `${pendingPct}%` }} className="bg-[#EAB308]" />
      </div>
    );
  };

  if (loading && !campaigns.length) return <div className="p-8 text-muted-foreground">Loading monitoring data...</div>;

  return (
    <div className="p-8 h-screen flex flex-col overflow-hidden">
      <div className="flex items-center justify-between mb-8 shrink-0">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link to={`/shop/${shopId}`} className="p-2 hover:bg-[#1C1C1C] rounded-lg transition-colors text-muted-foreground hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-4xl font-bold flex items-center gap-3" style={{ fontFamily: 'Chivo, sans-serif' }}>
              <Activity className="w-8 h-8 text-[#3ECF8E]" />
              System Monitoring
            </h1>
          </div>
          <p className="text-muted-foreground ml-14">Live campaign tracking, dead-letter queues, and performance metrics.</p>
        </div>
        
        <div className="flex items-center gap-4">
          <input 
            type="month" 
            value={selectedPeriod}
            onChange={(e) => setSelectedPeriod(e.target.value)}
            className="px-4 py-2 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg focus:outline-none focus:border-[#3ECF8E] text-white"
          />
          <button 
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className={`p-3 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg text-white hover:bg-[#2A2A2A] transition-colors ${refreshing ? 'animate-spin opacity-50' : ''}`}
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* LEFT PANEL: Campaigns List */}
        <div className="w-1/3 bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl flex flex-col overflow-hidden">
          <div className="p-4 border-b border-[#2E2E2E] bg-[#121212]">
            <h2 className="text-lg font-bold">Campaigns</h2>
          </div>
          <div className="p-4 overflow-y-auto space-y-3 flex-1 scrollbar-thin">
            {campaigns.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">No campaigns found.</p>
            ) : (
              campaigns.map(c => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedCampaign(c);
                    setSelectedBatch(null);
                    setFailedPanelOpen(false);
                    loadCampaignDetail(c.id);
                  }}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    selectedCampaign?.id === c.id 
                      ? 'bg-[#3ECF8E]/10 border-[#3ECF8E]' 
                      : 'bg-[#121212] border-[#2E2E2E] hover:border-gray-500'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-bold text-white truncate pr-2">{c.campaign_name}</h3>
                    <span className={`text-xs px-2 py-1 rounded border uppercase tracking-wider ${
                      c.status === 'completed' ? 'bg-[#3ECF8E]/20 text-[#3ECF8E] border-[#3ECF8E]/30' :
                      c.status === 'sending' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                      'bg-[#2E2E2E] text-gray-400 border-gray-600'
                    }`}>
                      {c.status}
                    </span>
                  </div>
                  
                  <div className="flex justify-between text-xs text-muted-foreground mb-2">
                    <span>{c.created_at ? new Date(c.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}</span>
                    <span>{c.messages_sent || 0} / {c.total_customers || 0} sent</span>
                  </div>
                  
                  {renderProgressBar(
                    c.messages_sent || 0,
                    c.messages_failed || 0,
                    (c.total_customers || 0) - (c.messages_sent || 0) - (c.messages_failed || 0),
                    c.total_customers || 1
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        {/* MIDDLE/RIGHT PANEL: Drill Down */}
        <div className="flex-1 bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl flex flex-col overflow-hidden">
          {!selectedCampaign ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground flex-col">
              <Activity className="w-16 h-16 mb-4 opacity-20" />
              <p>Select a campaign to view live telemetry</p>
            </div>
          ) : (
            <>
              {/* Campaign Header Details */}
              <div className="p-6 border-b border-[#2E2E2E] bg-[#121212]">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-2xl font-bold text-white mb-1">{selectedCampaign.campaign_name}</h2>
                    <p className="text-xs text-muted-foreground">
                      Started: {selectedCampaign.created_at ? new Date(selectedCampaign.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}
                      {(selectedCampaign.completed_at) ? (
                        <> · Ended: {new Date(selectedCampaign.completed_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</>
                      ) : (['completed', 'stopped', 'cancelled'].includes(selectedCampaign.status) && selectedCampaign.updated_at) ? (
                        <> · Ended: {new Date(selectedCampaign.updated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</>
                      ) : null}
                    </p>
                  </div>
                  <div className="flex gap-3">
                    <button 
                      onClick={() => {
                        setFailedPanelOpen(!failedPanelOpen);
                        if (!failedPanelOpen) loadFailedDetails(selectedCampaign.id);
                      }}
                      className={`px-4 py-2 rounded-lg font-semibold flex items-center gap-2 transition-colors ${
                        failedPanelOpen ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-[#2E2E2E] text-white hover:bg-[#3A3A3A]'
                      }`}
                    >
                      <AlertTriangle className="w-4 h-4" />
                      DLQ & Failed
                    </button>
                  </div>
                </div>

                {campaignDetail?.stats && (
                  <div className="grid grid-cols-4 gap-4">
                    <div className="bg-[#1C1C1C] p-3 rounded-lg border border-[#2E2E2E]">
                      <p className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Total Targets</p>
                      <p className="text-xl font-bold text-white">{campaignDetail.stats.total}</p>
                    </div>
                    <div className="bg-[#3ECF8E]/10 p-3 rounded-lg border border-[#3ECF8E]/30">
                      <p className="text-xs text-[#3ECF8E] mb-1 uppercase tracking-wider">Delivered</p>
                      <p className="text-xl font-bold text-[#3ECF8E]">{campaignDetail.stats.sent}</p>
                    </div>
                    <div className="bg-red-500/10 p-3 rounded-lg border border-red-500/30">
                      <p className="text-xs text-red-400 mb-1 uppercase tracking-wider">Failed</p>
                      <p className="text-xl font-bold text-red-400">{campaignDetail.stats.failed}</p>
                    </div>
                    <div className="bg-yellow-500/10 p-3 rounded-lg border border-yellow-500/30">
                      <p className="text-xs text-yellow-400 mb-1 uppercase tracking-wider">Pending</p>
                      <p className="text-xl font-bold text-yellow-400">{campaignDetail.stats.pending}</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
                {failedPanelOpen ? (
                  /* Failed Panel View */
                  <div>
                    <div className="flex justify-between items-center mb-6">
                      <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        <AlertTriangle className="text-red-400 w-5 h-5" />
                        Dead Letter Queue (Failed Messages)
                      </h3>
                      <button onClick={() => handleReschedule('failed')} className="px-4 py-2 bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/30 transition-colors">
                        Reschedule All Failed
                      </button>
                    </div>

                    {failedDetails?.reasons_breakdown && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                        {Object.entries(failedDetails.reasons_breakdown).map(([reason, count]) => (
                          <div key={reason} className="bg-[#121212] border border-[#2E2E2E] p-4 rounded-lg">
                            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{reason.replace('_', ' ')}</p>
                            <p className="text-2xl font-bold text-white">{count}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="bg-[#121212] rounded-lg border border-[#2E2E2E] overflow-hidden">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-[#1C1C1C] border-b border-[#2E2E2E] text-muted-foreground">
                          <tr>
                            <th className="p-3 font-medium">Customer</th>
                            <th className="p-3 font-medium">Phone</th>
                            <th className="p-3 font-medium">Reason</th>
                            <th className="p-3 font-medium">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2E2E2E]">
                          {failedDetails?.messages?.map(msg => (
                            <tr key={msg.id} className="hover:bg-[#1C1C1C]/50">
                              <td className="p-3 text-white">{msg.customer_name}</td>
                              <td className="p-3 text-muted-foreground">{msg.phone_number}</td>
                              <td className="p-3 text-red-400">{msg.failure_reason || 'Unknown Error'}</td>
                              <td className="p-3 text-muted-foreground">{msg.status}</td>
                            </tr>
                          ))}
                          {failedDetails?.messages?.length === 0 && (
                            <tr>
                              <td colSpan={4} className="p-8 text-center text-muted-foreground">No failed messages in this campaign! 🎉</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : selectedBatch ? (
                  /* Batch Detail View */
                  <div>
                    <button onClick={() => setSelectedBatch(null)} className="mb-4 flex items-center gap-2 text-muted-foreground hover:text-white transition-colors">
                      <ArrowLeft className="w-4 h-4" /> Back to Batches
                    </button>
                    <h3 className="text-xl font-bold text-white mb-6">Batch {selectedBatch.batch_number} Messages</h3>
                    
                    <div className="bg-[#121212] rounded-lg border border-[#2E2E2E] overflow-hidden">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-[#1C1C1C] border-b border-[#2E2E2E] text-muted-foreground">
                          <tr>
                            <th className="p-3 font-medium">Customer</th>
                            <th className="p-3 font-medium">Segment</th>
                            <th className="p-3 font-medium">Status</th>
                            <th className="p-3 font-medium">Updated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2E2E2E]">
                          {batchDetail?.messages?.map(msg => (
                            <tr key={msg.id} className="hover:bg-[#1C1C1C]/50">
                              <td className="p-3 text-white">
                                {msg.customer_name}
                                <br/><span className="text-xs text-muted-foreground">{msg.phone_number}</span>
                              </td>
                              <td className="p-3 text-muted-foreground">
                                <span className="px-2 py-1 bg-[#2E2E2E] rounded text-xs">{msg.customer_segment}</span>
                              </td>
                              <td className="p-3">
                                {msg.status === 'sent' || msg.status === 'delivered' ? (
                                  <span className="flex items-center gap-1 text-[#3ECF8E]"><CheckCircle className="w-4 h-4" /> Delivered</span>
                                ) : msg.status.includes('fail') ? (
                                  <span className="flex items-center gap-1 text-red-400"><AlertTriangle className="w-4 h-4" /> Failed</span>
                                ) : (
                                  <span className="flex items-center gap-1 text-yellow-400"><Clock className="w-4 h-4" /> {msg.status}</span>
                                )}
                              </td>
                              <td className="p-3 text-muted-foreground">{new Date(msg.updated_at).toLocaleTimeString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  /* Batch List View */
                  <div>
                    <h3 className="text-xl font-bold text-white mb-6">Batches ({campaignDetail?.batches?.length || 0})</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {campaignDetail?.batches?.map(batch => (
                        <button 
                          key={batch.id}
                          onClick={() => {
                            setSelectedBatch(batch);
                            loadBatchDetail(batch.id);
                          }}
                          className="bg-[#121212] border border-[#2E2E2E] p-4 rounded-xl text-left hover:border-gray-500 transition-colors flex flex-col h-full"
                        >
                          <div className="flex justify-between items-center mb-3">
                            <span className="font-bold text-white">Batch #{batch.batch_number}</span>
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                          </div>
                          <div className="mt-auto">
                            <div className="flex justify-between text-xs text-muted-foreground mb-1">
                              <span>{batch.status}</span>
                              <span>{batch.customer_count} targets</span>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default MonitoringPage;
