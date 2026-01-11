import React, { useState, useEffect } from 'react';
import { batchesAPI } from '../lib/api';
import { Clock, CheckCircle, XCircle, Loader, AlertTriangle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

const BatchMonitorPage = () => {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rescheduling, setRescheduling] = useState(null);

  useEffect(() => {
    loadBatches();
    const interval = setInterval(loadBatches, 3000); // Refresh every 3 seconds
    return () => clearInterval(interval);
  }, []);

  const loadBatches = async () => {
    try {
      const response = await batchesAPI.list();
      setBatches(response.data.batches);
    } catch (error) {
      toast.error('Failed to load batches');
    } finally {
      setLoading(false);
    }
  };

  const handleReschedule = async (batchId) => {
    setRescheduling(batchId);
    try {
      await batchesAPI.reschedule(batchId);
      toast.success('Batch rescheduled with priority');
      await loadBatches();
    } catch (error) {
      toast.error('Failed to reschedule batch');
    } finally {
      setRescheduling(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending':
        return <Clock className="w-4 h-4 text-yellow-500" />;
      case 'sending':
        return <Loader className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-[#3ECF8E]" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending':
        return 'text-yellow-500';
      case 'sending':
        return 'text-blue-500';
      case 'completed':
        return 'text-[#3ECF8E]';
      case 'failed':
        return 'text-red-500';
      default:
        return 'text-muted-foreground';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader className="w-8 h-8 animate-spin text-[#3ECF8E]" />
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Batch Monitoring
          </h1>
          <p className="text-muted-foreground">
            Track and manage your message batches in real-time
          </p>
        </div>
        <button
          data-testid="refresh-button"
          onClick={loadBatches}
          className="px-4 py-2 bg-[#2E2E2E] hover:bg-[#3E3E3E] rounded-md transition-colors flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Batches Table */}
      <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg overflow-hidden">
        {batches.length === 0 ? (
          <div className="p-12 text-center">
            <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No batches found. Create a campaign to get started.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" data-testid="batches-table">
              <thead className="bg-[#121212] border-b border-[#2E2E2E]">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Batch ID
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Scheduled Time
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Success
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Failed
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Priority
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <tr
                    key={batch.id}
                    data-testid={`batch-row-${batch.id}`}
                    className="hover:bg-[#232323] transition-colors border-b border-[#2E2E2E] last:border-0"
                  >
                    <td className="px-4 py-3">
                      <code className="text-xs font-mono">
                        {batch.id.substring(0, 8)}...
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono">
                        {new Date(batch.start_time).toLocaleString()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(batch.status)}
                        <span className={`text-sm font-medium capitalize ${getStatusColor(batch.status)}`}>
                          {batch.status}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono text-[#3ECF8E]">
                        {batch.success_count}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono text-red-500">
                        {batch.failed_count}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {batch.priority > 0 && (
                        <span className="inline-block px-2 py-0.5 bg-red-500/20 text-red-500 text-xs rounded">
                          Priority {batch.priority}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {batch.failed_count > 0 && batch.status === 'failed' && (
                        <button
                          data-testid={`reschedule-button-${batch.id}`}
                          onClick={() => handleReschedule(batch.id)}
                          disabled={rescheduling === batch.id}
                          className="px-3 py-1 bg-red-500/20 text-red-500 hover:bg-red-500/30 rounded text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1"
                        >
                          {rescheduling === batch.id ? (
                            <Loader className="w-3 h-3 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3 h-3" />
                          )}
                          Reschedule Priority 1
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Summary */}
      {batches.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Total Batches</p>
            <p className="text-2xl font-semibold font-mono">{batches.length}</p>
          </div>
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Pending</p>
            <p className="text-2xl font-semibold font-mono text-yellow-500">
              {batches.filter(b => b.status === 'pending').length}
            </p>
          </div>
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Completed</p>
            <p className="text-2xl font-semibold font-mono text-[#3ECF8E]">
              {batches.filter(b => b.status === 'completed').length}
            </p>
          </div>
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Failed</p>
            <p className="text-2xl font-semibold font-mono text-red-500">
              {batches.filter(b => b.status === 'failed').length}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default BatchMonitorPage;
