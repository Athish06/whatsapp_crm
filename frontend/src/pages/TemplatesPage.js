import React, { useState, useEffect } from 'react';
import { templatesAPI } from '../lib/api';
import { Plus, Trash2, FileText } from 'lucide-react';
import { toast } from 'sonner';

const TemplatesPage = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

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

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this template?')) return;
    
    try {
      await templatesAPI.delete(id);
      toast.success('Template deleted');
      await loadTemplates();
    } catch (error) {
      toast.error('Failed to delete template');
    }
  };

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
        <a
          href="/campaign"
          data-testid="create-template-btn"
          className="px-4 py-2 bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md shadow-[0_0_10px_rgba(62,207,142,0.2)] transition-all flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Campaign
        </a>
      </div>

      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading templates...</div>
      ) : templates.length === 0 ? (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-12 text-center">
          <FileText className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <p className="text-muted-foreground">No templates yet. Create a campaign to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((template) => (
            <div
              key={template.id}
              data-testid={`template-card-${template.id}`}
              className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 hover:border-[#3E3E3E] transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold">{template.name}</h3>
                <button
                  data-testid={`delete-template-${template.id}`}
                  onClick={() => handleDelete(template.id)}
                  className="text-muted-foreground hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
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
          ))}
        </div>
      )}
    </div>
  );
};

export default TemplatesPage;
