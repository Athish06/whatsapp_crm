import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Users, Tag, Send, Activity, Settings, ArrowLeft, MessageCircle, Calendar, Hash } from 'lucide-react';
import { toast } from 'sonner';
import { shopsAPI, templatesAPI, customersAPI, batchesAPI } from '../lib/api';

/* WhatsApp-style Bubble */
const WhatsAppBubble = ({ message, segment, color }) => (
  <div className="mb-4">
    <div className="flex items-center gap-2 mb-1">
      <span className="text-xs font-semibold uppercase tracking-wider" style={{ color }}>{segment}</span>
    </div>
    <div className="relative bg-[#005C4B] text-white text-sm px-4 py-3 rounded-xl rounded-tl-sm max-w-sm shadow-lg" style={{ whiteSpace: 'pre-wrap' }}>
      {message}
      <div className="text-[10px] text-white/50 text-right mt-1">Preview ✓✓</div>
      {/* tail */}
      <div className="absolute top-0 -left-2 w-0 h-0 border-t-[10px] border-t-[#005C4B] border-l-[10px] border-l-transparent" />
    </div>
  </div>
);

const CampaignCreatorPage = () => {
  const { shopId } = useParams();
  const navigate = useNavigate();

  const [step, setStep] = useState(1);
  const [campaignName, setCampaignName] = useState('');

  // Template strategy
  const [templateStrategy, setTemplateStrategy] = useState('ai');
  const [fixedProduct, setFixedProduct] = useState('');

  // Real data
  const [shop, setShop] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [segmentCounts, setSegmentCounts] = useState({});
  const [loading, setLoading] = useState(true);

  // Segment → Template mapping
  const segmentKeys = ['vip', 'at_risk', 'potential_bulk', 'loyal_frequent', 'boring'];
  const [segmentTemplates, setSegmentTemplates] = useState({
    vip: '', at_risk: '', potential_bulk: '', loyal_frequent: '', boring: ''
  });

  // Scheduling
  const [scheduledTime, setScheduledTime] = useState('');
  const [batchSize, setBatchSize] = useState(100);
  const [launching, setLaunching] = useState(false);

  // Load real data
  useEffect(() => {
    const loadData = async () => {
      try {
        const [shopRes, templatesRes, customersRes] = await Promise.all([
          shopsAPI.getDetail(shopId),
          templatesAPI.list(shopId),
          customersAPI.list(shopId),
        ]);
        setShop(shopRes.data);
        setTemplates(templatesRes.data.templates || []);

        const custs = customersRes.data.customers || [];
        setCustomers(custs);

        // Calculate segment counts
        const counts = {};
        custs.forEach(c => {
          const seg = c.segment || c.category || 'boring';
          counts[seg] = (counts[seg] || 0) + 1;
        });
        setSegmentCounts(counts);
      } catch (err) {
        console.error('Failed to load campaign data:', err);
        toast.error('Failed to load shop data');
      } finally {
        setLoading(false);
      }
    };
    if (shopId) loadData();
  }, [shopId]);

  // Hydration preview: pick a sample customer per segment and fill in the template
  const getHydrationPreviews = () => {
    const previews = [];
    const previewSegments = [
      { key: 'vip', label: 'VIP Champion', color: '#3ECF8E' },
      { key: 'at_risk', label: 'At-Risk', color: '#EF4444' },
      { key: 'loyal_frequent', label: 'Loyal (Frequent)', color: '#3B82F6' },
      { key: 'boring', label: 'Boring / New', color: '#6B7280' },
    ];

    for (const seg of previewSegments) {
      const templateId = segmentTemplates[seg.key];
      const template = templates.find(t => t.id === templateId);
      if (!template) continue;

      const sampleCustomer = customers.find(c => (c.segment || c.category || 'boring') === seg.key);
      if (!sampleCustomer) continue;

      let msg = template.content;
      // Replace known placeholders
      msg = msg.replace(/\{\{name\}\}/gi, sampleCustomer.name || 'Customer');
      msg = msg.replace(/\{\{phone\}\}/gi, sampleCustomer.phone || '');
      msg = msg.replace(/\{\{email\}\}/gi, sampleCustomer.email || '');
      msg = msg.replace(/\{\{category\}\}/gi, sampleCustomer.top_category || '');
      msg = msg.replace(/\{\{product_category\}\}/gi, sampleCustomer.top_category || '');

      if (templateStrategy === 'fixed' && fixedProduct) {
        msg = msg.replace(/\{\{fixed_product\}\}/gi, fixedProduct);
        msg = msg.replace(/\{\{offer_product_1\}\}/gi, fixedProduct);
        msg = msg.replace(/\{\{favorite_item\}\}/gi, fixedProduct);
      } else {
        msg = msg.replace(/\{\{offer_product_1\}\}/gi, '[AI: their favorite item]');
        msg = msg.replace(/\{\{favorite_item\}\}/gi, '[AI: their favorite item]');
        msg = msg.replace(/\{\{fixed_product\}\}/gi, '[your offer]');
      }

      previews.push({ segment: seg.label, color: seg.color, message: msg });
    }
    return previews;
  };

  const handleNext = () => {
    if (step === 1 && !campaignName.trim()) {
      toast.error('Please enter a campaign name');
      return;
    }
    setStep(prev => Math.min(prev + 1, 4));
  };

  const handleLaunch = async () => {
    // Validate
    const mappedSegments = Object.entries(segmentTemplates).filter(([_, v]) => v);
    if (mappedSegments.length === 0) {
      toast.error('Map at least one segment to a template');
      return;
    }
    if (!scheduledTime) {
      toast.error('Select a schedule date/time');
      return;
    }

    // Collect customer IDs for mapped segments only
    const mappedKeys = mappedSegments.map(([k]) => k);
    const targetCustomerIds = customers
      .filter(c => mappedKeys.includes(c.segment || c.category || 'boring'))
      .map(c => c.id);

    if (targetCustomerIds.length === 0) {
      toast.error('No customers in selected segments');
      return;
    }

    setLaunching(true);
    try {
      const segTemplatesObj = {};
      for (const [seg, tId] of mappedSegments) {
        segTemplatesObj[seg] = tId;
      }

      await batchesAPI.create({
        shop_id: shopId,
        campaign_name: campaignName,
        customer_ids: targetCustomerIds,
        batch_size: batchSize,
        start_time: new Date(scheduledTime).toISOString(),
        priority: 0,
        segment_templates: segTemplatesObj,
        ai_mode: templateStrategy === 'ai',
        fixed_product: templateStrategy === 'fixed' ? fixedProduct : null,
      });

      toast.success('Campaign launched successfully!');
      navigate(`/shop/${shopId}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to launch campaign');
    } finally {
      setLaunching(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground animate-pulse text-lg">Loading campaign data…</div>
      </div>
    );
  }

  const totalCustomers = Object.values(segmentCounts).reduce((a, b) => a + b, 0);

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center space-x-2 text-muted-foreground mb-2 text-sm">
          <Link to={`/shop/${shopId}`} className="hover:text-white transition-colors flex items-center gap-1">
            <ArrowLeft className="w-3 h-3" /> {shop?.shop_name || 'Shop'}
          </Link>
          <span>/</span>
          <span className="text-white">New Campaign</span>
        </div>
        <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
          Create New Campaign
        </h1>
        <p className="text-muted-foreground">
          {shop?.shop_name} · {totalCustomers} customers segmented
        </p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {['Details', 'Templates', 'Preview', 'Schedule'].map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <button
              onClick={() => { if (i + 1 < step) setStep(i + 1); }}
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                step === i + 1
                  ? 'bg-[#3ECF8E] text-black'
                  : step > i + 1
                  ? 'bg-[#3ECF8E]/30 text-[#3ECF8E]'
                  : 'bg-[#2E2E2E] text-muted-foreground'
              }`}
            >
              {i + 1}
            </button>
            <span className={`text-sm ${step === i + 1 ? 'text-white font-medium' : 'text-muted-foreground'}`}>{label}</span>
            {i < 3 && <div className="w-8 h-px bg-[#2E2E2E]" />}
          </div>
        ))}
      </div>

      {/* Step 1: Campaign Name */}
      {step === 1 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>Campaign Details</h2>
          <label className="block text-sm font-medium text-muted-foreground mb-1">Campaign Name</label>
          <input
            type="text"
            value={campaignName}
            onChange={(e) => setCampaignName(e.target.value)}
            placeholder="e.g., Pongal 2026 Special"
            className="w-full bg-[#121212] border border-[#2E2E2E] rounded-md px-3 py-2 text-white focus:outline-none focus:border-[#3ECF8E] mb-6"
            autoFocus
          />

          {/* Audience Overview */}
          <div className="bg-[#121212] border border-[#2E2E2E] rounded-md p-4 mb-6">
            <div className="flex items-center mb-3 text-[#3B82F6]">
              <Users className="w-5 h-5 mr-2" />
              <span className="font-semibold">Audience ({totalCustomers} customers)</span>
            </div>
            <div className="space-y-2 text-sm">
              {segmentKeys.map(seg => (
                <div key={seg} className="flex justify-between">
                  <span className="text-muted-foreground capitalize">{seg.replace('_', ' ')}</span>
                  <span className="text-white font-medium">{segmentCounts[seg] || 0}</span>
                </div>
              ))}
            </div>
          </div>

          <button onClick={handleNext} className="px-6 py-2 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors">
            Continue to Templates
          </button>
        </div>
      )}

      {/* Step 2: Template Strategy + Mapping */}
      {step === 2 && (
        <div className="space-y-6">
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
            <div className="flex items-center mb-6">
              <Settings className="w-5 h-5 text-[#3ECF8E] mr-2" />
              <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>Template Strategy</h2>
            </div>

            {/* Toggle */}
            <div className="flex items-center bg-[#121212] p-1.5 rounded-lg mb-6 w-fit border border-[#2E2E2E]">
              <button
                type="button"
                onClick={() => setTemplateStrategy('ai')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${templateStrategy === 'ai' ? 'bg-[#3ECF8E] text-black shadow-sm' : 'text-muted-foreground hover:text-white'}`}
              >
                AI Selection (Behavioral Map)
              </button>
              <button
                type="button"
                onClick={() => setTemplateStrategy('fixed')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${templateStrategy === 'fixed' ? 'bg-[#3B82F6] text-white shadow-sm' : 'text-muted-foreground hover:text-white'}`}
              >
                Fixed Product
              </button>
            </div>

            <div className="bg-[#121212] border border-[#2E2E2E] p-5 rounded-md mb-6">
              {templateStrategy === 'ai' ? (
                <div>
                  <h4 className="font-medium text-[#3ECF8E] mb-2">Automated Product Matching</h4>
                  <p className="text-sm text-muted-foreground">
                    The system will pick each customer's favorite item from their purchase history. Uses <code className="text-[#3ECF8E]">{'{{offer_product_1}}'}</code> and <code className="text-[#3ECF8E]">{'{{favorite_item}}'}</code> placeholders.
                  </p>
                </div>
              ) : (
                <div>
                  <h4 className="font-medium text-[#3B82F6] mb-2">Fixed Product Campaign</h4>
                  <p className="text-sm text-muted-foreground mb-3">
                    Type a specific product or kit for the <code className="text-[#3B82F6]">{'{{fixed_product}}'}</code> placeholder.
                  </p>
                  <input
                    type="text"
                    value={fixedProduct}
                    onChange={(e) => setFixedProduct(e.target.value)}
                    placeholder="e.g., Special Pongal Kit"
                    className="w-full bg-[#1C1C1C] border border-[#2E2E2E] rounded-md px-3 py-2 text-white focus:outline-none focus:border-[#3B82F6]"
                  />
                </div>
              )}
            </div>

            {/* Segment → Template Mapping */}
            <div className="space-y-3">
              <h4 className="font-medium">Map Templates to Segments</h4>
              {templates.length === 0 ? (
                <div className="bg-[#121212] border border-[#2E2E2E] p-4 rounded-md text-sm text-muted-foreground text-center">
                  No templates found. <Link to="/templates" className="text-[#3ECF8E] hover:underline">Create templates first.</Link>
                </div>
              ) : (
                segmentKeys.map((segment) => (
                  <div key={segment} className="flex items-center justify-between bg-[#121212] p-3 border border-[#2E2E2E] rounded-md">
                    <div className="w-1/3">
                      <span className="capitalize text-sm font-medium">{segment.replace('_', ' ')}</span>
                      <span className="text-xs text-muted-foreground ml-2">({segmentCounts[segment] || 0})</span>
                    </div>
                    <select
                      value={segmentTemplates[segment]}
                      onChange={(e) => setSegmentTemplates({ ...segmentTemplates, [segment]: e.target.value })}
                      className="w-2/3 bg-[#1C1C1C] border border-[#2E2E2E] rounded-md px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#3ECF8E]"
                    >
                      <option value="">— Skip this segment —</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>{t.name} ({t.segment || 'all'})</option>
                      ))}
                    </select>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-between items-center pt-6 border-t border-[#2E2E2E] mt-6">
              <button onClick={() => setStep(1)} className="px-4 py-2 text-muted-foreground hover:text-white transition-colors">Back</button>
              <button onClick={handleNext} className="px-6 py-2 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors">
                Preview Messages
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Hydration Preview */}
      {step === 3 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <div className="flex items-center mb-6">
            <MessageCircle className="w-5 h-5 text-[#3ECF8E] mr-2" />
            <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>Message Preview</h2>
            <span className="ml-3 text-xs bg-[#3ECF8E]/15 text-[#3ECF8E] px-2 py-1 rounded-full border border-[#3ECF8E]/30">WhatsApp Style</span>
          </div>

          <p className="text-sm text-muted-foreground mb-6">
            Below is how your messages will look for a sample customer from each segment. Placeholders are hydrated with real data.
          </p>

          {/* WhatsApp preview background */}
          <div className="bg-[#0B141A] rounded-xl p-6 border border-[#2E2E2E]" style={{
            backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'200\' height=\'200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cdefs%3E%3Cpattern id=\'a\' patternUnits=\'userSpaceOnUse\' width=\'40\' height=\'40\'%3E%3Cpath d=\'M0 38.59l2.83-2.83 1.41 1.41L1.41 40H0v-1.41zm0-2.83V34.34l6.36-6.36 1.41 1.41L1.41 36.76 0 35.35zM40 2.83V0h-1.41l-2.83 2.83 1.41 1.41L40 1.41v1.41zM40 0v.59L38.59 2l-1.41-1.41L40 0z\' fill=\'%231a2c38\' fill-opacity=\'0.3\'/%3E%3C/pattern%3E%3C/defs%3E%3Crect width=\'200\' height=\'200\' fill=\'url(%23a)\'/%3E%3C/svg%3E")',
          }}>
            {getHydrationPreviews().length > 0 ? (
              getHydrationPreviews().map((p, i) => (
                <WhatsAppBubble key={i} message={p.message} segment={p.segment} color={p.color} />
              ))
            ) : (
              <p className="text-center text-muted-foreground py-8 text-sm">
                No previews available. Map at least one segment to a template and ensure customers exist in that segment.
              </p>
            )}
          </div>

          <div className="flex justify-between items-center pt-6 border-t border-[#2E2E2E] mt-6">
            <button onClick={() => setStep(2)} className="px-4 py-2 text-muted-foreground hover:text-white transition-colors">Back</button>
            <button onClick={handleNext} className="px-6 py-2 bg-[#3ECF8E] text-black font-medium rounded-md hover:bg-[#32B37A] transition-colors">
              Schedule & Launch
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Schedule & Launch */}
      {step === 4 && (
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-6">
          <div className="flex items-center mb-6">
            <Calendar className="w-5 h-5 text-[#3ECF8E] mr-2" />
            <h2 className="text-xl font-semibold" style={{ fontFamily: 'Chivo, sans-serif' }}>Schedule & Launch</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-2">Schedule Date & Time</label>
              <input
                type="datetime-local"
                value={scheduledTime}
                onChange={(e) => setScheduledTime(e.target.value)}
                className="w-full bg-[#121212] border border-[#2E2E2E] rounded-md px-3 py-2 text-white focus:outline-none focus:border-[#3ECF8E]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-2">
                <Hash className="w-4 h-4 inline mr-1" />Batch Size
              </label>
              <input
                type="number"
                value={batchSize}
                onChange={(e) => setBatchSize(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
                max={1000}
                className="w-full bg-[#121212] border border-[#2E2E2E] rounded-md px-3 py-2 text-white focus:outline-none focus:border-[#3ECF8E]"
              />
              <p className="text-xs text-muted-foreground mt-1">Messages per batch. Smaller = safer throttling.</p>
            </div>
          </div>

          {/* ── Train Station Launch Summary ── */}
          {(() => {
            const SEGMENT_PRIORITY = {
              vip: { label: 'VIP Champions', color: '#F59E0B', priority: 1 },
              at_risk: { label: 'At-Risk', color: '#EF4444', priority: 2 },
              potential_bulk: { label: 'Potential (Bulk)', color: '#8B5CF6', priority: 3 },
              loyal_frequent: { label: 'Loyal (Frequent)', color: '#3B82F6', priority: 4 },
              boring: { label: 'Boring / New', color: '#6B7280', priority: 5 },
            };
            const targetCustomers = customers.filter(c => {
              const seg = c.segment || c.category || 'boring';
              return segmentTemplates[seg];
            });
            const total = targetCustomers.length;
            const totalBatches = Math.ceil(total / batchSize);
            const cooldown = 30; // seconds
            const batchSendSecs = batchSize * 1.5;
            const totalSecs = (batchSendSecs * totalBatches) + (cooldown * Math.max(0, totalBatches - 1));
            const estMinutes = Math.ceil(totalSecs / 60);

            // Group by segment
            const segGroups = {};
            targetCustomers.forEach(c => {
              const seg = c.segment || c.category || 'boring';
              segGroups[seg] = (segGroups[seg] || 0) + 1;
            });
            const sortedSegs = Object.entries(segGroups)
              .sort(([a], [b]) => (SEGMENT_PRIORITY[a]?.priority ?? 9) - (SEGMENT_PRIORITY[b]?.priority ?? 9));

            return (
              <div className="bg-gradient-to-br from-[#1C1C1C] to-[#121212] border border-[#3ECF8E]/30 rounded-xl p-5 mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-8 h-8 rounded-lg bg-[#3ECF8E]/10 flex items-center justify-center">
                    <Send className="w-4 h-4 text-[#3ECF8E]" />
                  </div>
                  <div>
                    <h4 className="font-bold text-white">Ready to Launch?</h4>
                    <p className="text-xs text-muted-foreground">Train Station Batching Preview</p>
                  </div>
                </div>

                {/* Key stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {[
                    { label: 'Total Audience',       value: `${total} customers`,         color: '#3ECF8E' },
                    { label: 'Total Batches',         value: `${totalBatches} batches`,    color: '#3B82F6' },
                    { label: 'Batch Size',            value: `${batchSize} / batch`,       color: '#8B5CF6' },
                    { label: 'Est. Duration',         value: `~${estMinutes} min`,         color: '#F59E0B' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-[#2E2E2E]/40 rounded-lg p-3 border border-[#2E2E2E]">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
                      <p className="font-bold text-sm" style={{ color }}>{value}</p>
                    </div>
                  ))}
                </div>

                {/* Segment breakdown table */}
                {sortedSegs.length > 0 && (
                  <div className="space-y-1.5 mb-4">
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Segment → Batch Breakdown (Priority Order)</p>
                    {sortedSegs.map(([seg, count], idx) => {
                      const cfg = SEGMENT_PRIORITY[seg] || { label: seg, color: '#6B7280', priority: 9 };
                      const segBatches = Math.ceil(count / batchSize);
                      const lastBatch = count % batchSize || batchSize;
                      const batchDesc = segBatches === 1
                        ? `1 batch (${count})`
                        : `${segBatches} batches (${Array(segBatches - 1).fill(batchSize).join(', ')}, ${lastBatch})`;
                      return (
                        <div key={seg} className="flex items-center gap-3 text-xs bg-[#121212] rounded-lg px-3 py-2 border border-[#2E2E2E]">
                          <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold bg-[#2E2E2E]" style={{ color: cfg.color }}>
                            {idx + 1}
                          </span>
                          <span className="w-32 font-medium" style={{ color: cfg.color }}>{cfg.label}</span>
                          <span className="text-muted-foreground w-16">{count} people</span>
                          <span className="text-white flex-1">{batchDesc}</span>
                          <span className="text-[#3ECF8E] font-mono">{segBatches}×</span>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Safety note */}
                <div className="flex items-start gap-2 bg-[#F59E0B]/5 border border-[#F59E0B]/20 rounded-lg px-3 py-2 text-xs text-[#F59E0B]">
                  <span className="mt-0.5">⚡</span>
                  <span>
                    <strong>Smart Safety Delay:</strong> {cooldown}s cooldown between each batch to avoid WhatsApp rate limits.
                    VIPs receive messages first (Priority 1), Boring/New last (Priority 5).
                  </span>
                </div>
              </div>
            );
          })()}


          <div className="flex justify-between items-center pt-4 border-t border-[#2E2E2E]">
            <button onClick={() => setStep(3)} className="px-4 py-2 text-muted-foreground hover:text-white transition-colors">Back</button>
            <button
              onClick={handleLaunch}
              disabled={launching}
              className="flex items-center px-8 py-2.5 bg-[#3ECF8E] text-black font-semibold rounded-md hover:bg-[#32B37A] transition-colors disabled:opacity-50 shadow-[0_0_20px_rgba(62,207,142,0.3)]"
            >
              <Send className="w-4 h-4 mr-2" />
              {launching ? 'Launching…' : 'Launch Campaign'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default CampaignCreatorPage;
