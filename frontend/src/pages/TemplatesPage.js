import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { templatesAPI } from '../lib/api';
import { Plus, Trash2, FileText, X, Crown, AlertTriangle, Package, Zap, User, Users, Copy, Edit2, Eye, ChevronDown, ChevronUp, Sparkles, ArrowLeft, ShoppingBag, Star } from 'lucide-react';
import { toast } from 'sonner';

/* ── 11 Smart Variables ── */
const SMART_VARS = [
  { key: 'customer_name', label: 'Customer Name', example: 'Rahul Menon', color: '#3ECF8E', desc: "Customer's full name" },
  { key: 'segment', label: 'Segment', example: 'VIP', color: '#F59E0B', desc: 'RFM segment (VIP, At-Risk…)' },
  { key: 'favorite_category', label: 'Favorite Category', example: 'Cosmetics', color: '#8B5CF6', desc: 'Top category by weighted affinity' },
  { key: 'favorite_premium_product', label: 'Favorite Premium Product', example: "L'Oréal Serum", color: '#EC4899', desc: 'Top premium product in fav category' },
  { key: 'favorite_bulk_product', label: 'Favorite Bulk Product', example: 'Rice 5kg', color: '#3B82F6', desc: 'Top bulk product by quantity' },
  { key: 'second_favorite_premium_product', label: '2nd Premium Product', example: 'Maybelline Lipstick', color: '#06B6D4', desc: 'Second highest premium product' },
  { key: 'recently_bought_product', label: 'Recently Bought', example: 'Dove Soap', color: '#10B981', desc: 'Most recent product bought' },
  { key: 'complementary_product', label: 'Complementary Product', example: 'Shampoo', color: '#F97316', desc: 'Frequently bought alongside top product' },
  { key: 'offer_title', label: 'Offer Title', example: 'Great deals throughout our store', color: '#A855F7', desc: 'Matched offer title' },
  { key: 'offer_discount', label: 'Offer Discount', example: 'the best wholesale prices', color: '#F43F5E', desc: 'Matched discount (e.g. 20% OFF)' },
  { key: 'offer_product', label: 'Offer Product', example: 'your next household purchase', color: '#14B8A6', desc: 'Target product(s) for the offer' },
  { key: 'offer_list', label: 'Offer List', example: '🏷️ 20% off Rice\n🏷️ 15% off Oil', color: '#D946EF', desc: 'Formatted list of all matched offers' },
];


/* ── Quick starter templates ── */
const QUICK_TEMPLATES = [
  {
    name: 'VIP Exclusive Offer', segment: 'vip',
    content: `Hi {{customer_name}} 👑\n\nAs one of our VIP Champions, you deserve the best!\n\nYour favourite pick: {{favorite_premium_product}}\n\nWe have an exclusive offer waiting for you in {{favorite_category}}. Don't miss it! 🎁\n\nReply YES to know more.`
  },
  {
    name: 'Win-Back At-Risk', segment: 'at_risk',
    content: `Hi {{customer_name}}, we miss you! 😢\n\nIt's been a while. We noticed you loved {{recently_bought_product}} — and we have something even better now.\n\nCome back today and enjoy a special discount just for you!\n\nReply BACK to claim your offer.`
  },
  {
    name: 'Bulk Buyer Deal', segment: 'potential_bulk',
    content: `Hello {{customer_name}}! 📦\n\nWe know you love buying in bulk — your top pick {{favorite_bulk_product}} is now available at a special rate!\n\nStock up and save more. Reply BULK to see the offer.`
  },
  {
    name: 'Loyalty Reward', segment: 'loyal_frequent',
    content: `Hi {{customer_name}} ⚡\n\nYou're one of our most loyal customers and we appreciate that!\n\nAs a {{segment}} member, you get early access to new arrivals in {{favorite_category}}.\n\nPair {{favorite_premium_product}} with {{complementary_product}} for a complete experience!`
  },
];

const segments = [
  { value: 'all', label: 'All', icon: Users, color: '#6B7280' },
  { value: 'vip', label: 'VIP', icon: Crown, color: '#F59E0B' },
  { value: 'at_risk', label: 'At-Risk', icon: AlertTriangle, color: '#EF4444' },
  { value: 'potential_bulk', label: 'Potential (Bulk)', icon: ShoppingBag, color: '#8B5CF6' },
  { value: 'loyal_frequent', label: 'Loyal (Frequent)', icon: Star, color: '#3B82F6' },
  { value: 'boring', label: 'Occasional', icon: User, color: '#6B7280' },

];

/* ── WhatsApp Bubble (renders hydrated text) ── */
const WhatsAppBubble = ({ text }) => {
  if (!text) return <span className="text-white/40 italic">Start typing to preview…</span>;
  const lines = text.split('\n').map((line, i) => {
    const parts = line.split(/(\*[^*]+\*)/g);
    return (
      <span key={i}>
        {parts.map((p, j) =>
          p.startsWith('*') && p.endsWith('*') ? <strong key={j}>{p.slice(1, -1)}</strong> : p
        )}
        <br />
      </span>
    );
  });
  return <>{lines}</>;
};

/* ── Template Form (with real customer preview) ── */
const TemplateForm = ({ initial, onSave, onCancel, saving }) => {
  const [form, setForm] = useState(initial || { name: '', content: '', segment: 'all' });
  const [showPreview, setShowPreview] = useState(true);
  const [showVarPopup, setShowVarPopup] = useState(false);
  const textareaRef = useRef(null);

  // Real preview state
  const [shops, setShops] = useState([]);
  const [selectedShop, setSelectedShop] = useState('');
  const [previewData, setPreviewData] = useState(null);
  const [availableCustomers, setAvailableCustomers] = useState([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewWarning, setPreviewWarning] = useState('');

  // Load shops once
  useEffect(() => {
    const loadShops = async () => {
      try {
        const { shopsAPI } = await import('../lib/api');
        const res = await shopsAPI.list();
        const list = res.data.shops || [];
        setShops(list);
        if (list.length > 0) setSelectedShop(list[0].id);
      } catch { /* ignore */ }
    };
    loadShops();
  }, []);

  // Fetch preview when shop / segment / content / customer changes
  useEffect(() => {
    if (!selectedShop || !form.content) { setPreviewData(null); return; }
    const timeout = setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const { shopsAPI } = await import('../lib/api');
        const res = await shopsAPI.previewTemplate(selectedShop, {
          template_text: form.content,
          segment: form.segment !== 'all' ? form.segment : '',
          customer_id: selectedCustomerId || undefined,
        });
        const d = res.data;
        setPreviewData(d);
        setAvailableCustomers(d.available_customers || []);
        if (!selectedCustomerId && d.used_customer?.customer_id) {
          setSelectedCustomerId(d.used_customer.customer_id);
        }
        setPreviewWarning(d.warning || '');
      } catch { setPreviewData(null); setPreviewWarning('Preview unavailable'); }
      finally { setPreviewLoading(false); }
    }, 600); // debounce
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShop, form.content, form.segment, selectedCustomerId]);

  // Fallback: if no shop selected, use dummy example preview
  const fallbackPreview = (() => {
    let t = form.content || '';
    SMART_VARS.forEach(v => { t = t.replace(new RegExp(`\\{\\{${v.key}\\}\\}`, 'g'), v.example); });
    return t;
  })();

  const displayText = previewData?.hydrated_text || fallbackPreview;

  const insertVar = (key) => {
    const ta = textareaRef.current;
    if (!ta) { setForm(f => ({ ...f, content: f.content + `{{${key}}}` })); return; }
    const s = ta.selectionStart, e = ta.selectionEnd;
    const next = form.content.substring(0, s) + `{{${key}}}` + form.content.substring(e);
    setForm(f => ({ ...f, content: next }));
    setTimeout(() => { ta.focus(); ta.setSelectionRange(s + key.length + 4, s + key.length + 4); }, 0);
  };

  /* ── Preview Widget ── */
  const PreviewWidget = () => (
    <div className="space-y-3">
      {/* Shop selector */}
      <div className="flex items-center gap-2">
        <select value={selectedShop} onChange={e => { setSelectedShop(e.target.value); setSelectedCustomerId(''); }}
          className="flex-1 bg-[#121212] border border-[#2E2E2E] rounded-lg px-2 py-1.5 text-xs outline-none">
          <option value="">Select shop for preview…</option>
          {shops.map(s => <option key={s.id} value={s.id}>{s.shop_name}</option>)}
        </select>
      </div>

      {/* Customer toggle */}
      {availableCustomers.length > 0 && (
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Previewing as:</p>
          <select value={selectedCustomerId} onChange={e => setSelectedCustomerId(e.target.value)}
            className="w-full bg-[#121212] border border-[#2E2E2E] rounded-lg px-2 py-1.5 text-xs outline-none">
            {availableCustomers.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.segment})</option>
            ))}
          </select>
        </div>
      )}

      {/* Warning */}
      {previewWarning && (
        <div className="text-[10px] bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-lg px-2 py-1.5">
          ⚠ {previewWarning}
        </div>
      )}

      {/* Customer badge */}
      {previewData?.used_customer && (
        <div className="flex items-center gap-2 text-[10px]">
          <div className="w-5 h-5 rounded-full bg-[#3ECF8E]/20 flex items-center justify-center text-[#3ECF8E] font-bold">
            {previewData.used_customer.customer_name?.charAt(0) || '?'}
          </div>
          <span className="text-white font-medium">{previewData.used_customer.customer_name}</span>
          <span className="text-muted-foreground">· {previewData.used_customer.segment}</span>
        </div>
      )}

      {/* WhatsApp bubble */}
      <div className="bg-[#0B141A] rounded-xl p-4 border border-[#2E2E2E]" style={{
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 38.59l2.83-2.83 1.41 1.41L1.41 40H0v-1.41z' fill='%231a2c38' fill-opacity='0.4'/%3E%3C/svg%3E\")"
      }}>
        <div className="max-w-[280px]">
          <div className="relative bg-[#005C4B] text-white text-sm px-4 py-3 rounded-xl rounded-tl-sm shadow-lg" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
            {previewLoading
              ? <span className="text-white/40 animate-pulse">Loading real preview…</span>
              : <WhatsAppBubble text={displayText} />}
            <div className="text-[10px] text-white/50 text-right mt-1">
              {previewData ? 'Real Data ✓✓' : 'Example ✓✓'}
            </div>
            <div className="absolute top-0 -left-2 w-0 h-0 border-t-[10px] border-t-[#005C4B] border-l-[10px] border-l-transparent" />
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: Form */}
      <div className="lg:col-span-2 space-y-5 bg-[#1C1C1C] border border-[#3ECF8E]/50 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>
            {initial?.id ? 'Edit Template' : 'New Template'}
          </h2>
          <button onClick={onCancel} className="p-1.5 hover:bg-[#2E2E2E] rounded-md transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Name */}
        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Template Name</label>
          <input
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g., Pongal VIP Offer"
            className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-lg px-3 py-2.5 text-sm outline-none transition-colors"
          />
        </div>

        {/* Segment */}
        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Target Segment</label>
          <div className="flex flex-wrap gap-2">
            {segments.map(seg => {
              const Icon = seg.icon;
              const active = form.segment === seg.value;
              return (
                <button key={seg.value} onClick={() => setForm(f => ({ ...f, segment: seg.value }))}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${active ? 'border-current' : 'border-[#2E2E2E] text-muted-foreground hover:border-[#3E3E3E]'}`}
                  style={active ? { color: seg.color, borderColor: seg.color, backgroundColor: seg.color + '18' } : {}}>
                  <Icon className="w-3.5 h-3.5" />{seg.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Message Content</label>
            <button onClick={() => setShowPreview(p => !p)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-white transition-colors">
              <Eye className="w-3.5 h-3.5" />{showPreview ? 'Hide' : 'Show'} Preview
            </button>
          </div>
          <textarea ref={textareaRef} value={form.content}
            onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
            placeholder="Hi {{customer_name}}, we have something special for you…"
            rows={8}
            className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] rounded-lg p-3 text-sm outline-none resize-none transition-colors font-mono"
          />
          <div className="flex items-center justify-between mt-1.5">
            <p className="text-xs text-muted-foreground">{form.content.length} chars · Use <code className="text-[#3ECF8E]">{'{{variable}}'}</code> to personalise</p>
            <button
              type="button"
              onClick={() => setShowVarPopup(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[#3ECF8E]/10 text-[#3ECF8E] border border-[#3ECF8E]/30 rounded-lg hover:bg-[#3ECF8E]/20 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" />Insert Variable
            </button>
          </div>
        </div>

        {/* ── Variable Insertion Popup ── */}
        {showVarPopup && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-6 max-w-md w-full max-h-[80vh] flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-[#3ECF8E]" />
                  <h3 className="text-lg font-bold">Insert Variable</h3>
                  <span className="text-xs text-muted-foreground bg-[#2E2E2E] px-2 py-0.5 rounded-full">{SMART_VARS.length}</span>
                </div>
                <button onClick={() => setShowVarPopup(false)} className="p-1.5 hover:bg-[#2E2E2E] rounded-md transition-colors">
                  <X className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>
              <div className="overflow-y-auto flex-1 space-y-1.5 pr-1">
                {SMART_VARS.map(v => (
                  <button
                    key={v.key}
                    onClick={() => { insertVar(v.key); setShowVarPopup(false); }}
                    className="w-full group flex items-start gap-3 p-3 rounded-lg hover:bg-[#2E2E2E]/60 transition-colors text-left"
                  >
                    <div className="w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: v.color }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <code className="text-sm font-mono" style={{ color: v.color }}>{`{{${v.key}}}`}</code>
                        <span className="text-[10px] text-[#3ECF8E] opacity-0 group-hover:opacity-100 transition-opacity font-medium">+ Insert</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{v.desc}</p>
                      <p className="text-[10px] text-white/40 italic">e.g. {v.example}</p>
                    </div>
                  </button>
                ))}
              </div>
              <div className="pt-3 mt-3 border-t border-[#2E2E2E]">
                <button onClick={() => setShowVarPopup(false)} className="w-full py-2 text-sm text-muted-foreground hover:text-white transition-colors">
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Preview (inline on mobile) */}
        {showPreview && (
          <div className="lg:hidden">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Real Customer Preview</p>
            <PreviewWidget />
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onCancel} className="px-5 py-2 text-sm text-muted-foreground hover:text-white border border-[#2E2E2E] rounded-lg transition-colors">Cancel</button>
          <button onClick={() => onSave(form)} disabled={saving || !form.name || !form.content}
            className="flex-1 py-2 text-sm bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] disabled:opacity-40 transition-colors">
            {saving ? 'Saving…' : initial?.id ? 'Save Changes' : 'Create Template'}
          </button>
        </div>
      </div>

      {/* Right: Variable sidebar + preview */}
      <div className="space-y-4">
        {/* Variables */}
        <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-[#3ECF8E]" />
            <span className="text-sm font-semibold">11 Smart Variables</span>
          </div>
          <div className="space-y-1.5">
            {SMART_VARS.map(v => (
              <div key={v.key} className="group flex items-start gap-2 p-2 rounded-lg hover:bg-[#2E2E2E]/60 transition-colors cursor-pointer"
                onClick={() => insertVar(v.key)}>
                <div className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: v.color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <code className="text-xs font-mono" style={{ color: v.color }}>{`{{${v.key}}}`}</code>
                    <span className="text-[10px] text-[#3ECF8E] opacity-0 group-hover:opacity-100 transition-opacity font-medium">+ Insert</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate">{v.desc}</p>
                  <p className="text-[10px] text-white/40 italic">e.g. {v.example}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Live preview (desktop) — Real customer data */}
        {showPreview && (
          <div className="hidden lg:block">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Real Customer Preview</p>
            <PreviewWidget />
          </div>
        )}
      </div>
    </div>
  );
};

/* ── Main Page ── */
const TemplatesPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const redirectState = location.state || {};
  const isRedirect = !!redirectState.redirectToCampaign;

  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState('list'); // 'list' | 'create' | 'edit'
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState('all');
  const [showQuick, setShowQuick] = useState(true);

  // Auto-open create form if redirected from campaign page
  useEffect(() => {
    if (isRedirect) {
      setEditing(redirectState.prefilledSegment
        ? { name: '', content: '', segment: redirectState.prefilledSegment }
        : null);
      setMode('create');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try { const r = await templatesAPI.list(); setTemplates(r.data.templates || []); }
    catch { toast.error('Failed to load templates'); }
    finally { setLoading(false); }
  };

  const handleSave = async (form) => {
    setSaving(true);
    try {
      if (editing?.id) {
        // update — try update endpoint, fall back to delete+create
        try { await templatesAPI.update(editing.id, form); }
        catch {
          await templatesAPI.delete(editing.id);
          await templatesAPI.create({ ...form, placeholders: [] });
        }
        toast.success('Template updated');
      } else {
        await templatesAPI.create({ ...form, placeholders: [] });
        toast.success('Template created');
      }
      setMode('list'); setEditing(null); await load();
      // If we came from campaign creator, navigate back
      if (isRedirect && redirectState.prefilledShopId) {
        navigate(`/campaign/new/${redirectState.prefilledShopId}`, { 
          replace: true, 
          state: { campaignState: redirectState.campaignState } 
        });
      }
    } catch { toast.error('Failed to save template'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this template?')) return;
    try { await templatesAPI.delete(id); toast.success('Deleted'); await load(); }
    catch { toast.error('Failed to delete'); }
  };

  const handleDuplicate = async (t, e) => {
    e.stopPropagation();
    try {
      await templatesAPI.create({ name: t.name + ' (Copy)', content: t.content, segment: t.segment, placeholders: [] });
      toast.success('Duplicated');
      await load();
    } catch { toast.error('Failed to duplicate'); }
  };

  const handleUseQuick = (qt) => {
    setEditing(null);
    setMode('create');
    // pre-fill via editing state trick
    setEditing({ name: qt.name, content: qt.content, segment: qt.segment });
  };

  const filtered = filter === 'all' ? templates : templates.filter(t => t.segment === filter || t.segment === 'all');
  const segMap = Object.fromEntries(segments.map(s => [s.value, s]));

  if (loading) return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading templates…</div>;

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          {isRedirect && (
            <button
              onClick={() => navigate(`/campaign/new/${redirectState.prefilledShopId}`, { 
                replace: true, 
                state: { campaignState: redirectState.campaignState } 
              })}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-white transition-colors mb-2"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Campaign
            </button>
          )}
          <h1 className="text-4xl font-bold mb-1" style={{ fontFamily: 'Chivo, sans-serif' }}>Message Templates</h1>
          <p className="text-muted-foreground text-sm">{templates.length} templates · 11 smart personalisation variables</p>
        </div>
        {mode === 'list' && (
          <button onClick={() => { setEditing(null); setMode('create'); }}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#3ECF8E] text-black font-semibold rounded-lg hover:bg-[#32B37A] transition-colors">
            <Plus className="w-4 h-4" />New Template
          </button>
        )}
      </div>

      {/* Form */}
      {(mode === 'create' || mode === 'edit') && (
        <TemplateForm
          initial={editing}
          onSave={handleSave}
          onCancel={() => { setMode('list'); setEditing(null); }}
          saving={saving}
        />
      )}

      {mode === 'list' && (
        <>
          {/* Quick Templates */}
          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl overflow-hidden">
            <button onClick={() => setShowQuick(p => !p)}
              className="w-full flex items-center justify-between p-4 hover:bg-[#252525] transition-colors">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#F59E0B]" />
                <span className="font-semibold text-sm">Quick Starter Templates</span>
                <span className="text-xs text-muted-foreground bg-[#2E2E2E] px-2 py-0.5 rounded-full">{QUICK_TEMPLATES.length}</span>
              </div>
              {showQuick ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {showQuick && (
              <div className="border-t border-[#2E2E2E] p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                {QUICK_TEMPLATES.map(qt => {
                  const seg = segMap[qt.segment] || segMap.all;
                  const Icon = seg.icon;
                  return (
                    <div key={qt.name} className="flex items-start gap-3 bg-[#121212] rounded-lg p-3 border border-[#2E2E2E] hover:border-[#3ECF8E]/40 transition-colors group">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: seg.color }} />
                          <span className="text-sm font-medium">{qt.name}</span>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2">{qt.content.substring(0, 100)}…</p>
                      </div>
                      <button onClick={() => handleUseQuick(qt)}
                        className="flex-shrink-0 px-3 py-1.5 text-xs font-medium bg-[#3ECF8E]/10 text-[#3ECF8E] border border-[#3ECF8E]/30 rounded-md hover:bg-[#3ECF8E]/20 transition-colors opacity-0 group-hover:opacity-100">
                        Use
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Filter + list */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>
                Your Templates <span className="text-muted-foreground font-normal text-base ml-2">({filtered.length})</span>
              </h2>
              <div className="flex gap-2">
                {segments.map(seg => {
                  const Icon = seg.icon;
                  const active = filter === seg.value;
                  return (
                    <button key={seg.value} onClick={() => setFilter(seg.value)}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-medium transition-all ${active ? 'border-current' : 'border-[#2E2E2E] text-muted-foreground hover:border-[#3E3E3E]'}`}
                      style={active ? { color: seg.color, borderColor: seg.color, backgroundColor: seg.color + '18' } : {}}>
                      <Icon className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">{seg.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {filtered.length === 0 ? (
              <div className="text-center py-16 bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl">
                <FileText className="w-12 h-12 text-[#2E2E2E] mx-auto mb-3" />
                <p className="text-muted-foreground">{templates.length === 0 ? 'No templates yet — create your first one above!' : 'No templates for this segment'}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {filtered.map(t => {
                  const seg = segMap[t.segment || 'all'] || segMap.all;
                  const Icon = seg.icon;
                  // Extract variables used
                  const usedVars = SMART_VARS.filter(v => t.content?.includes(`{{${v.key}}}`));
                  return (
                    <div key={t.id} className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-xl p-5 hover:border-[#3ECF8E]/40 transition-all group relative flex flex-col">
                      {/* Top */}
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold truncate mb-1">{t.name}</h3>
                          <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border"
                            style={{ color: seg.color, borderColor: seg.color + '50', backgroundColor: seg.color + '15' }}>
                            <Icon className="w-2.5 h-2.5" />{seg.label}
                          </span>
                        </div>
                        {/* Actions */}
                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                          <button onClick={() => { setEditing(t); setMode('edit'); }}
                            className="p-1.5 hover:bg-[#2E2E2E] rounded-md transition-colors" title="Edit">
                            <Edit2 className="w-3.5 h-3.5 text-muted-foreground hover:text-white" />
                          </button>
                          <button onClick={(e) => handleDuplicate(t, e)}
                            className="p-1.5 hover:bg-[#2E2E2E] rounded-md transition-colors" title="Duplicate">
                            <Copy className="w-3.5 h-3.5 text-muted-foreground hover:text-white" />
                          </button>
                          <button onClick={(e) => handleDelete(t.id, e)}
                            className="p-1.5 hover:bg-red-500/10 rounded-md transition-colors" title="Delete">
                            <Trash2 className="w-3.5 h-3.5 text-red-400" />
                          </button>
                        </div>
                      </div>

                      {/* Content preview */}
                      <p className="text-xs text-muted-foreground line-clamp-3 flex-1 mb-3">{t.content}</p>

                      {/* Variables used */}
                      {usedVars.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {usedVars.map(v => (
                            <span key={v.key} className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                              style={{ backgroundColor: v.color + '18', color: v.color }}>
                              {`{{${v.key}}}`}
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
        </>
      )}
    </div>
  );
};

export default TemplatesPage;
