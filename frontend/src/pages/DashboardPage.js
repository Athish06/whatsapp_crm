import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Store, Plus, ArrowRight, Activity, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { shopsAPI } from '../lib/api';

const DashboardPage = () => {
  const navigate = useNavigate();
  const [shops, setShops] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isCreatingShop, setIsCreatingShop] = useState(false);
  const [newShopName, setNewShopName] = useState('');

  const loadShops = useCallback(async () => {
    try {
      const res = await shopsAPI.list();
      setShops(res.data.shops || []);
    } catch (err) {
      console.error('Failed to load shops:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadShops();
    const interval = setInterval(loadShops, 10000);
    return () => clearInterval(interval);
  }, [loadShops]);

  const handleCreateShop = async (e) => {
    e.preventDefault();
    if (!newShopName.trim()) {
      toast.error('Please enter a shop name');
      return;
    }
    try {
      const res = await shopsAPI.create(newShopName.trim());
      toast.success(`Shop "${newShopName}" created!`);
      setNewShopName('');
      setIsCreatingShop(false);
      navigate(`/shop/${res.data.id}`);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to create shop';
      toast.error(msg);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground animate-pulse text-lg">Loading shops…</div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8 text-white">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Your Shops
          </h1>
          <p className="text-muted-foreground">
            Manage your stores, view live pulse, and access data containers
          </p>
        </div>
        {!isCreatingShop && (
          <button
            onClick={() => setIsCreatingShop(true)}
            className="flex items-center px-4 py-2 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors"
          >
            <Plus className="w-5 h-5 mr-2" />
            Add New Shop
          </button>
        )}
      </div>

      {isCreatingShop && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 mb-8 max-w-md">
          <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Create a New Shop
          </h2>
          <form onSubmit={handleCreateShop}>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Shop Name
                </label>
                <input
                  type="text"
                  value={newShopName}
                  onChange={(e) => setNewShopName(e.target.value)}
                  placeholder="e.g., Sree Ganesh Stores"
                  className="w-full bg-[#121212] border border-[#2E2E2E] rounded-md px-3 py-2 text-white focus:outline-none focus:border-[#3ECF8E]"
                  autoFocus
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsCreatingShop(false)}
                  className="px-4 py-2 text-muted-foreground hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors"
                >
                  Create Shop
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Empty State */}
      {shops.length === 0 && !isCreatingShop ? (
        <div className="flex flex-col items-center justify-center p-16 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg border-dashed">
          <div className="w-16 h-16 bg-[#121212] rounded-full flex items-center justify-center mb-6">
            <Store className="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 className="text-2xl font-semibold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
            No Shops found.
          </h2>
          <p className="text-muted-foreground mb-8 text-center max-w-md">
            Add a Shop to get started. A Shop acts as your global data container for customers, products, and campaigns.
          </p>
          <button
            onClick={() => setIsCreatingShop(true)}
            className="flex items-center px-6 py-3 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors"
          >
            <Plus className="w-5 h-5 mr-2" />
            Add a Shop
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {shops.map((shop) => {
            const stats = shop.live_stats || {};
            const totalMessages = stats.total_messages || 0;
            const sentPct = totalMessages > 0 ? Math.round((stats.sent / totalMessages) * 100) : 0;
            return (
              <div
                key={shop.id}
                className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 hover:border-[#3ECF8E] transition-all group flex flex-col relative"
              >
                {/* Shop Header */}
                <div className="flex justify-between items-start mb-6">
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 bg-[#121212] flex-shrink-0 border border-[#2E2E2E] rounded-lg flex items-center justify-center text-[#3ECF8E]">
                      <Store className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-bold font-sans">{shop.shop_name}</h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        {shop.customer_count || 0} Customers · {shop.product_count || 0} Products · {shop.transaction_count || 0} Transactions
                      </p>
                    </div>
                  </div>
                  <Link
                    to={`/shop/${shop.id}`}
                    className="p-2 bg-[#2E2E2E] hover:bg-[#3ECF8E] hover:text-black rounded transition-colors text-white"
                    title="Open Shop Dashboard"
                  >
                    <ArrowRight className="w-5 h-5" />
                  </Link>
                </div>

                {/* Live Pulse Section */}
                <div className="flex-1 bg-[#121212] rounded-md p-4 border border-[#2E2E2E] flex flex-col justify-center">
                  <div className="flex items-center mb-3">
                    <Activity className="w-4 h-4 text-[#3ECF8E] mr-2" />
                    <span className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Live Pulse</span>
                  </div>

                  {totalMessages > 0 ? (
                    <div className="mb-4">
                      <p className="text-sm font-medium mb-2 flex justify-between">
                        <span><span className="text-[#3ECF8E]">▶</span> Active Campaign</span>
                        <span>{stats.sent || 0} / {totalMessages} sent ({sentPct}%)</span>
                      </p>
                      <div className="w-full bg-[#2E2E2E] rounded-full h-2.5 overflow-hidden">
                        <div
                          className="bg-[#3ECF8E] h-2.5 rounded-full transition-all duration-500 relative"
                          style={{ width: `${sentPct}%` }}
                        >
                          <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="mb-4 text-sm text-muted-foreground italic">
                      No active campaigns currently streaming.
                    </div>
                  )}

                  {/* Quick Stats Grid */}
                  <div className="grid grid-cols-3 gap-2 mt-auto pt-4 border-t border-[#2E2E2E]">
                    <div className="flex flex-col">
                      <span className="text-xs text-muted-foreground mb-1">🟢 Campaigns</span>
                      <span className="font-bold">{stats.total_campaigns || 0}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-muted-foreground mb-1">🟡 Active Batches</span>
                      <span className="font-bold">{stats.active_batches || 0}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-muted-foreground mb-1">🔴 Failed</span>
                      <span className="font-bold">{stats.failed || 0}</span>
                    </div>
                  </div>
                </div>

                {/* CSV Status Ribbon */}
                <div className="mt-4 flex gap-2">
                  {['customer_data', 'product_data', 'transaction_data'].map((purpose) => {
                    const status = shop.csv_status?.[purpose];
                    const labels = {
                      customer_data: 'Customers',
                      product_data: 'Products',
                      transaction_data: 'Transactions',
                    };
                    return (
                      <div
                        key={purpose}
                        className={`flex-1 text-center py-1.5 rounded text-xs font-medium border ${
                          status?.uploaded
                            ? 'bg-[#3ECF8E]/10 border-[#3ECF8E]/30 text-[#3ECF8E]'
                            : 'bg-[#121212] border-[#2E2E2E] text-muted-foreground'
                        }`}
                      >
                        {status?.uploaded ? '✓' : '○'} {labels[purpose]}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
