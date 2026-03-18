import React from 'react';
import { Crown, AlertTriangle, Package, Zap, User, Users } from 'lucide-react';

const BatchDistributionPreview = ({ classifications, batchSize }) => {
  // Calculate batch distribution
  const calculateBatchDistribution = () => {
    if (!classifications || !batchSize || batchSize <= 0) {
      return [];
    }

    // Priority order: VIP → At-Risk → Potential (Bulk) → Loyal (Frequent) → Boring
    const segments = [
      { type: 'vip', count: classifications.vip || 0, label: 'VIP Champions', icon: Crown, color: 'text-yellow-400', description: 'Priority 1' },
      { type: 'at_risk', count: classifications.at_risk || 0, label: 'At-Risk', icon: AlertTriangle, color: 'text-red-400', description: 'Priority 1 (Urgent)' },
      { type: 'potential_bulk', count: classifications.potential_bulk || 0, label: 'Potential (Bulk)', icon: Package, color: 'text-purple-400', description: 'Priority 2' },
      { type: 'loyal_frequent', count: classifications.loyal_frequent || 0, label: 'Loyal (Frequent)', icon: Zap, color: 'text-blue-400', description: 'Priority 3' },
      { type: 'boring', count: classifications.boring || 0, label: 'Boring', icon: User, color: 'text-slate-400', description: 'Priority 4' }
    ];

    const batches = [];
    let currentBatch = { batchNum: 1, segments: [], total: 0 };
    
    segments.forEach(segment => {
      let remaining = segment.count;
      
      while (remaining > 0) {
        const spaceInBatch = batchSize - currentBatch.total;
        
        if (spaceInBatch === 0) {
          // Current batch is full, start a new one
          batches.push(currentBatch);
          currentBatch = { batchNum: batches.length + 1, segments: [], total: 0 };
        }
        
        const toAdd = Math.min(remaining, batchSize - currentBatch.total);
        currentBatch.segments.push({
          ...segment,
          count: toAdd
        });
        currentBatch.total += toAdd;
        remaining -= toAdd;
      }
    });
    
    // Push the last batch if it has any customers
    if (currentBatch.total > 0) {
      batches.push(currentBatch);
    }
    
    return batches;
  };

  const batches = calculateBatchDistribution();
  const totalCustomers = Object.values(classifications || {}).reduce((sum, count) => sum + count, 0);
  const totalBatches = batches.length;

  const getSegmentIcon = (IconComponent, color) => {
    return <IconComponent className={`w-4 h-4 ${color}`} />;
  };

  return (
    <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Batch Distribution Preview
        </h2>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-[#3ECF8E]" />
            <span className="text-muted-foreground">Total: <span className="text-white font-semibold">{totalCustomers}</span></span>
          </div>
          <div className="h-4 w-px bg-[#2E2E2E]"></div>
          <span className="text-muted-foreground">Batches: <span className="text-[#3ECF8E] font-semibold">{totalBatches}</span></span>
        </div>
      </div>

      {batches.length === 0 ? (
        <div className="text-center p-8 text-muted-foreground">
          <p>Set a batch size to see distribution preview</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
          {batches.map((batch) => (
            <div 
              key={batch.batchNum} 
              className="bg-[#121212] border border-[#2E2E2E] rounded-lg p-4 hover:border-[#3ECF8E]/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium text-sm">
                  Batch {batch.batchNum}
                </h3>
                <span className="text-xs bg-[#3ECF8E]/10 text-[#3ECF8E] px-2 py-1 rounded font-mono">
                  {batch.total} customers
                </span>
              </div>
              
              <div className="flex flex-wrap gap-2">
                {batch.segments.map((segment, idx) => (
                  <div 
                    key={idx}
                    className="flex items-center gap-2 bg-[#0C0C0C] border border-[#2E2E2E] rounded-md px-3 py-1.5 text-xs"
                  >
                    {getSegmentIcon(segment.icon, segment.color)}
                    <span className="text-muted-foreground">{segment.label}:</span>
                    <span className="text-white font-semibold font-mono">{segment.count}</span>
                  </div>
                ))}
              </div>
              
              {/* Progress Bar */}
              <div className="mt-3 h-1.5 bg-[#0C0C0C] rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-[#3ECF8E] to-[#34B27B] rounded-full transition-all"
                  style={{ width: `${(batch.total / batchSize) * 100}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="mt-4 pt-4 border-t border-[#2E2E2E]">
        <p className="text-xs text-muted-foreground mb-2">RFM Segmentation Priority:</p>
        <div className="flex flex-wrap gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Crown className="w-3 h-3 text-emerald-400" />
            <span className="text-muted-foreground">VIP Champions (1st) - RFM 12-15</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Zap className="w-3 h-3 text-blue-400" />
            <span className="text-muted-foreground">Loyal (2nd) - RFM 8-11</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Package className="w-3 h-3 text-purple-400" />
            <span className="text-muted-foreground">Potential (3rd) - RFM 5-7</span>
          </div>
          <div className="flex items-center gap-1.5">
            <User className="w-3 h-3 text-slate-400" />
            <span className="text-muted-foreground">At-Risk (4th) - RFM 3-4</span>
          </div>
        </div>
      </div>

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: #0C0C0C;
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #3ECF8E;
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #34B27B;
        }
      `}</style>
    </div>
  );
};

export default BatchDistributionPreview;
