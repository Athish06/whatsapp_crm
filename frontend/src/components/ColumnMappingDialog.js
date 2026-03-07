import React from 'react';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { ArrowRight, CheckCircle2, AlertCircle, Info } from 'lucide-react';

const ColumnMappingDialog = ({
  detectedColumns,
  columnMapping,
  onColumnMappingChange,
  percentile,
  onPercentileChange,
  onConfirm,
  onCancel,
  loading
}) => {
  // Required fields
  const requiredFields = [
    { key: 'name', label: 'Customer Name', description: 'Full name of the customer' },
    { key: 'phone', label: 'Phone Number', description: 'Contact number (with country code)' },
  ];

  // Optional fields (for RFM segmentation)
  const optionalFields = [
    { key: 'purchase_count', label: 'Purchase Count (Frequency)', description: 'Total number of purchases/orders - used for RFM Frequency score' },
    { key: 'total_spent', label: 'Total Spent (Monetary)', description: 'Total amount spent - used for RFM Monetary score' },
    { key: 'last_transaction_date', label: 'Last Transaction Date (Recency)', description: 'Date of last purchase (YYYY-MM-DD) - used for RFM Recency score' },
    { key: 'quantity', label: 'Total Items Quantity', description: 'Total items ordered (optional)' },
    { key: 'email', label: 'Email', description: 'Email address (optional)' },
  ];

  const isRequiredFieldMapped = (fieldKey) => {
    return columnMapping[fieldKey] && columnMapping[fieldKey] !== '' && columnMapping[fieldKey] !== 'none';
  };

  const allRequiredFieldsMapped = requiredFields.every(field => isRequiredFieldMapped(field.key));

  const handleMappingChange = (fieldKey, columnValue) => {
    onColumnMappingChange({
      ...columnMapping,
      [fieldKey]: columnValue === 'none' ? '' : columnValue
    });
  };

  return (
    <div className="min-h-screen bg-[#1A1A1A] text-white p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">Column Mapping</h1>
            {allRequiredFieldsMapped ? (
              <CheckCircle2 className="h-7 w-7 text-[#3ECF8E]" />
            ) : (
              <AlertCircle className="h-7 w-7 text-amber-500" />
            )}
          </div>
          <p className="text-gray-400">
            Map your CSV columns to our system fields. We detected <span className="text-[#3ECF8E] font-semibold">{detectedColumns.length} columns</span> in your file.
          </p>
        </div>

        {/* Info Banner */}
        <div className="bg-[#2E2E3E] border border-[#3ECF8E]/30 rounded-lg p-4 mb-8 flex gap-3">
          <Info className="h-5 w-5 text-[#3ECF8E] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-gray-300">
              <strong className="text-white">RFM Segmentation:</strong> Match your file's column names to our system fields.
              Required fields are mandatory. Optional RFM fields (Recency, Frequency, Monetary) enable advanced AI-powered customer segmentation with log transformation and z-score scaling.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Required Fields */}
          <div className="space-y-6">
            <div className="bg-[#2E2E2E] rounded-lg p-6 border border-[#3E3E3E]">
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                Required Fields
                <span className="text-red-400 text-sm">*</span>
              </h2>
              <div className="space-y-5">
                {requiredFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <Label className="text-white font-medium flex items-center gap-2">
                      {field.label}
                      <span className="text-red-400">*</span>
                      {isRequiredFieldMapped(field.key) && (
                        <CheckCircle2 className="h-4 w-4 text-[#3ECF8E]" />
                      )}
                    </Label>
                    <p className="text-xs text-gray-400">{field.description}</p>
                    <select
                      value={columnMapping[field.key] || 'none'}
                      onChange={(e) => handleMappingChange(field.key, e.target.value)}
                      className={`w-full px-4 py-3 bg-[#1A1A1A] border rounded-lg text-white focus:outline-none focus:ring-2 transition-all ${
                        !isRequiredFieldMapped(field.key)
                          ? 'border-red-400 focus:ring-red-400/50'
                          : 'border-[#3ECF8E] focus:ring-[#3ECF8E]/50'
                      }`}
                    >
                      <option value="none" className="bg-[#2E2E2E]">-- Select Column --</option>
                      {detectedColumns.map((col) => (
                        <option key={col} value={col} className="bg-[#2E2E2E]">
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* RFM Segmentation Threshold (Hidden/Deprecated) */}
            <div className="bg-[#2E2E2E] rounded-lg p-6 border border-[#3E3E3E] opacity-50">
              <h2 className="text-xl font-semibold mb-2">Segmentation Method</h2>
              <div className="bg-gradient-to-r from-[#3ECF8E]/20 to-transparent rounded-lg p-4 border border-[#3ECF8E]/30">
                <p className="text-sm text-[#3ECF8E] font-semibold mb-1">✨ Hybrid RFM Segmentation</p>
                <p className="text-xs text-gray-400">
                  Uses Log Transformation + Z-Score Scaling + Quintile Scoring to automatically segment customers into 4 tiers (VIP, Loyal, Potential, At-Risk) based on Recency, Frequency, and Monetary values.
                </p>
              </div>
            </div>
          </div>

          {/* Right Column - Optional Fields */}
          <div className="space-y-6">
            <div className="bg-[#2E2E2E] rounded-lg p-6 border border-[#3E3E3E]">
              <h2 className="text-xl font-semibold mb-4">Optional Fields</h2>
              <p className="text-xs text-gray-400 mb-4">
                Enable advanced segmentation based on purchase behavior patterns.
              </p>
              <div className="space-y-5">
                {optionalFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <Label className="text-white font-medium flex items-center gap-2">
                      {field.label}
                      {columnMapping[field.key] && columnMapping[field.key] !== 'none' && (
                        <CheckCircle2 className="h-4 w-4 text-[#3ECF8E]" />
                      )}
                    </Label>
                    <p className="text-xs text-gray-400">{field.description}</p>
                    <select
                      value={columnMapping[field.key] || 'none'}
                      onChange={(e) => handleMappingChange(field.key, e.target.value)}
                      className="w-full px-4 py-3 bg-[#1A1A1A] border border-[#3E3E3E] rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-[#3ECF8E]/50 focus:border-[#3ECF8E] transition-all"
                    >
                      <option value="none" className="bg-[#2E2E2E]">-- Not Mapped --</option>
                      {detectedColumns.map((col) => (
                        <option key={col} value={col} className="bg-[#2E2E2E]">
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* RFM Segmentation Info */}
            <div className="bg-gradient-to-br from-[#3ECF8E]/10 to-[#2E2E3E] rounded-lg p-6 border border-[#3ECF8E]/30">
              <h3 className="text-lg font-semibold mb-3 text-[#3ECF8E]">RFM Customer Segments</h3>
              <p className="text-xs text-gray-400 mb-4">AI-powered segmentation based on RFM scores (3-15 range)</p>
              <div className="space-y-3 text-sm">
                <div className="flex items-start gap-3 p-2 bg-[#3ECF8E]/10 rounded-lg">
                  <span className="text-[#3ECF8E] font-bold text-lg">★</span>
                  <div>
                    <span className="block"><strong className="text-[#3ECF8E]">VIP Champions (12-15):</strong></span>
                    <span className="text-gray-300 text-xs">High recency + frequency + monetary - Top tier customers</span>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-2 bg-blue-500/10 rounded-lg">
                  <span className="text-blue-400 font-bold text-lg">◆</span>
                  <div>
                    <span className="block"><strong className="text-blue-400">Loyal Customers (8-11):</strong></span>
                    <span className="text-gray-300 text-xs">Frequent buyers with good engagement</span>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-2 bg-purple-500/10 rounded-lg">
                  <span className="text-purple-400 font-bold text-lg">▲</span>
                  <div>
                    <span className="block"><strong className="text-purple-400">Potential Growth (5-7):</strong></span>
                    <span className="text-gray-300 text-xs">Developing customers with growth potential</span>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-2 bg-gray-500/10 rounded-lg">
                  <span className="text-gray-400 font-bold text-lg">○</span>
                  <div>
                    <span className="block"><strong className="text-gray-300">At-Risk Regular (3-4):</strong></span>
                    <span className="text-gray-400 text-xs">Re-engagement recommended</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4 mt-8">
          <Button
            onClick={onCancel}
            disabled={loading}
            className="px-8 py-6 bg-[#2E2E2E] text-white border border-[#3E3E3E] hover:bg-[#3E3E3E] rounded-lg transition-colors text-base"
          >
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={!allRequiredFieldsMapped || loading}
            className="flex-1 px-8 py-6 bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-semibold rounded-lg shadow-[0_0_20px_rgba(62,207,142,0.3)] transition-all text-base disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              'Processing...'
            ) : (
              <>
                Confirm & Process Customers
                <ArrowRight className="h-5 w-5" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ColumnMappingDialog;

