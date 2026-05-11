import React, { useState, useEffect } from 'react';
import { Crown, AlertTriangle, Package, Zap, User, ChevronDown, Check } from 'lucide-react';

const SegmentTemplateSelector = ({ 
  segment, 
  templates, 
  selectedTemplateId, 
  onSelect, 
  customerCount 
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [filteredTemplates, setFilteredTemplates] = useState([]);

  useEffect(() => {
    // Filter templates that match this segment or are available for 'all'
    const filtered = templates.filter(t => 
      t.segment === segment || t.segment === 'all'
    );
    setFilteredTemplates(filtered);
  }, [templates, segment]);

  const getSegmentInfo = () => {
    const segmentMap = {
      'vip': { 
        label: 'VIP Champions', 
        icon: Crown, 
        color: 'text-yellow-400',
        bgColor: 'bg-yellow-400/10',
        borderColor: 'border-yellow-400/30',
        description: 'Retain gold assets'
      },
      'at_risk': { 
        label: 'At-Risk', 
        icon: AlertTriangle, 
        color: 'text-red-400',
        bgColor: 'bg-red-400/10',
        borderColor: 'border-red-400/30',
        description: 'Urgent - prevent churn'
      },
      'potential_bulk': { 
        label: 'Potential (Bulk)', 
        icon: Package, 
        color: 'text-purple-400',
        bgColor: 'bg-purple-400/10',
        borderColor: 'border-purple-400/30',
        description: 'Increase spend per visit'
      },
      'loyal_frequent': { 
        label: 'Loyal (Frequent)', 
        icon: Zap, 
        color: 'text-blue-400',
        bgColor: 'bg-blue-400/10',
        borderColor: 'border-blue-400/30',
        description: 'Reward the habit'
      },
      'boring': { 
        label: 'Boring', 
        icon: User, 
        color: 'text-slate-400',
        bgColor: 'bg-slate-400/10',
        borderColor: 'border-slate-400/30',
        description: 'Low priority baseline'
      }
    };
    return segmentMap[segment] || segmentMap['boring'];
  };

  const segmentInfo = getSegmentInfo();
  const SegmentIcon = segmentInfo.icon;
  const selectedTemplate = filteredTemplates.find(t => t.id === selectedTemplateId);

  return (
    <div className={`bg-[#121212] border ${segmentInfo.borderColor} rounded-lg p-4`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <SegmentIcon className={`w-5 h-5 ${segmentInfo.color}`} />
          <h3 className="font-medium text-sm">{segmentInfo.label}</h3>
        </div>
        <span className={`text-xs ${segmentInfo.bgColor} ${segmentInfo.color} px-2 py-1 rounded font-mono`}>
          {customerCount} customers
        </span>
      </div>

      {/* Template Selector */}
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`w-full flex items-center justify-between bg-[#0C0C0C] border ${
            selectedTemplateId ? segmentInfo.borderColor : 'border-[#2E2E2E]'
          } hover:border-[#3ECF8E] rounded-md px-3 py-2.5 text-sm transition-colors`}
        >
          <span className={selectedTemplate ? 'text-white' : 'text-muted-foreground'}>
            {selectedTemplate ? selectedTemplate.name : '-- Select a template --'}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {/* Dropdown Menu */}
        {isOpen && (
          <>
            {/* Backdrop */}
            <div 
              className="fixed inset-0 z-10" 
              onClick={() => setIsOpen(false)}
            ></div>
            
            {/* Options */}
            <div className="absolute z-20 mt-1 w-full bg-[#0C0C0C] border border-[#2E2E2E] rounded-md shadow-lg max-h-48 overflow-y-auto custom-scrollbar">
              {filteredTemplates.length === 0 ? (
                <div className="p-3 text-sm text-muted-foreground text-center">
                  No templates available for this segment
                </div>
              ) : (
                filteredTemplates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => {
                      onSelect(template.id);
                      setIsOpen(false);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2.5 text-sm hover:bg-[#1C1C1C] transition-colors text-left ${
                      template.id === selectedTemplateId ? 'bg-[#1C1C1C]' : ''
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{template.name}</p>
                      {template.segment && (
                        <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded ${
                          template.segment === 'all' 
                            ? 'bg-slate-400/10 text-slate-400' 
                            : segmentInfo.bgColor + ' ' + segmentInfo.color
                        }`}>
                          {template.segment === 'all' ? 'All Segments' : segmentInfo.label}
                        </span>
                      )}
                    </div>
                    {template.id === selectedTemplateId && (
                      <Check className="w-4 h-4 text-[#3ECF8E] flex-shrink-0 ml-2" />
                    )}
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* Selected Template Preview */}
      {selectedTemplate && (
        <div className="mt-3 pt-3 border-t border-[#2E2E2E]">
          <p className="text-xs text-muted-foreground mb-1.5">Template Preview:</p>
          <div className="bg-[#0C0C0C] border border-[#2E2E2E] rounded-md p-2 text-xs text-muted-foreground max-h-20 overflow-y-auto custom-scrollbar">
            {selectedTemplate.content.length > 150 
              ? selectedTemplate.content.substring(0, 150) + '...' 
              : selectedTemplate.content}
          </div>
        </div>
      )}

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

export default SegmentTemplateSelector;
