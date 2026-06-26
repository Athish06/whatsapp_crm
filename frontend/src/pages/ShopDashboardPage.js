import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Upload, Users, ShoppingBag, Receipt, PlusCircle, Activity, CheckCircle, Database, Trash2, AlertTriangle, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { shopsAPI } from '../lib/api';

/* ==========================================
   Column Mapping Modal (inline)
   ========================================== */
const ColumnMappingModal = ({ dataType, detectedColumns, suggestedMapping, requiredColumns, onConfirm, onCancel, loading }) => {
  const [mapping, setMapping] = useState(suggestedMapping || {});

  const handleChange = (key, value) => {
    setMapping(prev => ({ ...prev, [key]: value === 'none' ? null : value }));
  };

  const isRequired = (col) => {
    if (dataType === 'customers') return ['name', 'phone'].includes(col.key);
    if (dataType === 'products') return ['product_id', 'product_name', 'category', 'price', 'unit'].includes(col.key);
    if (dataType === 'transactions') return ['customer_id', 'product_id', 'purchase_date', 'quantity', 'amount'].includes(col.key);
    return false;
  };

  const allRequiredMapped = requiredColumns
    .filter(c => isRequired(c))
    .every(c => mapping[c.key] && mapping[c.key] !== 'none');

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-6 shadow-2xl">
        <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Map Columns — {dataType === 'customers' ? 'Customer Data' : dataType === 'products' ? 'Product Master' : 'Transactions'}
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          We detected <span className="text-[#3ECF8E] font-semibold">{detectedColumns.length}</span> columns. Map them to the required fields below.
        </p>

        <div className="space-y-4">
          {requiredColumns.map((col) => {
            const req = isRequired(col);
            const mapped = mapping[col.key] && mapping[col.key] !== 'none';
            return (
              <div key={col.key} className="flex items-start gap-4 bg-[#121212] p-4 rounded-lg border border-[#2E2E2E]">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-white">{col.label}</span>
                    {req && <span className="text-red-400 text-xs">required</span>}
                    {mapped && <CheckCircle className="w-4 h-4 text-[#3ECF8E]" />}
                  </div>
                  <p className="text-xs text-muted-foreground">{col.description}</p>
                </div>
                <select
                  value={mapping[col.key] || 'none'}
                  onChange={(e) => handleChange(col.key, e.target.value)}
                  className={`w-56 px-3 py-2 bg-[#1C1C1C] border rounded-md text-sm text-white focus:outline-none focus:ring-2 transition-all ${
                    req && !mapped
                      ? 'border-red-400 focus:ring-red-400/50'
                      : 'border-[#2E2E2E] focus:ring-[#3ECF8E]/50'
                  }`}
                >
                  <option value="none">— Select Column —</option>
                  {detectedColumns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-[#2E2E2E]">
          <button onClick={onCancel} disabled={loading} className="px-5 py-2 text-muted-foreground hover:text-white transition-colors">
            Cancel
          </button>
          <button
            onClick={() => onConfirm(mapping)}
            disabled={!allRequiredMapped || loading}
            className="px-6 py-2 bg-[#3ECF8E] text-black font-semibold rounded-md hover:bg-[#32B37A] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Processing…' : 'Confirm & Process'}
          </button>
        </div>
      </div>
    </div>
  );
};

/* ==========================================
   RFM Segmentation Chart
   ========================================== */
const RFMChart = ({ segmentCounts }) => {
  const segments = [
    { key: 'vip', label: 'VIP Champions', color: '#3ECF8E' },
    { key: 'at_risk', label: 'At-Risk', color: '#EF4444' },
    { key: 'potential_bulk', label: 'Potential (Bulk)', color: '#8B5CF6' },
    { key: 'loyal_frequent', label: 'Loyal (Frequent)', color: '#3B82F6' },
    { key: 'boring', label: 'Occasional', color: '#6B7280' },

  ];
  const total = Object.values(segmentCounts).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="space-y-3">
      {segments.map(({ key, label, color }) => {
        const count = segmentCounts[key] || 0;
        const pct = Math.round((count / total) * 100);
        return (
          <div key={key}>
            <div className="flex justify-between text-sm mb-1">
              <span style={{ color }}>{label}</span>
              <span className="text-muted-foreground">{count} ({pct}%)</span>
            </div>
            <div className="w-full bg-[#2E2E2E] rounded-full h-3 overflow-hidden">
              <div
                className="h-3 rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

/* ==========================================
   Upload Card (Real)
   ========================================== */
const UploadCard = ({ title, icon: Icon, color, csvStatus, dataType, shopId, onUploadComplete }) => {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [mappingState, setMappingState] = useState(null); // { detected, suggested, required, fileId }
  const [processing, setProcessing] = useState(false);

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await shopsAPI.upload(shopId, dataType, file);
      const d = res.data;
      setMappingState({
        detected: d.detected_columns,
        suggested: d.suggested_mapping,
        required: d.required_columns,
        fileId: d.file_id,
      });
      if (d.duplicate) {
        toast.info(d.message || "This file was uploaded before. You can re-map and re-process it.");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleConfirmMapping = async (columnMapping) => {
    if (!mappingState) return;
    setProcessing(true);
    try {
      const res = await shopsAPI.process(shopId, dataType, mappingState.fileId, { column_mapping: columnMapping });
      toast.success(`${title} processed successfully!`);
      setMappingState(null);
      onUploadComplete(dataType, res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Processing failed');
    } finally {
      setProcessing(false);
    }
  };

  const uploaded = csvStatus?.uploaded;
  const lastUpdated = csvStatus?.last_updated;

  return (
    <>
      <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 relative overflow-hidden">
        <div className="flex items-start justify-between mb-4">
          <div className="w-12 h-12 bg-[#121212] rounded-lg flex items-center justify-center" style={{ color }}>
            <Icon className="w-6 h-6" />
          </div>
          {uploaded && <CheckCircle className="w-6 h-6 text-[#3ECF8E]" />}
        </div>

        <h3 className="text-xl font-semibold mb-1">{title}</h3>
        {uploaded && lastUpdated ? (
          <div>
            <p className="text-xs text-[#3ECF8E] mb-1">Last updated: {new Date(lastUpdated).toLocaleString()}</p>
            {csvStatus.period_tag && (
              <p className="text-xs text-[#8B5CF6] mb-4 font-semibold uppercase tracking-wider">
                Cycle Tag: {csvStatus.period_tag}
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground mb-4">No data uploaded yet</p>
        )}

        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="w-full flex items-center justify-center px-4 py-2 bg-[#121212] border border-[#2E2E2E] rounded-md hover:border-[#3ECF8E] transition-colors group disabled:opacity-50"
        >
          <Upload className="w-4 h-4 mr-2 text-muted-foreground group-hover:text-[#3ECF8E]" />
          <span className="text-sm font-medium group-hover:text-[#3ECF8E]">
            {uploading ? 'Uploading…' : uploaded ? 'Update CSV' : 'Upload CSV'}
          </span>
        </button>
      </div>

      {mappingState && (
        <ColumnMappingModal
          dataType={dataType}
          detectedColumns={mappingState.detected}
          suggestedMapping={mappingState.suggested}
          requiredColumns={mappingState.required}
          onConfirm={handleConfirmMapping}
          onCancel={() => setMappingState(null)}
          loading={processing}
        />
      )}
    </>
  );
};

/* ==========================================
   Main Page
   ========================================== */
const ShopDashboardPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [shop, setShop] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processResults, setProcessResults] = useState({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null); // 'campaign' | 'shop' | null

  const loadShop = useCallback(async () => {
    try {
      const res = await shopsAPI.getDetail(id);
      setShop(res.data);
    } catch (err) {
      toast.error('Failed to load shop');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadShop();
  }, [loadShop]);

  const handleUploadComplete = (dataType, result) => {
    setProcessResults(prev => ({ ...prev, [dataType]: result }));
    loadShop();
  };

  const handleDeleteCampaign = async () => {
    try {
      await shopsAPI.deleteCampaign(id);
      toast.success('Campaign data deleted');
      setShowDeleteConfirm(null);
      loadShop();
    } catch (err) {
      toast.error('Failed to delete campaign data');
    }
  };

  const handleDeleteShop = async () => {
    try {
      await shopsAPI.deleteShop(id);
      toast.success('Shop deleted permanently');
      navigate('/dashboard');
    } catch (err) {
      toast.error('Failed to delete shop');
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground animate-pulse text-lg">Loading shop…</div>
      </div>
    );
  }

  if (!shop) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground mb-4">Shop not found.</p>
        <Link to="/dashboard" className="text-[#3ECF8E] hover:underline">Back to Dashboard</Link>
      </div>
    );
  }

  const stats = shop.live_stats || {};
  const totalMessages = stats.total_messages || 0;
  const sentPct = totalMessages > 0 ? Math.round((stats.sent / totalMessages) * 100) : 0;
  const segCounts = shop.segment_counts || {};
  const hasSegments = Object.keys(segCounts).length > 0;
  const categoryBreakdown = shop.category_breakdown || {};
  const topProducts = shop.top_products_by_category || {};
  const premiumProducts = shop.premium_products_by_category || {};
  const bulkProducts = shop.bulk_products_by_category || {};
  const customerCatPct = shop.customer_category_pct || {};
  const hasBehavioral = Object.keys(topProducts).length > 0;

  return (
    <div className="p-8 space-y-8">
      {/* Status Ribbon */}
      {totalMessages > 0 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-3 flex items-center justify-between text-sm shadow-[0_0_15px_rgba(46,46,46,0.5)]">
          <div className="flex items-center space-x-6">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 rounded-full bg-[#3ECF8E] animate-pulse"></div>
              <span className="text-muted-foreground">Status:</span>
              <span className="font-medium text-[#3ECF8E]">Active</span>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-muted-foreground">Delivery:</span>
            <div className="flex items-center space-x-2 bg-[#121212] px-3 py-1 rounded-md border border-[#2E2E2E]">
              <span className="text-[#3ECF8E] font-medium">{stats.sent || 0}</span>
              <span className="text-muted-foreground">/</span>
              <span>{totalMessages} Sent</span>
              <span className="text-xs text-[#3ECF8E] ml-2">({sentPct}%)</span>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center space-x-2 text-muted-foreground mb-2 text-sm">
            <Link to="/dashboard" className="hover:text-white transition-colors flex items-center gap-1">
              <ArrowLeft className="w-3 h-3" /> Dashboard
            </Link>
            <span>/</span>
            <span className="text-white">{shop.shop_name}</span>
          </div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
            {shop.shop_name}
          </h1>
          <p className="text-muted-foreground">
            Global Data Container & Shop Operations
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to={`/shop/${id}/offers`}
            className="flex items-center px-4 py-2 bg-[#1C1C1C] border border-[#2E2E2E] text-white font-medium rounded-md hover:bg-[#2A2A2A] transition-colors"
          >
            Offers
          </Link>
          <Link
            to={`/shop/${id}/monitoring`}
            className="flex items-center px-4 py-2 bg-[#1C1C1C] border border-[#2E2E2E] text-white font-medium rounded-md hover:bg-[#2A2A2A] transition-colors"
          >
            Monitoring
          </Link>
          <Link
            to={`/campaign/new/${id}`}
            className="flex items-center px-5 py-2.5 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors"
          >
            <PlusCircle className="w-5 h-5 mr-2" />
            Create Campaign
          </Link>
        </div>
      </div>

      {/* Upload Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <UploadCard
          title="Customer Data"
          icon={Users}
          color="#3B82F6"
          csvStatus={shop.csv_status?.customer_data}
          dataType="customers"
          shopId={id}
          onUploadComplete={handleUploadComplete}
        />
        <UploadCard
          title="Product Master"
          icon={ShoppingBag}
          color="#F59E0B"
          csvStatus={shop.csv_status?.product_data}
          dataType="products"
          shopId={id}
          onUploadComplete={handleUploadComplete}
        />
        <UploadCard
          title="Transactions"
          icon={Receipt}
          color="#8B5CF6"
          csvStatus={shop.csv_status?.transaction_data}
          dataType="transactions"
          shopId={id}
          onUploadComplete={handleUploadComplete}
        />
      </div>

      {/* RFM Segmentation + Behavioral Intelligence */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* RFM Segmentation */}
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center">
              <Activity className="w-6 h-6 text-[#3ECF8E] mr-3" />
              <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
                RFM Segmentation
              </h2>
            </div>
            {shop.insights_last_updated && (
              <span className="text-xs text-muted-foreground">
                Updated: {new Date(shop.insights_last_updated).toLocaleString()}
              </span>
            )}
          </div>
          {hasSegments ? (
            <div>
              <div className="mb-4 bg-[#121212] p-3 rounded-md border border-[#2E2E2E]">
                <p className="text-3xl font-bold text-white mb-1 font-mono">{shop.customer_count}</p>
                <p className="text-xs text-muted-foreground">Total Segmented Customers</p>
              </div>
              <RFMChart segmentCounts={segCounts} />
            </div>
          ) : (
            <div className="text-center py-10">
              <Database className="w-12 h-12 text-[#2E2E2E] mx-auto mb-4" />
              <p className="text-muted-foreground text-sm">Upload customer CSV to see RFM segmentation results.</p>
            </div>
          )}
        </div>

        {/* Behavioral Intelligence */}
        {/* LEVEL_2_HOOK: Replace this section with Level 2 behavioral segmentation UI */}
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center">
              <ShoppingBag className="w-6 h-6 text-[#F59E0B] mr-3" />
              <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
                Behavioral Insights
              </h2>
            </div>
            <span className="text-xs bg-[#F59E0B]/10 text-[#F59E0B] px-2 py-1 rounded-full border border-[#F59E0B]/30">
              Phase 2
            </span>
          </div>
          {hasBehavioral ? (
            <div className="space-y-4">
              <div className="bg-[#121212] p-3 rounded-md border border-[#2E2E2E]">
                <p className="text-xs text-muted-foreground mb-1">Categories Found</p>
                <p className="text-2xl font-bold text-white font-mono">{Object.keys(categoryBreakdown).length}</p>
              </div>

              {/* Top products per category */}
              <div>
                <p className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Top Product per Category</p>
                <div className="space-y-2">
                  {Object.entries(topProducts).slice(0, 5).map(([cat, info]) => (
                    <div key={cat} className="flex flex-col bg-[#121212] p-3 rounded border border-[#2E2E2E] text-sm">
                      <div className="flex justify-between items-center">
                        <div>
                          <span className="text-white font-medium">{cat}</span>
                          <span className="text-muted-foreground ml-2">→ {info.product_name}</span>
                        </div>
                        <span className="text-xs text-[#8B5CF6] font-mono">{info.total_qty} units</span>
                      </div>
                      {/* Premium & Bulk details per category */}
                      {(premiumProducts[cat] || bulkProducts[cat]) && (
                        <div className="flex flex-col gap-1 mt-2 pt-2 border-t border-[#2E2E2E]/50 text-xs">
                          {premiumProducts[cat] && (
                            <div className="flex items-start">
                              <span className="text-[#F59E0B] font-medium min-w-[85px]">Premium Pick:</span>
                              <span className="text-muted-foreground line-clamp-1 flex-1">{premiumProducts[cat]}</span>
                            </div>
                          )}
                          {bulkProducts[cat] && (
                            <div className="flex items-start">
                              <span className="text-[#3B82F6] font-medium min-w-[85px]">Bulk Pick:</span>
                              <span className="text-muted-foreground line-clamp-1 flex-1">{bulkProducts[cat]}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Customer category percentages */}
              {Object.keys(customerCatPct).length > 0 && (
                <div>
                  <p className="text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Customer Affinity</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(customerCatPct).slice(0, 5).map(([cat, pct]) => (
                      <span key={cat} className="px-3 py-1.5 bg-[#8B5CF6]/15 text-[#8B5CF6] text-sm rounded-md font-medium border border-[#8B5CF6]/20">
                        {cat} ({pct}%)
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-10">
              <Database className="w-12 h-12 text-[#2E2E2E] mx-auto mb-4" />
              <p className="text-muted-foreground text-sm">Upload Products + Transactions to unlock behavioral insights.</p>
            </div>
          )}
        </div>
      </div>

      {/* Danger Zone */}
      <div className="bg-[#1C1C1C] border border-red-500/20 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-red-400 mb-4 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" /> Danger Zone
        </h3>
        <div className="flex flex-wrap gap-4">
          <button
            onClick={() => setShowDeleteConfirm('campaign')}
            className="flex items-center px-4 py-2 border border-red-500/30 text-red-400 rounded-md hover:bg-red-500/10 transition-colors text-sm"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Delete Campaign Data
          </button>
          <button
            onClick={() => setShowDeleteConfirm('shop')}
            className="flex items-center px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 rounded-md hover:bg-red-500/20 transition-colors text-sm font-semibold"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Delete Shop & All Data
          </button>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl max-w-md w-full p-6 shadow-2xl">
            <h3 className="text-xl font-bold text-red-400 mb-3" style={{ fontFamily: 'Chivo, sans-serif' }}>
              {showDeleteConfirm === 'campaign' ? 'Delete Campaign Data?' : 'Delete Shop & All Data?'}
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              {showDeleteConfirm === 'campaign'
                ? 'This will delete all messages, batches, and campaigns for this shop. Customer, product, and transaction data will be kept.'
                : 'This will PERMANENTLY delete the shop and ALL associated data: customers, products, transactions, campaigns, messages, files. This cannot be undone.'}
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteConfirm(null)} className="px-4 py-2 text-muted-foreground hover:text-white transition-colors">
                Cancel
              </button>
              <button
                onClick={showDeleteConfirm === 'campaign' ? handleDeleteCampaign : handleDeleteShop}
                className="px-4 py-2 bg-red-500 text-white font-semibold rounded-md hover:bg-red-600 transition-colors"
              >
                {showDeleteConfirm === 'campaign' ? 'Delete Campaigns' : 'Delete Everything'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ShopDashboardPage;