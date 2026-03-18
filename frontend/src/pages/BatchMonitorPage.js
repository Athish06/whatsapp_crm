import React, { useState, useEffect } from 'react';
import { batchesAPI, templatesAPI } from '../lib/api';
import { Clock, CheckCircle, XCircle, Loader, AlertTriangle, RefreshCw, Trash2, PauseCircle, PlayCircle, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '../lib/utils';

const BatchMonitorPage = () => {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rescheduling, setRescheduling] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [editingBatchId, setEditingBatchId] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [editForm, setEditForm] = useState({
    start_time: '',
    template_mode: 'segment',
    template_id: '',
    segment_templates: {
      vip: '',
      at_risk: '',
      potential_bulk: '',
      loyal_frequent: '',
      boring: ''
    }
  });

  useEffect(() => {
    loadBatches();
    loadTemplates();
    const interval = setInterval(loadBatches, 3000); // Refresh every 3 seconds
    return () => clearInterval(interval);
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await templatesAPI.list();
      setTemplates(response.data.templates || []);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to load templates'));
    }
  };

  const loadBatches = async () => {
    try {
      const response = await batchesAPI.list();
      setBatches(response.data.batches);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to load batches'));
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
      toast.error(getErrorMessage(error, 'Failed to reschedule batch'));
    } finally {
      setRescheduling(null);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear ALL batches and messages? This action cannot be undone!')) {
      return;
    }
    
    try {
      const response = await batchesAPI.clearAll();
      toast.success(`Cleared ${response.data.batches_deleted} batches and ${response.data.messages_deleted} messages`);
      await loadBatches();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to clear batches'));
    }
  };

  const handlePause = async (batchId) => {
    setActionLoading(`pause-${batchId}`);
    try {
      await batchesAPI.pause(batchId);
      toast.success('Batch paused');
      await loadBatches();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to pause batch'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async (batchId) => {
    setActionLoading(`resume-${batchId}`);
    try {
      await batchesAPI.resume(batchId);
      toast.success('Batch resumed');
      await loadBatches();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to resume batch'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteBatch = async (batchId) => {
    if (!window.confirm('Delete this extra scheduled batch? This will remove its pending messages.')) return;
    setActionLoading(`delete-${batchId}`);
    try {
      const response = await batchesAPI.delete(batchId);
      toast.success(`Batch deleted. Removed ${response.data.messages_deleted || 0} messages`);
      if (editingBatchId === batchId) setEditingBatchId(null);
      await loadBatches();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to delete batch'));
    } finally {
      setActionLoading(null);
    }
  };

  const openEditPanel = (batch) => {
    const defaultSegmentTemplates = {
      vip: '', at_risk: '', potential_bulk: '', loyal_frequent: '', boring: ''
    };

    setEditingBatchId(batch.id);
    setEditForm({
      start_time: batch.start_time ? new Date(batch.start_time).toISOString().slice(0, 16) : '',
      template_mode: batch.mode === 'single-template' ? 'single' : 'segment',
      template_id: batch.template_id || '',
      segment_templates: {
        ...defaultSegmentTemplates,
        ...(batch.segment_templates || {}),
      }
    });
  };

  const saveBatchEdit = async () => {
    if (!editingBatchId) return;

    const payload = {};
    if (editForm.start_time) {
      payload.start_time = new Date(editForm.start_time).toISOString();
    }

    if (editForm.template_mode === 'single') {
      if (!editForm.template_id) {
        toast.error('Select a template');
        return;
      }
      payload.template_id = editForm.template_id;
    } else {
      const selected = Object.fromEntries(
        Object.entries(editForm.segment_templates).filter(([_, value]) => !!value)
      );
      if (Object.keys(selected).length === 0) {
        toast.error('Select at least one segment template');
        return;
      }
      payload.segment_templates = selected;
    }

    setActionLoading(`edit-${editingBatchId}`);
    try {
      await batchesAPI.update(editingBatchId, payload);
      toast.success('Batch updated successfully');
      setEditingBatchId(null);
      await loadBatches();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update batch'));
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending':
        return <Clock className="w-4 h-4 text-yellow-500" />;
      case 'scheduled':
        return <Clock className="w-4 h-4 text-yellow-400" />;
      case 'paused':
        return <PauseCircle className="w-4 h-4 text-blue-400" />;
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
      case 'scheduled':
        return 'text-yellow-400';
      case 'paused':
        return 'text-blue-400';
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
        <div className="flex gap-3">
          <button
            data-testid="clear-all-button"
            onClick={handleClearAll}
            disabled={batches.length === 0}
            className="px-4 py-2 bg-red-600/10 hover:bg-red-600/20 border border-red-600/30 text-red-400 rounded-md transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash2 className="w-4 h-4" />
            Clear All
          </button>
          <button
            data-testid="refresh-button"
            onClick={loadBatches}
            className="px-4 py-2 bg-[#2E2E2E] hover:bg-[#3E3E3E] rounded-md transition-colors flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
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
                      <div className="flex flex-wrap gap-2">
                        {(batch.status === 'pending' || batch.status === 'scheduled' || batch.status === 'paused') && (
                          <button
                            onClick={() => openEditPanel(batch)}
                            className="px-2 py-1 bg-[#3ECF8E]/15 text-[#3ECF8E] hover:bg-[#3ECF8E]/25 rounded text-xs font-medium flex items-center gap-1"
                          >
                            <Pencil className="w-3 h-3" />
                            Edit
                          </button>
                        )}

                        {(batch.status === 'pending' || batch.status === 'scheduled') && (
                          <button
                            onClick={() => handlePause(batch.id)}
                            disabled={actionLoading === `pause-${batch.id}`}
                            className="px-2 py-1 bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 rounded text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                          >
                            <PauseCircle className="w-3 h-3" />
                            Stop
                          </button>
                        )}

                        {batch.status === 'paused' && (
                          <button
                            onClick={() => handleResume(batch.id)}
                            disabled={actionLoading === `resume-${batch.id}`}
                            className="px-2 py-1 bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 rounded text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                          >
                            <PlayCircle className="w-3 h-3" />
                            Resume
                          </button>
                        )}

                        {(batch.status === 'pending' || batch.status === 'scheduled' || batch.status === 'paused' || batch.status === 'failed') && (
                          <button
                            onClick={() => handleDeleteBatch(batch.id)}
                            disabled={actionLoading === `delete-${batch.id}`}
                            className="px-2 py-1 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                          >
                            <Trash2 className="w-3 h-3" />
                            Delete
                          </button>
                        )}
                      </div>

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

      {editingBatchId && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Edit Scheduled Batch
            </h2>
            <button
              onClick={() => setEditingBatchId(null)}
              className="text-sm text-muted-foreground hover:text-white"
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium mb-2">New Scheduled Time</label>
              <input
                type="datetime-local"
                value={editForm.start_time}
                onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })}
                className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Template Mode</label>
              <select
                value={editForm.template_mode}
                onChange={(e) => setEditForm({ ...editForm, template_mode: e.target.value })}
                className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
              >
                <option value="segment">Segment Templates</option>
                <option value="single">Single Template for All</option>
              </select>
            </div>
          </div>

          {editForm.template_mode === 'single' ? (
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Template</label>
              <select
                value={editForm.template_id}
                onChange={(e) => setEditForm({ ...editForm, template_id: e.target.value })}
                className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
              >
                <option value="">-- Select Template --</option>
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                ))}
              </select>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
              {Object.keys(editForm.segment_templates).map((segment) => (
                <div key={segment}>
                  <label className="block text-xs font-medium mb-1 capitalize">{segment.replace(/_/g, ' ')}</label>
                  <select
                    value={editForm.segment_templates[segment]}
                    onChange={(e) => setEditForm({
                      ...editForm,
                      segment_templates: {
                        ...editForm.segment_templates,
                        [segment]: e.target.value
                      }
                    })}
                    className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md h-9 px-2 text-sm outline-none"
                  >
                    <option value="">-- None --</option>
                    {templates.map((tpl) => (
                      <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={saveBatchEdit}
              disabled={actionLoading === `edit-${editingBatchId}`}
              className="px-5 py-2 bg-[#3ECF8E] text-black hover:bg-[#34B27B] rounded-md font-medium disabled:opacity-50"
            >
              {actionLoading === `edit-${editingBatchId}` ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              onClick={() => setEditingBatchId(null)}
              className="px-5 py-2 bg-[#2E2E2E] hover:bg-[#3E3E3E] rounded-md"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Summary */}
      {batches.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Total Batches</p>
            <p className="text-2xl font-semibold font-mono">{batches.length}</p>
          </div>
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Pending</p>
            <p className="text-2xl font-semibold font-mono text-yellow-500">
              {batches.filter(b => b.status === 'pending' || b.status === 'scheduled').length}
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
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-4">
            <p className="text-sm text-muted-foreground mb-1">Paused</p>
            <p className="text-2xl font-semibold font-mono text-blue-400">
              {batches.filter(b => b.status === 'paused').length}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default BatchMonitorPage;
