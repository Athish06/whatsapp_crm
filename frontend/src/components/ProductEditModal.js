import React, { useState, useEffect } from 'react';
import { X, Search, Check, AlertTriangle, RefreshCw } from 'lucide-react';
import { productsAPI } from '../lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '../lib/utils';

const ProductEditModal = ({ shopId, category, onClose }) => {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);

  useEffect(() => {
    fetchProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const fetchProducts = async (searchTerm = '') => {
    try {
      setLoading(true);
      const res = await productsAPI.list(shopId, { category, search: searchTerm });
      setProducts(res.data.products || []);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to fetch products'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      fetchProducts(search);
    }, 500);
    return () => clearTimeout(delayDebounceFn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const toggleFlag = async (productId, field, currentValue) => {
    try {
      // Optimistic update
      setProducts(products.map(p => 
        p.product_id === productId ? { ...p, [field]: !currentValue } : p
      ));
      await productsAPI.update(shopId, productId, { [field]: !currentValue });
    } catch (error) {
      toast.error('Failed to update product');
      fetchProducts(search); // Revert on failure
    }
  };

  const handleSaveAndRecalculate = async () => {
    try {
      setRecalculating(true);
      const res = await productsAPI.recalculateInsights(shopId);
      toast.success(`Recalculated insights for ${res.data.recalculated_count} customers!`);
      onClose(); // Will trigger dashboard reload
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to recalculate insights'));
    } finally {
      setRecalculating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl w-full max-w-3xl flex flex-col max-h-[85vh] shadow-2xl">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[#2E2E2E]">
          <div>
            <h2 className="text-xl font-bold text-white font-chivo">Edit {category} Picks</h2>
            <p className="text-sm text-muted-foreground mt-1">Override Premium and Bulk products for this category.</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[#2E2E2E] rounded-md transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Warning Banner */}
        <div className="bg-red-500/10 border-b border-red-500/20 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <p className="text-sm text-red-400 font-medium">
            <span className="font-bold">WARNING:</span> Editing these picks requires recalculating the entire customer database so their favorites update. Click "Save & Recalculate Customers" when you are done.
          </p>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-[#2E2E2E]">
          <div className="relative">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search products by name..."
              className="w-full bg-[#121212] border border-[#2E2E2E] rounded-md pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-[#3ECF8E] transition-colors"
            />
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <RefreshCw className="w-6 h-6 text-muted-foreground animate-spin" />
            </div>
          ) : products.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground">No products found.</div>
          ) : (
            products.map((p) => (
              <div key={p.product_id} className="flex items-center justify-between bg-[#121212] p-3 rounded-lg border border-[#2E2E2E] hover:border-[#4E4E4E] transition-colors">
                <div>
                  <h4 className="font-medium text-white">{p.product_name}</h4>
                  <div className="flex gap-3 text-xs text-muted-foreground mt-1 font-mono">
                    <span>ID: {p.product_id}</span>
                    <span>•</span>
                    <span>${parseFloat(p.price_per_unit || 0).toFixed(2)} / {p.unit}</span>
                  </div>
                </div>
                
                <div className="flex items-center gap-4 ml-4 shrink-0">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <div className={`w-5 h-5 rounded flex items-center justify-center border transition-colors ${
                      p.is_premium 
                        ? 'bg-[#F59E0B] border-[#F59E0B]' 
                        : 'bg-transparent border-[#4E4E4E] group-hover:border-[#F59E0B]'
                    }`}>
                      {p.is_premium && <Check className="w-3.5 h-3.5 text-black stroke-[3]" />}
                    </div>
                    <span className={`text-sm ${p.is_premium ? 'text-[#F59E0B] font-medium' : 'text-muted-foreground'}`}>
                      Premium
                    </span>
                    <input 
                      type="checkbox" 
                      className="hidden" 
                      checked={!!p.is_premium}
                      onChange={() => toggleFlag(p.product_id, 'is_premium', !!p.is_premium)}
                    />
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer group w-20">
                    <div className={`w-5 h-5 rounded flex items-center justify-center border transition-colors ${
                      p.is_bulk 
                        ? 'bg-[#3B82F6] border-[#3B82F6]' 
                        : 'bg-transparent border-[#4E4E4E] group-hover:border-[#3B82F6]'
                    }`}>
                      {p.is_bulk && <Check className="w-3.5 h-3.5 text-white stroke-[3]" />}
                    </div>
                    <span className={`text-sm ${p.is_bulk ? 'text-[#3B82F6] font-medium' : 'text-muted-foreground'}`}>
                      Bulk
                    </span>
                    <input 
                      type="checkbox" 
                      className="hidden" 
                      checked={!!p.is_bulk}
                      onChange={() => toggleFlag(p.product_id, 'is_bulk', !!p.is_bulk)}
                    />
                  </label>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#2E2E2E] bg-[#121212] rounded-b-xl flex justify-end gap-3">
          <button 
            onClick={onClose}
            disabled={recalculating}
            className="px-4 py-2 rounded-md hover:bg-[#2E2E2E] text-sm font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleSaveAndRecalculate}
            disabled={recalculating}
            className="px-5 py-2 bg-[#3ECF8E] hover:bg-[#34B27B] text-black text-sm font-bold rounded-md transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {recalculating ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Recalculating...</>
            ) : (
              'Save & Recalculate Customers'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProductEditModal;
