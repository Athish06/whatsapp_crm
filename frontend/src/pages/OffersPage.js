import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Tag, PlusCircle, Trash2, Edit, Save, X, ArrowLeft, CheckCircle, Upload, FileSpreadsheet, AlertCircle, Layers, Grid3X3 } from 'lucide-react';
import { toast } from 'sonner';
import api, { offersAPI } from '../lib/api';

const OffersPage = () => {
  const { id: shopId } = useParams();
  const [offers, setOffers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  const [isEditing, setIsEditing] = useState(false);
  const [currentOffer, setCurrentOffer] = useState(null);

  // CSV Upload state
  const [showCSVModal, setShowCSVModal] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState('');
  const fileInputRef = useRef(null);

  const SEGMENTS = [
    { key: 'vip', label: 'VIP Champions' },
    { key: 'at_risk', label: 'At-Risk' },
    { key: 'potential_bulk', label: 'Potential (Bulk)' },
    { key: 'loyal_frequent', label: 'Loyal (Frequent)' },
    { key: 'boring', label: 'Occasional (Boring)' }
  ];

  useEffect(() => {
    fetchData();
  }, [shopId]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [offersRes, productsRes] = await Promise.all([
        offersAPI.list(shopId, false), // fetch all offers including inactive
        api.get(`/shops/${shopId}/products`) // fetch products
      ]);
      setOffers(offersRes.data.offers || []);
      setProducts(productsRes.data.products || []);
    } catch (err) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  // Build product name lookup
  const productNameMap = {};
  products.forEach(p => { productNameMap[p.product_id] = p.product_name || p.name || p.product_id; });

  const handleCreateNew = () => {
    setCurrentOffer({
      title: '',
      description: '',
      discount_value: '',
      target_segments: [],
      product_ids: [],
      category: '',
      discount_type: 'percentage',
      offer_mode: 'individual',
      is_active: true
    });
    setIsEditing(true);
  };

  const handleEdit = (offer) => {
    setCurrentOffer(offer);
    setIsEditing(true);
  };

  const handleDelete = async (offerId) => {
    if (!window.confirm("Are you sure you want to deactivate this offer?")) return;
    try {
      await offersAPI.delete(shopId, offerId);
      toast.success('Offer deactivated');
      fetchData();
    } catch (err) {
      toast.error('Failed to deactivate offer');
    }
  };

  const handleSave = async () => {
    if (!currentOffer.title || !currentOffer.discount_value) {
      toast.error('Please fill required fields (Title, Discount)');
      return;
    }
    try {
      const payload = {
        ...currentOffer,
        discount_value: parseFloat(currentOffer.discount_value) || 0,
        discount_type: currentOffer.discount_type || 'percentage',
        offer_mode: currentOffer.offer_mode || 'individual',
        product_ids: currentOffer.product_ids || [],
        target_segments: currentOffer.target_segments || [],
      };

      if (payload.id) {
        await offersAPI.update(shopId, payload.id, payload);
        toast.success('Offer updated');
      } else {
        await offersAPI.create(shopId, payload);
        toast.success('Offer created');
      }
      setIsEditing(false);
      fetchData();
    } catch (err) {
      toast.error('Failed to save offer');
    }
  };

  const toggleSegment = (segKey) => {
    setCurrentOffer(prev => {
      const segs = prev.target_segments || [];
      if (segs.includes(segKey)) {
        return { ...prev, target_segments: segs.filter(s => s !== segKey) };
      } else {
        return { ...prev, target_segments: [...segs, segKey] };
      }
    });
  };

  const toggleProduct = (prodId) => {
    setCurrentOffer(prev => {
      const pids = prev.product_ids || [];
      if (pids.includes(prodId)) {
        return { ...prev, product_ids: pids.filter(p => p !== prodId) };
      } else {
        return { ...prev, product_ids: [...pids, prodId] };
      }
    });
  };

  // ── CSV Upload Handlers ──
  const handleCSVUpload = async () => {
    if (!csvFile) return;
    setCsvUploading(true);
    setCsvError('');
    try {
      const result = await offersAPI.uploadCSV(shopId, csvFile);
      toast.success(`Successfully created ${result.data.created} offers from CSV`);
      setShowCSVModal(false);
      setCsvFile(null);
      fetchData();
    } catch (err) {
      const detail = err.response?.data?.detail || 'CSV upload failed';
      setCsvError(detail);
      toast.error(detail);
    } finally {
      setCsvUploading(false);
    }
  };

  if (loading) return <div className="p-8 text-muted-foreground">Loading offers...</div>;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link to={`/shop/${shopId}`} className="p-2 hover:bg-[#1C1C1C] rounded-lg transition-colors text-muted-foreground hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-4xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Offers & Promotions
            </h1>
          </div>
          <p className="text-muted-foreground ml-10">Manage dynamic segment-based offers for your campaigns.</p>
        </div>
        {!isEditing && (
          <div className="flex items-center gap-3">
            <button
              onClick={() => { setShowCSVModal(true); setCsvFile(null); setCsvError(''); }}
              className="flex items-center gap-2 px-5 py-3 bg-[#1C1C1C] border border-[#2E2E2E] text-white font-semibold rounded-lg hover:border-[#3ECF8E] transition-colors"
            >
              <Upload className="w-5 h-5" />
              Upload CSV
            </button>
            <button
              onClick={handleCreateNew}
              className="flex items-center gap-2 px-6 py-3 bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] transition-colors"
            >
              <PlusCircle className="w-5 h-5" />
              Create Offer
            </button>
          </div>
        )}
      </div>

      {/* ── CSV Upload Modal ── */}
      {showCSVModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-8 max-w-lg w-full">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-[#3ECF8E]/10 rounded-lg">
                  <FileSpreadsheet className="w-6 h-6 text-[#3ECF8E]" />
                </div>
                <h2 className="text-xl font-bold">Upload Offers CSV</h2>
              </div>
              <button onClick={() => setShowCSVModal(false)} className="text-muted-foreground hover:text-white">
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Required columns info */}
            <div className="bg-[#121212] border border-[#2E2E2E] rounded-lg p-4 mb-6">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Required Columns</p>
              <div className="flex flex-wrap gap-2 mb-3">
                {['title', 'discount_type', 'discount_value'].map(col => (
                  <span key={col} className="px-2 py-1 text-xs bg-[#3ECF8E]/10 text-[#3ECF8E] rounded-md font-mono">{col}</span>
                ))}
              </div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Optional Columns</p>
              <div className="flex flex-wrap gap-2">
                {['description', 'offer_mode', 'product_ids', 'category', 'target_segments', 'valid_from', 'valid_until'].map(col => (
                  <span key={col} className="px-2 py-1 text-xs bg-[#2E2E2E] text-gray-400 rounded-md font-mono">{col}</span>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-3">
                <strong>product_ids</strong> and <strong>target_segments</strong> use semicolons (;) to separate multiple values within a cell.
                All product IDs must exist in your product database.
              </p>
            </div>

            {/* File drop zone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors mb-4 ${
                csvFile ? 'border-[#3ECF8E] bg-[#3ECF8E]/5' : 'border-[#2E2E2E] hover:border-[#3ECF8E]/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => { setCsvFile(e.target.files[0]); setCsvError(''); }}
              />
              {csvFile ? (
                <div>
                  <FileSpreadsheet className="w-10 h-10 text-[#3ECF8E] mx-auto mb-2" />
                  <p className="text-white font-medium">{csvFile.name}</p>
                  <p className="text-xs text-muted-foreground">{(csvFile.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <div>
                  <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-2 opacity-50" />
                  <p className="text-muted-foreground">Click to select a CSV file</p>
                </div>
              )}
            </div>

            {/* Error display */}
            {csvError && (
              <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
                <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-400">{csvError}</p>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button onClick={() => setShowCSVModal(false)} className="px-5 py-2 text-muted-foreground hover:text-white transition-colors">
                Cancel
              </button>
              <button
                onClick={handleCSVUpload}
                disabled={!csvFile || csvUploading}
                className="flex items-center gap-2 px-6 py-2 bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] disabled:opacity-40 transition-colors"
              >
                {csvUploading ? 'Uploading...' : 'Upload & Create Offers'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isEditing ? (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-8 max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">{currentOffer.id ? 'Edit Offer' : 'New Offer'}</h2>
            <button onClick={() => setIsEditing(false)} className="text-muted-foreground hover:text-white">
              <X className="w-6 h-6" />
            </button>
          </div>

          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2 text-muted-foreground">Offer Title *</label>
                <input
                  type="text"
                  value={currentOffer.title}
                  onChange={(e) => setCurrentOffer({ ...currentOffer, title: e.target.value })}
                  placeholder="e.g. 20% Off Groceries"
                  className="w-full px-4 py-2 bg-[#121212] border border-[#2E2E2E] rounded-lg focus:outline-none focus:border-[#3ECF8E]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2 text-muted-foreground">Discount Value *</label>
                <div className="flex gap-2">
                  <select
                    value={currentOffer.discount_type || 'percentage'}
                    onChange={(e) => setCurrentOffer({ ...currentOffer, discount_type: e.target.value })}
                    className="bg-[#121212] border border-[#2E2E2E] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-[#3ECF8E]"
                  >
                    <option value="percentage">%</option>
                    <option value="flat">Flat</option>
                    <option value="bogo">BOGO</option>
                  </select>
                  <input
                    type="number"
                    value={currentOffer.discount_value}
                    onChange={(e) => setCurrentOffer({ ...currentOffer, discount_value: e.target.value })}
                    placeholder="e.g. 20"
                    className="flex-1 px-4 py-2 bg-[#121212] border border-[#2E2E2E] rounded-lg focus:outline-none focus:border-[#3ECF8E]"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-muted-foreground">Description</label>
              <textarea
                value={currentOffer.description}
                onChange={(e) => setCurrentOffer({ ...currentOffer, description: e.target.value })}
                className="w-full px-4 py-2 bg-[#121212] border border-[#2E2E2E] rounded-lg focus:outline-none focus:border-[#3ECF8E] min-h-[80px]"
                placeholder="Internal notes or terms..."
              />
            </div>

            {/* ── Offer Mode (Combined / Individual) ── */}
            <div className="border-t border-[#2E2E2E] pt-6">
              <label className="block text-sm font-medium mb-4 text-white">Offer Mode</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setCurrentOffer({ ...currentOffer, offer_mode: 'individual' })}
                  className={`flex items-center gap-3 p-4 rounded-lg border text-left transition-colors ${
                    currentOffer.offer_mode !== 'combined'
                      ? 'bg-[#3ECF8E]/10 border-[#3ECF8E] text-[#3ECF8E]'
                      : 'bg-[#121212] border-[#2E2E2E] text-muted-foreground hover:border-gray-500'
                  }`}
                >
                  <Grid3X3 className="w-5 h-5" />
                  <div>
                    <p className="font-medium">Individual</p>
                    <p className="text-xs opacity-70">Discount applies to each product separately</p>
                  </div>
                </button>
                <button
                  onClick={() => setCurrentOffer({ ...currentOffer, offer_mode: 'combined' })}
                  className={`flex items-center gap-3 p-4 rounded-lg border text-left transition-colors ${
                    currentOffer.offer_mode === 'combined'
                      ? 'bg-[#8B5CF6]/10 border-[#8B5CF6] text-[#8B5CF6]'
                      : 'bg-[#121212] border-[#2E2E2E] text-muted-foreground hover:border-gray-500'
                  }`}
                >
                  <Layers className="w-5 h-5" />
                  <div>
                    <p className="font-medium">Combined</p>
                    <p className="text-xs opacity-70">Discount applies only when ALL products are bought together</p>
                  </div>
                </button>
              </div>
            </div>

            {/* ── Target Segments (Optional) ── */}
            <div className="border-t border-[#2E2E2E] pt-6">
              <label className="block text-sm font-medium mb-1 text-white">Target Segments</label>
              <p className="text-xs text-muted-foreground mb-4">Optional — leave empty for a general offer open to all customers.</p>
              <div className="grid grid-cols-3 gap-3">
                {SEGMENTS.map(seg => {
                  const isActive = currentOffer.target_segments?.includes(seg.key);
                  return (
                    <button
                      key={seg.key}
                      onClick={() => toggleSegment(seg.key)}
                      className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${
                        isActive 
                          ? 'bg-[#3ECF8E]/10 border-[#3ECF8E] text-[#3ECF8E]' 
                          : 'bg-[#121212] border-[#2E2E2E] text-muted-foreground hover:border-gray-500'
                      }`}
                    >
                      {isActive ? <CheckCircle className="w-5 h-5" /> : <div className="w-5 h-5 rounded-full border border-[#2E2E2E]" />}
                      {seg.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="border-t border-[#2E2E2E] pt-6">
              <label className="block text-sm font-medium mb-2 text-white">Target Products (Optional)</label>
              <p className="text-sm text-muted-foreground mb-4">If selected, this offer will prioritize customers who buy these items.</p>
              
              <div className="max-h-[200px] overflow-y-auto bg-[#121212] border border-[#2E2E2E] rounded-lg p-2 space-y-1">
                {products.length === 0 ? (
                  <p className="p-4 text-center text-muted-foreground text-sm">No products found in inventory.</p>
                ) : (
                  products.map(p => {
                    const isActive = currentOffer.product_ids?.includes(p.product_id);
                    return (
                      <button
                        key={p.product_id}
                        onClick={() => toggleProduct(p.product_id)}
                        className={`w-full flex items-center gap-3 p-2 rounded-md hover:bg-[#1C1C1C] transition-colors ${isActive ? 'text-white' : 'text-muted-foreground'}`}
                      >
                        <input type="checkbox" checked={isActive} readOnly className="rounded border-[#2E2E2E] bg-transparent text-[#3ECF8E] focus:ring-[#3ECF8E]" />
                        <span className="flex-1 text-left">{p.product_name || p.name || p.product_id}</span>
                        <span className="text-xs opacity-50">{p.category}</span>
                      </button>
                    )
                  })
                )}
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-6 border-t border-[#2E2E2E]">
              <button onClick={() => setIsEditing(false)} className="px-6 py-2 text-muted-foreground hover:text-white transition-colors">
                Cancel
              </button>
              <button onClick={handleSave} className="flex items-center gap-2 px-6 py-2 bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] transition-colors">
                <Save className="w-4 h-4" />
                Save Offer
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {offers.map(offer => (
            <div key={offer.id} className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-6 hover:border-[#4A4A4A] transition-colors group">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="p-3 bg-[#3ECF8E]/10 rounded-lg text-[#3ECF8E]">
                    <Tag className="w-6 h-6" />
                  </div>
                  {/* Offer mode badge */}
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                    offer.offer_mode === 'combined'
                      ? 'bg-[#8B5CF6]/10 text-[#8B5CF6] border-[#8B5CF6]/30'
                      : 'bg-[#3ECF8E]/10 text-[#3ECF8E] border-[#3ECF8E]/30'
                  }`}>
                    {offer.offer_mode === 'combined' ? '⛓ Combined' : '▤ Individual'}
                  </span>
                </div>
                <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => handleEdit(offer)} className="p-2 text-muted-foreground hover:text-white bg-[#121212] rounded-md">
                    <Edit className="w-4 h-4" />
                  </button>
                  <button onClick={() => handleDelete(offer.id)} className="p-2 text-red-400 hover:text-red-300 bg-[#121212] rounded-md">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <h3 className="text-xl font-bold mb-1 text-white">{offer.title}</h3>
              <p className="text-[#3ECF8E] font-medium mb-4">
                {offer.discount_type === 'percentage' ? `${offer.discount_value}%` : offer.discount_type === 'bogo' ? 'BOGO' : `₹${offer.discount_value}`} OFF
              </p>
              
              <div className="space-y-3">
                {offer.target_segments?.length > 0 ? (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Target Segments</p>
                    <div className="flex flex-wrap gap-2">
                      {offer.target_segments.map(seg => (
                        <span key={seg} className="px-2 py-1 text-xs bg-[#121212] text-gray-300 rounded-md border border-[#2E2E2E]">
                          {SEGMENTS.find(s => s.key === seg)?.label || seg}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div>
                    <span className="px-2 py-1 text-xs bg-[#3ECF8E]/10 text-[#3ECF8E] rounded-md border border-[#3ECF8E]/20">
                      Open to All
                    </span>
                  </div>
                )}
                {offer.product_ids?.length > 0 && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1 uppercase tracking-wider">Target Products</p>
                    <div className="flex flex-wrap gap-1">
                      {offer.product_ids.slice(0, 3).map(pid => (
                        <span key={pid} className="text-xs text-gray-300 bg-[#121212] px-2 py-0.5 rounded border border-[#2E2E2E]">
                          {productNameMap[pid] || pid}
                        </span>
                      ))}
                      {offer.product_ids.length > 3 && (
                        <span className="text-xs text-muted-foreground px-2 py-0.5">
                          +{offer.product_ids.length - 3} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {!offer.is_active && (
                <div className="mt-4 inline-block px-3 py-1 bg-red-500/10 text-red-400 text-xs rounded-full border border-red-500/20">
                  Inactive
                </div>
              )}
            </div>
          ))}

          {offers.length === 0 && (
            <div className="col-span-full py-16 text-center border border-dashed border-[#2E2E2E] rounded-xl bg-[#1C1C1C]">
              <Tag className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium text-white mb-2">No offers created yet</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-6">Create your first offer to dynamically attach discounts to your WhatsApp campaigns based on customer behavior.</p>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => { setShowCSVModal(true); setCsvFile(null); setCsvError(''); }}
                  className="inline-flex items-center gap-2 px-5 py-2 bg-[#1C1C1C] border border-[#2E2E2E] text-white font-semibold rounded-lg hover:border-[#3ECF8E] transition-colors"
                >
                  <Upload className="w-5 h-5" />
                  Upload CSV
                </button>
                <button
                  onClick={handleCreateNew}
                  className="inline-flex items-center gap-2 px-6 py-2 bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] transition-colors"
                >
                  <PlusCircle className="w-5 h-5" />
                  Create First Offer
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default OffersPage;
