import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { customersAPI, templatesAPI, batchesAPI } from '../lib/api';
import { Upload, FileSpreadsheet, Users, Loader, CheckCircle, Plus } from 'lucide-react';
import { toast } from 'sonner';

const CampaignCreatorPage = () => {
  const [step, setStep] = useState(1);
  const [uploadData, setUploadData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  
  const [template, setTemplate] = useState({ name: '', content: '' });
  const [batchConfig, setBatchConfig] = useState({
    batch_size: 100,
    start_time: ''
  });
  const [estimate, setEstimate] = useState(null);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls']
    },
    maxFiles: 1,
    onDrop: async (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        await handleFileUpload(acceptedFiles[0]);
      }
    }
  });

  const handleFileUpload = async (file) => {
    setUploading(true);
    setAnalyzing(true);
    
    try {
      // Simulate analysis phase
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const response = await customersAPI.upload(file);
      setUploadData(response.data);
      setAnalyzing(false);
      toast.success(`Uploaded ${response.data.total_customers} customers`);
      setStep(2);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Upload failed');
      setAnalyzing(false);
    } finally {
      setUploading(false);
    }
  };

  const insertPlaceholder = (placeholder) => {
    const textarea = document.querySelector('[data-testid="template-content"]');
    const cursorPos = textarea.selectionStart;
    const textBefore = template.content.substring(0, cursorPos);
    const textAfter = template.content.substring(cursorPos);
    const newContent = textBefore + `{{${placeholder}}}` + textAfter;
    setTemplate({ ...template, content: newContent });
  };

  const calculateEstimate = async () => {
    if (uploadData && batchConfig.batch_size > 0) {
      try {
        const response = await batchesAPI.estimate(
          uploadData.total_customers,
          batchConfig.batch_size
        );
        setEstimate(response.data);
      } catch (error) {
        console.error('Failed to calculate estimate');
      }
    }
  };

  const handleCreateCampaign = async () => {
    if (!template.name || !template.content) {
      toast.error('Please fill in template name and content');
      return;
    }
    
    if (!batchConfig.start_time) {
      toast.error('Please select start time');
      return;
    }

    try {
      // Create template
      const templateResponse = await templatesAPI.create({
        name: template.name,
        content: template.content,
        placeholders: []
      });

      // Create batches
      const customerIds = uploadData.customers.map(c => c.id);
      await batchesAPI.create({
        template_id: templateResponse.data.id,
        customer_ids: customerIds,
        batch_size: batchConfig.batch_size,
        start_time: new Date(batchConfig.start_time).toISOString(),
        priority: 0
      });

      toast.success('Campaign created successfully!');
      setTimeout(() => {
        window.location.href = '/monitor';
      }, 1500);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create campaign');
    }
  };

  React.useEffect(() => {
    if (uploadData && batchConfig.batch_size > 0) {
      calculateEstimate();
    }
  }, [uploadData, batchConfig.batch_size]);

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Campaign Creator
        </h1>
        <p className="text-muted-foreground">
          Upload customer data, configure batches, and create message templates
        </p>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center gap-4 mb-8">
        <div className={`flex items-center gap-2 ${step >= 1 ? 'text-[#3ECF8E]' : 'text-muted-foreground'}`}>
          <div className="w-8 h-8 rounded-full border-2 flex items-center justify-center">
            {step > 1 ? <CheckCircle className="w-5 h-5" /> : '1'}
          </div>
          <span className="text-sm font-medium">Upload Data</span>
        </div>
        <div className="h-px bg-[#2E2E2E] flex-1"></div>
        <div className={`flex items-center gap-2 ${step >= 2 ? 'text-[#3ECF8E]' : 'text-muted-foreground'}`}>
          <div className="w-8 h-8 rounded-full border-2 flex items-center justify-center">
            {step > 2 ? <CheckCircle className="w-5 h-5" /> : '2'}
          </div>
          <span className="text-sm font-medium">Configure & Template</span>
        </div>
      </div>

      {/* Step 1: File Upload */}
      {step === 1 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-8">
          <h2 className="text-2xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Upload Customer Data
          </h2>
          
          <div
            {...getRootProps()}
            data-testid="file-dropzone"
            className={`border-2 border-dashed rounded-lg p-12 text-center transition-all cursor-pointer
              ${isDragActive ? 'border-[#3ECF8E] bg-[#3ECF8E]/5' : 'border-[#2E2E2E] hover:border-[#3E3E3E]'}
              ${uploading ? 'pointer-events-none opacity-50' : ''}`}
          >
            <input {...getInputProps()} />
            
            {analyzing ? (
              <div className="space-y-4">
                <Loader className="w-12 h-12 mx-auto animate-spin text-[#3ECF8E]" />
                <div>
                  <p className="font-medium">Analyzing customer data...</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Classifying customers by purchase patterns
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <Upload className="w-12 h-12 mx-auto text-muted-foreground" />
                <div>
                  <p className="font-medium">
                    {isDragActive ? 'Drop file here' : 'Drag & drop your file here'}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    or click to browse (CSV, XLSX, XLS)
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 p-4 bg-[#121212] border border-[#2E2E2E] rounded-md">
            <p className="text-sm font-medium mb-2">Required columns in your file:</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• <code className="font-mono">name</code> - Customer name</li>
              <li>• <code className="font-mono">phone</code> - Phone number</li>
              <li>• <code className="font-mono">email</code> (optional)</li>
              <li>• <code className="font-mono">total_quantity</code>, <code className="font-mono">purchase_count</code>, <code className="font-mono">order_value</code> (for classification)</li>
            </ul>
          </div>
        </div>
      )}

      {/* Step 2: Configuration & Template */}
      {step === 2 && uploadData && (
        <div className="space-y-6">
          {/* Classification Summary */}
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6" data-testid="classification-summary">
            <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Classification Summary
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 bg-[#121212] rounded-md">
                <p className="text-sm text-muted-foreground mb-1">Total Customers</p>
                <p className="text-2xl font-semibold font-mono">{uploadData.total_customers}</p>
              </div>
              {Object.entries(uploadData.classifications).map(([category, count]) => (
                <div key={category} className="p-4 bg-[#121212] rounded-md">
                  <p className="text-sm text-muted-foreground mb-1 capitalize">
                    {category.replace('_', ' ')}
                  </p>
                  <p className="text-2xl font-semibold font-mono">{count}</p>
                  {category === 'both' && (
                    <span className="inline-block mt-1 text-xs bg-[#3ECF8E] text-black px-2 py-0.5 rounded">
                      Combined Template
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Batch Configuration */}
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Batch Configuration
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Batch Size</label>
                <input
                  data-testid="batch-size-input"
                  type="number"
                  value={batchConfig.batch_size}
                  onChange={(e) => setBatchConfig({ ...batchConfig, batch_size: parseInt(e.target.value) })}
                  className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
                  min="1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Start Time</label>
                <input
                  data-testid="start-time-input"
                  type="datetime-local"
                  value={batchConfig.start_time}
                  onChange={(e) => setBatchConfig({ ...batchConfig, start_time: e.target.value })}
                  className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
                />
              </div>
            </div>

            {/* Estimate */}
            {estimate && (
              <div className="mt-4 p-4 bg-[#121212] border border-[#2E2E2E] rounded-md" data-testid="split-notifier">
                <p className="text-sm font-medium mb-2">Split Notifier</p>
                <div className="space-y-1 text-sm text-muted-foreground">
                  <p>
                    <span className="font-mono text-[#3ECF8E]">{estimate.total_batches}</span> batches will be created
                  </p>
                  <p>
                    Estimated time to split batches: <span className="font-mono text-[#3ECF8E]">{estimate.split_time_seconds}s</span>
                  </p>
                  <p>
                    Total estimated completion time: <span className="font-mono text-[#3ECF8E]">{estimate.estimated_completion_minutes} mins</span>
                  </p>
                </div>
                <div className="mt-3 h-1 bg-[#2E2E2E] rounded-full overflow-hidden">
                  <div className="h-full bg-[#3ECF8E] w-1/3 animate-pulse"></div>
                </div>
              </div>
            )}
          </div>

          {/* Message Template */}
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Message Template
            </h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Template Name</label>
                <input
                  data-testid="template-name-input"
                  type="text"
                  value={template.name}
                  onChange={(e) => setTemplate({ ...template, name: e.target.value })}
                  placeholder="e.g., Welcome Campaign"
                  className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 px-3 text-sm outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Message Content</label>
                <textarea
                  data-testid="template-content"
                  value={template.content}
                  onChange={(e) => setTemplate({ ...template, content: e.target.value })}
                  placeholder="Hi {{name}}, thanks for your order of {{product_category}}!"
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
                      data-testid={`insert-${placeholder}-btn`}
                      onClick={() => insertPlaceholder(placeholder)}
                      className="px-3 py-1 bg-[#121212] border border-[#2E2E2E] rounded-md text-sm hover:border-[#3ECF8E] transition-colors"
                    >
                      <Plus className="w-3 h-3 inline mr-1" />
                      {placeholder}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button
              data-testid="back-button"
              onClick={() => setStep(1)}
              className="px-6 py-2 bg-[#2E2E2E] text-white border border-[#3E3E3E] hover:bg-[#3E3E3E] rounded-md transition-colors"
            >
              Back
            </button>
            <button
              data-testid="create-campaign-button"
              onClick={handleCreateCampaign}
              className="flex-1 px-6 py-2 bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md shadow-[0_0_10px_rgba(62,207,142,0.2)] transition-all"
            >
              Create Campaign
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default CampaignCreatorPage;
