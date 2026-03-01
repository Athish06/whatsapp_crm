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

  // Optional fields
  const optionalFields = [
    { key: 'purchase_count', label: 'Purchase Count', description: 'Total number of purchases' },
    { key: 'total_spent', label: 'Total Spent', description: 'Total amount spent' },
    { key: 'quantity', label: 'Items per Order', description: 'Average items per order' },
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
              <strong className="text-white">How it works:</strong> Match your file's column names to our system fields.
              Required fields must be mapped. The system will automatically segment customers based on behavior patterns.
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

            {/* Percentile Threshold */}
            <div className="bg-[#2E2E2E] rounded-lg p-6 border border-[#3E3E3E]">
              <h2 className="text-xl font-semibold mb-4">Segmentation Threshold</h2>
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <Label className="text-white font-medium">
                    Percentile: {percentile}%
                  </Label>
                  <span className="text-[#3ECF8E] text-sm font-semibold">
                    {percentile}th percentile
                  </span>
                </div>
                <p className="text-xs text-gray-400">
                  Customers above the {percentile}th percentile will be classified as high-value segments (VIP, Frequent, Bulk).
                </p>
                <div className="space-y-2">
                  <input
                    type="range"
                    min="50"
                    max="95"
                    step="5"
                    value={percentile}
                    onChange={(e) => onPercentileChange(parseInt(e.target.value))}
                    className="w-full h-2 bg-[#1A1A1A] rounded-lg appearance-none cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, #3ECF8E 0%, #3ECF8E ${((percentile - 50) / 45) * 100}%, #1A1A1A ${((percentile - 50) / 45) * 100}%, #1A1A1A 100%)`
                    }}
                  />
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>50% (Lower)</span>
                    <span>95% (Higher)</span>
                  </div>
                </div>
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

            {/* Segmentation Info */}
            <div className="bg-gradient-to-br from-[#3ECF8E]/10 to-[#2E2E3E] rounded-lg p-6 border border-[#3ECF8E]/30">
              <h3 className="text-lg font-semibold mb-3 text-[#3ECF8E]">Customer Segments</h3>
              <div className="space-y-2 text-sm">
                <div className="flex items-start gap-2">
                  <span className="text-[#3ECF8E] font-bold">•</span>
                  <span><strong className="text-white">VIP:</strong> <span className="text-gray-300">High purchase frequency + High bulk orders</span></span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-blue-400 font-bold">•</span>
                  <span><strong className="text-white">Frequent Customers:</strong> <span className="text-gray-300">High purchase frequency</span></span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-purple-400 font-bold">•</span>
                  <span><strong className="text-white">Bulk Buyers:</strong> <span className="text-gray-300">High quantity per order</span></span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-gray-400 font-bold">•</span>
                  <span><strong className="text-white">Regular:</strong> <span className="text-gray-300">Standard customers</span></span>
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

