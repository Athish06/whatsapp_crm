import React, { useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { customersAPI, templatesAPI, batchesAPI, filesAPI } from '../lib/api';
import { Upload, FileSpreadsheet, Users, Loader, CheckCircle, Plus, File, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '../lib/utils';
import ColumnMappingDialog from '../components/ColumnMappingDialog';
import BatchDistributionPreview from '../components/BatchDistributionPreview';
import SegmentTemplateSelector from '../components/SegmentTemplateSelector';

const CampaignCreatorPage = () => {
  const [view, setView] = useState('fileSelection'); // 'fileSelection', 'uploadNew', 'columnMapping', 'configure'
  const [step, setStep] = useState(1);
  const [uploadData, setUploadData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  
  // Column mapping state
  const [detectedColumns, setDetectedColumns] = useState([]);
  const [columnMapping, setColumnMapping] = useState({});
  const [percentile, setPercentile] = useState(70);
  const [uploadedFile, setUploadedFile] = useState(null); // Temporary file storage for mapping
  
  const [existingFiles, setExistingFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);
  
  const [existingTemplates, setExistingTemplates] = useState([]);
  const [openedFromExistingFile, setOpenedFromExistingFile] = useState(false);
  const [fileScheduleSummary, setFileScheduleSummary] = useState(null);
  const [templateMode, setTemplateMode] = useState('choose');
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [newTemplate, setNewTemplate] = useState({
    name: '',
    content: '',
    segment: 'vip'
  });
  
  // Segment-specific template selections - Hybrid RFM+B Intelligence
  const [segmentTemplates, setSegmentTemplates] = useState({
    vip: '',
    at_risk: '',
    potential_bulk: '',
    loyal_frequent: '',
    boring: ''
  });
  
  const [batchConfig, setBatchConfig] = useState({
    batch_size: 50,  // WhatsApp limit-friendly batch size
    start_time: ''
  });
  const [estimate, setEstimate] = useState(null);

  // Load existing files on mount
  useEffect(() => {
    loadExistingFiles();
    loadExistingTemplates();
  }, []);

  const loadExistingFiles = async () => {
    try {
      setLoadingFiles(true);
      const response = await filesAPI.getMyFiles(0, 50);
      
      // FIX: Deduplicate files by ID to prevent duplicate cards
      const uniqueFiles = [];
      const seenIds = new Set();
      
      for (const file of response.data.files) {
        if (!seenIds.has(file._id)) {
          seenIds.add(file._id);
          uniqueFiles.push(file);
        }
      }
      
      setExistingFiles(uniqueFiles);
    } catch (error) {
      console.error('Failed to load files:', error);
      toast.error('Failed to load existing files');
    } finally {
      setLoadingFiles(false);
    }
  };

  const loadExistingTemplates = async () => {
    try {
      const response = await templatesAPI.list();
      setExistingTemplates(response.data.templates);
    } catch (error) {
      console.error('Failed to load templates:', error);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'text/csv': ['.csv'] },
    multiple: false,
    onDrop: handleFileUpload
  });

  async function handleFileUpload(acceptedFiles) {
    if (acceptedFiles.length === 0) return;

    const file = acceptedFiles[0];
    setUploading(true);

    try {
      // Step 1: Upload to B2 and get file metadata
      const uploadResponse = await filesAPI.upload(file);
      const fileId = uploadResponse.data.file_id;
      
      // Check if file is duplicate
      if (uploadResponse.data.duplicate) {
        setUploading(false);
        
        // Show confirmation dialog
        const userChoice = window.confirm(
          `This file "${uploadResponse.data.file_name}" has already been uploaded.\n\n` +
          `Choose:\n` +
          `- OK: Continue with the existing file and create new campaign\n` +
          `- Cancel: Upload a different file`
        );
        
        if (!userChoice) {
          toast.info('Please upload a different file');
          return;
        }
        
        // User chose to continue with existing file
        toast.info('Using existing file for campaign');
      }
      
      toast.success('File uploaded successfully!');

      // Step 2: Detect columns for mapping
      const columnsResponse = await filesAPI.detectColumns(fileId);
      const detectedCols = columnsResponse.data.columns;
      const suggestedMapping = columnsResponse.data.suggested_mapping || {};
      
      setDetectedColumns(detectedCols);
      setColumnMapping(suggestedMapping);
      setUploadedFile({ file_id: fileId, file_name: uploadResponse.data.file_name });
      setOpenedFromExistingFile(false);
      setFileScheduleSummary(null);
      
      // Step 3: Show column mapping dialog
      setView('columnMapping');
      
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(getErrorMessage(error, 'Failed to upload file'));
    } finally {
      setUploading(false);
    }
  }

  const handleConfirmMapping = async () => {
    if (!uploadedFile) return;

    try {
      setAnalyzing(true);
      toast.info('Processing customer data...');

      // Process customers with column mapping and classification
      const response = await customersAPI.processWithMapping(uploadedFile.file_id, {
        column_mapping: columnMapping,
        percentile: percentile
      });

      setUploadData(response.data);
      setSelectedFile(uploadedFile);
      setOpenedFromExistingFile(false);
      setFileScheduleSummary(null);
      setAnalyzing(false);
      
      // Move to configure view
      setView('configure');
      setStep(2);

      toast.success(`Classified ${response.data.total_customers} customers!`);
    } catch (error) {
      console.error('Processing error:', error);
      toast.error(getErrorMessage(error, 'Failed to process customer data'));
      setAnalyzing(false);
    }
  };

  const handleSelectExistingFile = async (file) => {
    try {
      setAnalyzing(true);
      setSelectedFile(file);
      
      toast.info('Loading customer data...');
      
      // Fetch already-processed customer data from MongoDB
      const customerResponse = await customersAPI.getByFile(file._id);
      
      if (customerResponse.data.total_customers === 0) {
        toast.error('No customer data found for this file. Please re-upload.');
        setAnalyzing(false);
        return;
      }
      
      setUploadData(customerResponse.data);

      try {
        const summaryResponse = await batchesAPI.getFileSummary(file._id);
        setFileScheduleSummary(summaryResponse.data);
      } catch {
        setFileScheduleSummary(null);
      }

      setOpenedFromExistingFile(true);
      setAnalyzing(false);
      
      // Skip to step 2
      setView('configure');
      setStep(2);
      
      toast.success(`Loaded ${customerResponse.data.total_customers} customers`);
    } catch (error) {
      console.error('Error loading file:', error);
      toast.error(getErrorMessage(error, 'Failed to load customer data from file'));
      setAnalyzing(false);
    }
  };

  const handleCreateNewCampaign = () => {
    setView('uploadNew');
    setStep(1);
    setUploadData(null);
    setSelectedFile(null);
    setOpenedFromExistingFile(false);
    setFileScheduleSummary(null);
    setSegmentTemplates({ vip: '', at_risk: '', potential_bulk: '', loyal_frequent: '', boring: '' });
  };

  const handleBackToFiles = () => {
    setView('fileSelection');
    setStep(1);
    setUploadData(null);
    setSelectedFile(null);
    setOpenedFromExistingFile(false);
    setFileScheduleSummary(null);
    setSegmentTemplates({ vip: '', at_risk: '', potential_bulk: '', loyal_frequent: '', boring: '' });
  };

  const handleQuickCreateTemplate = async () => {
    if (!newTemplate.name.trim() || !newTemplate.content.trim()) {
      toast.error('Enter template name and content');
      return;
    }

    try {
      setCreatingTemplate(true);
      const response = await templatesAPI.create({
        name: newTemplate.name.trim(),
        content: newTemplate.content.trim(),
        segment: newTemplate.segment,
      });

      const createdTemplate = response.data;
      await loadExistingTemplates();

      // Auto-assign newly created template for the selected segment
      if (newTemplate.segment !== 'all') {
        setSegmentTemplates((prev) => ({
          ...prev,
          [newTemplate.segment]: createdTemplate.id,
        }));
      }

      setTemplateMode('choose');
      setNewTemplate({ name: '', content: '', segment: 'vip' });
      toast.success('Template created and added to scheduler');
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to create template'));
    } finally {
      setCreatingTemplate(false);
    }
  };

  const handleDeleteFile = async (fileId, fileName, event) => {
    // Prevent card click event
    event.stopPropagation();
    
    // Confirmation dialog
    if (!window.confirm(`Are you sure you want to delete "${fileName}"?\n\nWARNING: This will permanently delete:\n- The file from cloud storage\n- All customer data imported from this file\n\nThis action cannot be undone.`)) {
      return;
    }
    
    try {
      const response = await filesAPI.deleteFile(fileId);
      const deletedCustomers = response?.data?.customers_deleted || 0;
      const deletedSchedules = response?.data?.campaigns_deleted || 0;
      toast.success(`File deleted. Removed ${deletedCustomers} customers and ${deletedSchedules} schedules.`);
      
      // Reload files list
      loadExistingFiles();
    } catch (error) {
      console.error('Error deleting file:', error);
      toast.error(getErrorMessage(error, 'Failed to delete file'));
    }
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
    // Validation: Check that all segments with customers have templates selected
    const segmentsWithCustomers = Object.entries(uploadData.classifications || {})
      .filter(([_, count]) => count > 0)
      .map(([segment, _]) => segment);

    const missingTemplates = segmentsWithCustomers.filter(segment => !segmentTemplates[segment]);

    if (missingTemplates.length > 0) {
      toast.error(`Please select templates for: ${missingTemplates.join(', ')}`);
      return;
    }
    
    if (!batchConfig.start_time) {
      toast.error('Please select start time');
      return;
    }

    try {
      // Create only the segment_templates object with segments that have customers
      const activeSegmentTemplates = {};
      segmentsWithCustomers.forEach(segment => {
        if (segmentTemplates[segment]) {
          activeSegmentTemplates[segment] = segmentTemplates[segment];
        }
      });

      // Create batches with segment-specific templates
      const customerIds = uploadData.customers.map(c => c.id);
      await batchesAPI.create({
        segment_templates: activeSegmentTemplates,  // NEW: Use segment_templates instead of template_id
        customer_ids: customerIds,
        batch_size: batchConfig.batch_size,
        start_time: new Date(batchConfig.start_time).toISOString(),
        file_id: selectedFile?._id || selectedFile?.file_id,
        campaign_name: selectedFile?.original_file_name
          ? `${selectedFile.original_file_name} Schedule ${new Date().toLocaleString()}`
          : undefined,
        priority: 0
      });

      toast.success('Campaign created successfully!');
      setTimeout(() => {
        window.location.href = '/monitor';
      }, 1500);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to create campaign'));
    }
  };

  React.useEffect(() => {
    if (uploadData && batchConfig.batch_size > 0) {
      calculateEstimate();
    }
  }, [uploadData, batchConfig.batch_size]);

  // Show Column Mapping Page (Full Screen)
  if (view === 'columnMapping') {
    return (
      <ColumnMappingDialog
        detectedColumns={detectedColumns}
        columnMapping={columnMapping}
        onColumnMappingChange={setColumnMapping}
        percentile={percentile}
        onPercentileChange={setPercentile}
        onConfirm={handleConfirmMapping}
        onCancel={() => {
          setView('fileSelection');
          setUploadedFile(null);
        }}
        loading={uploading || analyzing}
      />
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Campaign Creator
        </h1>
        <p className="text-muted-foreground">
          {view === 'fileSelection' 
            ? 'Select an existing file or create a new campaign' 
            : 'Upload customer data, configure batches, and assign templates to segments'}
        </p>
      </div>

      {/* Progress Steps - Show only when not in file selection */}
      {view !== 'fileSelection' && (
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
            <span className="text-sm font-medium">Configure Campaign</span>
          </div>
        </div>
      )}

      {/* File Selection View */}
      {view === 'fileSelection' && (
        <div className="space-y-6">
          {/* Create New Campaign Card */}
          <div 
            onClick={handleCreateNewCampaign}
            className="bg-gradient-to-br from-[#3ECF8E]/10 to-[#3ECF8E]/5 border-2 border-dashed border-[#3ECF8E] rounded-lg p-8 cursor-pointer hover:border-[#3ECF8E] hover:bg-[#3ECF8E]/10 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-[#3ECF8E] flex items-center justify-center group-hover:scale-110 transition-transform">
                <Plus className="w-8 h-8 text-black" />
              </div>
              <div>
                <h3 className="text-xl font-semibold mb-1">Create New Campaign</h3>
                <p className="text-muted-foreground">Upload a new CSV file to start a campaign</p>
              </div>
            </div>
          </div>

          {/* Existing Files */}
          <div>
            <h2 className="text-2xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Your Uploaded Files
            </h2>
            
            {loadingFiles ? (
              <div className="flex items-center justify-center p-12 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg">
                <Loader className="w-8 h-8 animate-spin text-[#3ECF8E]" />
              </div>
            ) : existingFiles.length === 0 ? (
              <div className="text-center p-12 bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg">
                <FileSpreadsheet className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <p className="text-muted-foreground">No files uploaded yet</p>
                <p className="text-sm text-muted-foreground mt-1">Upload your first file to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {existingFiles.map((file) => (
                  <div
                    key={file._id}
                    onClick={() => handleSelectExistingFile(file)}
                    className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6 cursor-pointer hover:border-[#3ECF8E] hover:bg-[#1C1C1C]/80 transition-all group relative"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 rounded-lg bg-[#3ECF8E]/10 flex items-center justify-center flex-shrink-0 group-hover:bg-[#3ECF8E]/20 transition-colors">
                        <File className="w-6 h-6 text-[#3ECF8E]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium truncate mb-1" title={file.original_file_name}>
                          {file.original_file_name}
                        </h3>
                        <p className="text-xs text-muted-foreground">
                          {new Date(file.uploaded_at).toLocaleDateString()} • {(file.file_size / 1024).toFixed(2)} KB
                        </p>
                      </div>
                      <button
                        onClick={(e) => handleDeleteFile(file._id, file.original_file_name, e)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-500/10 rounded-md"
                        title="Delete file"
                      >
                        <Trash2 className="w-4 h-4 text-red-400 hover:text-red-300" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 1: File Upload */}
      {view === 'uploadNew' && step === 1 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Upload Customer Data
            </h2>
            <button
              onClick={handleBackToFiles}
              className="text-sm text-muted-foreground hover:text-white transition-colors"
            >
              ← Back to Files
            </button>
          </div>
          
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
                    {isDragActive ? 'Drop file here' : 'Drag & drop your CSV file here'}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    or click to browse (CSV only)
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 p-4 bg-[#121212] border border-[#2E2E2E] rounded-md">
            <p className="text-sm font-medium mb-2">✓ Required columns in your CSV file:</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">name</code> - Customer name</li>
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">phone</code> - Phone number (with country code)</li>
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">email</code> - Email address (optional)</li>
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">total_quantity</code> - Total items purchased</li>
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">purchase_count</code> - Number of purchases</li>
              <li>• <code className="font-mono bg-[#0C0C0C] px-2 py-0.5 rounded">order_value</code> - Total order value</li>
            </ul>
            <p className="text-xs text-muted-foreground mt-3">
              💡 <strong>Note:</strong> The system classifies customers into VIP, At-Risk, Potential (Bulk), Loyal (Frequent), and Boring segments.
            </p>
          </div>
        </div>
      )}

      {/* Step 2: Configuration & Templates */}
      {view === 'configure' && step === 2 && uploadData && (
        <div className="space-y-6">
          {/* Back to Files Button */}
          <button
            onClick={handleBackToFiles}
            className="text-sm text-muted-foreground hover:text-white transition-colors mb-2"
          >
            ← Back to Files
          </button>

          {/* Selected File Info */}
          {selectedFile && (
            <div className="bg-[#1C1C1C] border border-[#3ECF8E]/30 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <File className="w-8 h-8 text-[#3ECF8E]" />
                <div>
                  <p className="font-medium">{selectedFile.file_name || selectedFile.original_file_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Uploaded on {new Date(selectedFile.uploaded_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          )}

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
                    {category.replace(/_/g, ' ')}
                  </p>
                  <p className="text-2xl font-semibold font-mono">{count}</p>
                </div>
              ))}
            </div>
          </div>

          {openedFromExistingFile && fileScheduleSummary && (
            <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    This File Scheduling History
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Reopened file ready. You can create a fresh schedule with new templates.
                  </p>
                </div>
                <button
                  onClick={() => document.getElementById('template-selection-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                  className="px-4 py-2 bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md transition-all"
                >
                  New Schedule
                </button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4">
                <div className="p-3 bg-[#121212] rounded-md">
                  <p className="text-xs text-muted-foreground">Schedules Done</p>
                  <p className="text-lg font-semibold font-mono">{fileScheduleSummary.schedule_count || 0}</p>
                </div>
                <div className="p-3 bg-[#121212] rounded-md">
                  <p className="text-xs text-muted-foreground">Total Batches</p>
                  <p className="text-lg font-semibold font-mono">{fileScheduleSummary.total_batches || 0}</p>
                </div>
                <div className="p-3 bg-[#121212] rounded-md">
                  <p className="text-xs text-muted-foreground">Active</p>
                  <p className="text-lg font-semibold font-mono">{fileScheduleSummary.active_batches || 0}</p>
                </div>
                <div className="p-3 bg-[#121212] rounded-md">
                  <p className="text-xs text-muted-foreground">Messages Sent</p>
                  <p className="text-lg font-semibold font-mono">{fileScheduleSummary.messages_sent || 0}</p>
                </div>
                <div className="p-3 bg-[#121212] rounded-md">
                  <p className="text-xs text-muted-foreground">Failed</p>
                  <p className="text-lg font-semibold font-mono">{fileScheduleSummary.messages_failed || 0}</p>
                </div>
              </div>
            </div>
          )}

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

          {/* NEW: Batch Distribution Preview */}
          <BatchDistributionPreview 
            classifications={uploadData.classifications}
            batchSize={batchConfig.batch_size}
          />

          {/* NEW: Segment Template Selection */}
          <div id="template-selection-section" className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Assign Templates to Segments
            </h2>
            <p className="text-sm text-muted-foreground mb-6">
              Select a template for each customer segment. Templates will be automatically matched to customers based on their classification.
            </p>

            <div className="flex items-center gap-2 mb-4">
              <button
                type="button"
                onClick={() => setTemplateMode('choose')}
                className={`px-3 py-1.5 rounded-md text-sm border ${templateMode === 'choose' ? 'bg-[#3ECF8E] text-black border-[#3ECF8E]' : 'bg-[#121212] text-white border-[#2E2E2E]'}`}
              >
                Choose Existing Templates
              </button>
              <button
                type="button"
                onClick={() => setTemplateMode('create')}
                className={`px-3 py-1.5 rounded-md text-sm border ${templateMode === 'create' ? 'bg-[#3ECF8E] text-black border-[#3ECF8E]' : 'bg-[#121212] text-white border-[#2E2E2E]'}`}
              >
                Create Template Here
              </button>
            </div>

            {templateMode === 'create' && (
              <div className="mb-6 p-4 bg-[#121212] border border-[#2E2E2E] rounded-md space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <input
                    type="text"
                    placeholder="Template name"
                    value={newTemplate.name}
                    onChange={(e) => setNewTemplate((prev) => ({ ...prev, name: e.target.value }))}
                    className="bg-[#0C0C0C] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md px-3 py-2 text-sm outline-none"
                  />
                  <select
                    value={newTemplate.segment}
                    onChange={(e) => setNewTemplate((prev) => ({ ...prev, segment: e.target.value }))}
                    className="bg-[#0C0C0C] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md px-3 py-2 text-sm outline-none"
                  >
                    <option value="all">All segments</option>
                    <option value="vip">VIP</option>
                    <option value="at_risk">At-Risk</option>
                    <option value="potential_bulk">Potential (Bulk)</option>
                    <option value="loyal_frequent">Loyal (Frequent)</option>
                    <option value="boring">Boring</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleQuickCreateTemplate}
                    disabled={creatingTemplate}
                    className="bg-[#3ECF8E] text-black hover:bg-[#34B27B] rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50"
                  >
                    {creatingTemplate ? 'Creating...' : 'Create Template'}
                  </button>
                </div>
                <textarea
                  placeholder="Message content. Example: Hi {{name}}, your monthly stock-up offer is ready."
                  value={newTemplate.content}
                  onChange={(e) => setNewTemplate((prev) => ({ ...prev, content: e.target.value }))}
                  className="w-full min-h-[110px] bg-[#0C0C0C] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-md p-3 text-sm outline-none"
                />
              </div>
            )}
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Show selector only for segments with customers - Hybrid RFM+B Intelligence */}
              {uploadData.classifications.vip > 0 && (
                <SegmentTemplateSelector
                  segment="vip"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.vip}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, vip: id})}
                  customerCount={uploadData.classifications.vip}
                />
              )}
              
              {uploadData.classifications.at_risk > 0 && (
                <SegmentTemplateSelector
                  segment="at_risk"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.at_risk}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, at_risk: id})}
                  customerCount={uploadData.classifications.at_risk}
                />
              )}
              
              {uploadData.classifications.potential_bulk > 0 && (
                <SegmentTemplateSelector
                  segment="potential_bulk"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.potential_bulk}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, potential_bulk: id})}
                  customerCount={uploadData.classifications.potential_bulk}
                />
              )}
              
              {uploadData.classifications.loyal_frequent > 0 && (
                <SegmentTemplateSelector
                  segment="loyal_frequent"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.loyal_frequent}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, loyal_frequent: id})}
                  customerCount={uploadData.classifications.loyal_frequent}
                />
              )}
              
              {uploadData.classifications.boring > 0 && (
                <SegmentTemplateSelector
                  segment="boring"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.boring}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, boring: id})}
                  customerCount={uploadData.classifications.boring}
                />
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <button
              data-testid="back-button"
              onClick={handleBackToFiles}
              className="px-6 py-2 bg-[#2E2E2E] text-white border border-[#3E3E3E] hover:bg-[#3E3E3E] rounded-md transition-colors"
            >
              Back to Files
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
