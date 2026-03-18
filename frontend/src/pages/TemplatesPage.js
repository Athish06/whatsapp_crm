import React, { useState, useEffect } from 'react';
import { templatesAPI } from '../lib/api';
import { Plus, Trash2, FileText, X, Crown, AlertTriangle, Package, Zap, User, Users } from 'lucide-react';
import { toast } from 'sonner';

const TemplatesPage = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTemplate, setNewTemplate] = useState({ name: '', content: '', segment: 'all' });
  const [creating, setCreating] = useState(false);
  const [filterSegment, setFilterSegment] = useState('all');

  // Segment configuration - Hybrid RFM+B Intelligence
  const segments = [
    { value: 'all', label: 'All Customers', icon: Users, color: 'gray' },
    { value: 'vip', label: 'VIP Champions', icon: Crown, color: 'yellow' },
    { value: 'at_risk', label: 'At-Risk', icon: AlertTriangle, color: 'red' },
    { value: 'potential_bulk', label: 'Potential (Bulk)', icon: Package, color: 'purple' },
    { value: 'loyal_frequent', label: 'Loyal (Frequent)', icon: Zap, color: 'blue' },
    { value: 'boring', label: 'Boring', icon: User, color: 'slate' }
  ];

  const getSegmentConfig = (segmentValue) => {
    return segments.find(s => s.value === segmentValue) || segments[0];
  };

  const getSegmentColors = (color) => {
    const colors = {
      gray: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' },
      yellow: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
      red: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
      purple: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
      blue: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
      slate: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/30' }
    };
    return colors[color] || colors.gray;
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await templatesAPI.list();
      setTemplates(response.data.templates);
    } catch (error) {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id, event) => {
    event.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this template?')) return;
    
    try {
      await templatesAPI.delete(id);
      toast.success('Template deleted');
      await loadTemplates();
    } catch (error) {
      toast.error('Failed to delete template');
    }
  };

  const handleCreateTemplate = async () => {
    if (!newTemplate.name || !newTemplate.content) {
      toast.error('Please fill in template name and content');
      return;
    }

    try {
      setCreating(true);
      await templatesAPI.create({
        name: newTemplate.name,
        content: newTemplate.content,
        segment: newTemplate.segment,
        placeholders: []
      });
      toast.success('Template created successfully');
      setNewTemplate({ name: '', content: '', segment: 'all' });
      setShowCreateForm(false);
      await loadTemplates();
    } catch (error) {
      toast.error('Failed to create template');
    } finally {
      setCreating(false);
    }
  };

  const insertPlaceholder = (placeholder) => {
    const textarea = document.querySelector('[data-testid="new-template-content"]');
    if (textarea) {
      const cursorPos = textarea.selectionStart;
      const textBefore = newTemplate.content.substring(0, cursorPos);
      const textAfter = newTemplate.content.substring(cursorPos);
      const newContent = textBefore + `{{${placeholder}}}` + textAfter;
      setNewTemplate({ ...newTemplate, content: newContent });
    } else {
      setNewTemplate({ ...newTemplate, content: newTemplate.content + `{{${placeholder}}}` });
    }
  };

  // Filter templates based on selected segment
  const filteredTemplates = filterSegment === 'all' 
    ? templates 
    : templates.filter(t => t.segment === filterSegment || t.segment === 'all');

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Message Templates
          </h1>
          <p className="text-muted-foreground">
            Manage your WhatsApp message templates
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading templates...</div>
      ) : (
        <div className="space-y-6">
          {/* New Template Form (Modal-like) */}
          {showCreateForm ? (
            <div className="bg-[#1C1C1C] border border-[#3ECF8E] rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
                  Create New Template
                </h2>
                <button
                  onClick={() => {
                    setShowCreateForm(false);
                    setNewTemplate({ name: '', content: '', segment: 'all' });
                  }}
                  className="text-muted-foreground hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Template Name</label>
                  <input
                    type="text"
                    value={newTemplate.name}
                    onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })}
                    placeholder="e.g., Welcome Message"
                    className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Customer Segment</label>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                    {segments.map((segment) => {
                      const Icon = segment.icon;
                      const colors = getSegmentColors(segment.color);
                      const isSelected = newTemplate.segment === segment.value;
                      
                      return (
                        <button
                          key={segment.value}
                          type="button"
                          onClick={() => setNewTemplate({ ...newTemplate, segment: segment.value })}
                          className={`p-3 rounded-lg border-2 transition-all text-left ${
                            isSelected
                              ? `${colors.bg} ${colors.border} ${colors.text}`
                              : 'bg-[#121212] border-[#2E2E2E] hover:border-[#3E3E3E]'
                          }`}
                        >
                          <Icon className={`w-5 h-5 mb-1 ${isSelected ? colors.text : 'text-muted-foreground'}`} />
                          <div className={`text-xs font-medium ${isSelected ? colors.text : 'text-muted-foreground'}`}>
                            {segment.label}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Message Content</label>
                  <textarea
                    data-testid="new-template-content"
                    value={newTemplate.content}
                    onChange={(e) => setNewTemplate({ ...newTemplate, content: e.target.value })}
                    placeholder="Hi {{name}}, thanks for your order!"
                    rows={6}
                    className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md p-3 text-sm outline-none resize-none"
                  />
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">Insert Placeholders</p>
                  <div className="flex flex-wrap gap-2">
                    {['name', 'phone', 'email', 'product_category', 'category'].map((placeholder) => (
                      <button
                        key={placeholder}
                        onClick={() => insertPlaceholder(placeholder)}
                        className="px-3 py-1 bg-[#121212] border border-[#2E2E2E] rounded-md text-sm hover:border-[#3ECF8E] transition-colors"
                      >
                        <Plus className="w-3 h-3 inline mr-1" />
                        {placeholder}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => {
                      setShowCreateForm(false);
                      setNewTemplate({ name: '', content: '', segment: 'all' });
                    }}
                    className="px-6 py-2 bg-[#2E2E2E] text-white border border-[#3E3E3E] hover:bg-[#3E3E3E] rounded-md transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateTemplate}
                    disabled={creating}
                    className="flex-1 px-6 py-2 bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md shadow-[0_0_10px_rgba(62,207,142,0.2)] transition-all disabled:opacity-50"
                  >
                    {creating ? 'Creating...' : 'Create Template'}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            /* New Template Card */
            <div 
              onClick={() => setShowCreateForm(true)}
              className="bg-gradient-to-br from-[#3ECF8E]/10 to-[#3ECF8E]/5 border-2 border-dashed border-[#3ECF8E] rounded-lg p-8 cursor-pointer hover:border-[#3ECF8E] hover:bg-[#3ECF8E]/10 transition-all group"
            >
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-full bg-[#3ECF8E] flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Plus className="w-8 h-8 text-black" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-1">Create New Template</h3>
                  <p className="text-muted-foreground">Add a new message template for your campaigns</p>
                </div>
              </div>
            </div>
          )}

          {/* Existing Templates */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
                Your Templates
              </h2>
              
              {/* Segment Filter */}
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Filter:</span>
                <div className="flex gap-2">
                  {segments.map((segment) => {
                    const Icon = segment.icon;
                    const colors = getSegmentColors(segment.color);
                    const isActive = filterSegment === segment.value;
                    
                    return (
                      <button
                        key={segment.value}
                        onClick={() => setFilterSegment(segment.value)}
                        className={`px-3 py-1.5 rounded-md border transition-all flex items-center gap-1.5 ${
                          isActive
                            ? `${colors.bg} ${colors.border} ${colors.text}`
                            : 'bg-[#121212] border-[#2E2E2E] text-muted-foreground hover:border-[#3E3E3E]'
                        }`}
                        title={segment.label}
                      >
                        <Icon className="w-4 h-4" />
                        <span className="text-xs font-medium hidden sm:inline">{segment.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            
            {filteredTemplates.length === 0 ? (
              <div className="text-center p-12 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg">
                <FileText className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <p className="text-muted-foreground">
                  {templates.length === 0 ? 'No templates yet' : `No templates for ${getSegmentConfig(filterSegment).label}`}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  {templates.length === 0 ? 'Create your first template to get started' : 'Try a different filter'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredTemplates.map((template) => {
                  const segmentConfig = getSegmentConfig(template.segment || 'all');
                  const SegmentIcon = segmentConfig.icon;
                  const colors = getSegmentColors(segmentConfig.color);
                  
                  return (
                    <div
                      key={template.id}
                      data-testid={`template-card-${template.id}`}
                      className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 hover:border-[#3ECF8E] transition-all group relative"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3 flex-1">
                          <div className="w-10 h-10 rounded-lg bg-[#3ECF8E]/10 flex items-center justify-center flex-shrink-0">
                            <FileText className="w-5 h-5 text-[#3ECF8E]" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-semibold truncate">{template.name}</h3>
                            <div className={`inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full border ${colors.bg} ${colors.border} ${colors.text}`}>
                              <SegmentIcon className="w-3 h-3" />
                              <span className="text-xs font-medium">{segmentConfig.label}</span>
                            </div>
                          </div>
                        </div>
                        <button
                          data-testid={`delete-template-${template.id}`}
                          onClick={(e) => handleDelete(template.id, e)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-500/10 rounded-md flex-shrink-0"
                          title="Delete template"
                        >
                          <Trash2 className="w-4 h-4 text-red-400 hover:text-red-300" />
                        </button>
                      </div>
                      <p className="text-sm text-muted-foreground mb-3 line-clamp-3">
                        {template.content}
                      </p>
                      {template.placeholders && template.placeholders.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {template.placeholders.map((ph, idx) => (
                            <span
                              key={idx}
                              className="text-xs bg-[#121212] px-2 py-0.5 rounded border border-[#2E2E2E]"
                            >
                              {ph}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplatesPage;
