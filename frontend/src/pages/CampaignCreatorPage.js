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
  
  // Segment-specific template selections (NEW: per-segment template mapping)
  const [segmentTemplates, setSegmentTemplates] = useState({
    both: '',
    bulk_buyer: '',
    frequent_customer: '',
    regular: ''
  });
  
  const [batchConfig, setBatchConfig] = useState({
    batch_size: 100,
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
      
      toast.success('File uploaded successfully!');

      // Step 2: Detect columns for mapping
      const columnsResponse = await filesAPI.detectColumns(fileId);
      const detectedCols = columnsResponse.data.columns;
      const suggestedMapping = columnsResponse.data.suggested_mapping || {};
      
      setDetectedColumns(detectedCols);
      setColumnMapping(suggestedMapping);
      setUploadedFile({ file_id: fileId, file_name: uploadResponse.data.file_name });
      
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
    setSegmentTemplates({ both: '', bulk_buyer: '', frequent_customer: '', regular: '' });
  };

  const handleBackToFiles = () => {
    setView('fileSelection');
    setStep(1);
    setUploadData(null);
    setSelectedFile(null);
    setSegmentTemplates({ both: '', bulk_buyer: '', frequent_customer: '', regular: '' });
  };

  const handleDeleteFile = async (fileId, fileName, event) => {
    // Prevent card click event
    event.stopPropagation();
    
    // Confirmation dialog
    if (!window.confirm(`Are you sure you want to delete "${fileName}"?\n\nThis will remove the file from cloud storage. Customer data will remain in the database.`)) {
      return;
    }
    
    try {
      await filesAPI.deleteFile(fileId);
      toast.success('File deleted successfully');
      
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
              💡 <strong>Note:</strong> The system will automatically classify customers as Bulk Buyers, Frequent Customers, or Both based on these metrics.
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
                    {category === 'both' ? 'VIP' : category.replace('_', ' ')}
                  </p>
                  <p className="text-2xl font-semibold font-mono">{count}</p>
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

          {/* NEW: Batch Distribution Preview */}
          <BatchDistributionPreview 
            classifications={uploadData.classifications}
            batchSize={batchConfig.batch_size}
          />

          {/* NEW: Segment Template Selection */}
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Assign Templates to Segments
            </h2>
            <p className="text-sm text-muted-foreground mb-6">
              Select a template for each customer segment. Templates will be automatically matched to customers based on their classification.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Show selector only for segments with customers */}
              {uploadData.classifications.both > 0 && (
                <SegmentTemplateSelector
                  segment="both"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.both}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, both: id})}
                  customerCount={uploadData.classifications.both}
                />
              )}
              
              {uploadData.classifications.frequent_customer > 0 && (
                <SegmentTemplateSelector
                  segment="frequent_customer"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.frequent_customer}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, frequent_customer: id})}
                  customerCount={uploadData.classifications.frequent_customer}
                />
              )}
              
              {uploadData.classifications.bulk_buyer > 0 && (
                <SegmentTemplateSelector
                  segment="bulk_buyer"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.bulk_buyer}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, bulk_buyer: id})}
                  customerCount={uploadData.classifications.bulk_buyer}
                />
              )}
              
              {uploadData.classifications.regular > 0 && (
                <SegmentTemplateSelector
                  segment="regular"
                  templates={existingTemplates}
                  selectedTemplateId={segmentTemplates.regular}
                  onSelect={(id) => setSegmentTemplates({...segmentTemplates, regular: id})}
                  customerCount={uploadData.classifications.regular}
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
