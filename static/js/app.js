// State global de l'application StockMaster Alu
const AppState = {
  currentTab: 'dashboard',
  currentActionSubTab: 'creer',
  stockViewMode: 'table', // 'table' ou 'cards'
  selectedDashboardOrder: 'ALL',
  dashboardPeriod: 'ALL',
  dashboardStartDate: null,
  dashboardEndDate: null,
  allReferences: [],
  allVariants: [],
  categories: [],
  gammes: [],
  units: [],
  workshopCases: [],
  colors: [],
  orders: [],
  destockBatchItems: [],
  reserveBatchItems: [],
  destockCollapsed: false,
  reserveCollapsed: false
};

// Formatage monétaire en Dinars Algériens (DZD)
function formatMoney(val) {
  const num = Number(val || 0);
  return new Intl.NumberFormat('fr-DZ', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num) + ' DZD';
}

// Rétrocompatibilité avec formatEuro
function formatEuro(val) {
  return formatMoney(val);
}

// Initialisation au chargement
async function initApp() {
  loadThemePreference();
  await loadGlobalSettings();
  await loadOrdersList();
  await loadReferencesForSelects();
  initSupabaseRealtime();
  switchTab('dashboard');
}

// =========================================================================
// GESTION SUPABASE CLOUD & SYNCHRONISATION MULTI-APPAREILS EN TEMPS RÉEL
// =========================================================================

function updateSupabaseUiStatus(connected) {
  const badge = document.getElementById('supabaseSyncBadge');
  const pill = document.getElementById('supabaseStatusPill');

  if (connected) {
    if (badge) badge.classList.replace('hidden', 'flex');
    if (pill) {
      pill.textContent = '🟢 Connecté & Synchronisé (Live)';
      pill.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300';
    }
  } else {
    if (badge) badge.classList.replace('flex', 'hidden');
    if (pill) {
      pill.textContent = 'Non configuré';
      pill.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
    }
  }
}

function initSupabaseRealtime() {
  const defaultUrl = 'https://oqdbhqpjspjezunvrzvo.supabase.co';
  const defaultKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9xZGJocXBqc3BqZXp1bnZyenZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM3MDg2NDYsImV4cCI6MjEwOTI4NDY0Nn0.Sxq7efJjTC1cQAQiK19PH0eYlFk84YhujW0zCKlmem0';

  const url = localStorage.getItem('stockmaster_supabase_url') || defaultUrl;
  const key = localStorage.getItem('stockmaster_supabase_key') || defaultKey;

  // Remplir les champs dans la page Paramètres si présents
  const urlInput = document.getElementById('cfgSupabaseUrl');
  const keyInput = document.getElementById('cfgSupabaseKey');
  if (urlInput && !urlInput.value) urlInput.value = url;
  if (keyInput && !keyInput.value) keyInput.value = key;

  if (!url || !key || typeof window.supabase === 'undefined') {
    updateSupabaseUiStatus(false);
    return;
  }

  try {
    if (window.supabaseClient) {
      window.supabaseClient.removeAllChannels();
    }

    window.supabaseClient = window.supabase.createClient(url, key);

    window.supabaseChannel = window.supabaseClient.channel('stockmaster-cloud-sync')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'variants' }, (payload) => {
        console.log('[Supabase Realtime] Changement de stock détecté :', payload);
        loadStockData();
        refreshDashboard();
      })
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'movements' }, (payload) => {
        console.log('[Supabase Realtime] Nouveau mouvement en atelier :', payload);
        loadMovementsData();
        refreshDashboard();
        if (payload.new && payload.new.product_reference) {
          showToast(`⚡ Synchro Cloud : Mouvement ${payload.new.action_type} (${payload.new.product_reference}) reçu d'un autre appareil`, 'info');
        }
      })
      .on('postgres_changes', { event: '*', schema: 'public', table: 'orders' }, (payload) => {
        console.log('[Supabase Realtime] Mise à jour des commandes :', payload);
        loadOrdersList();
      })
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          console.log('[Supabase Realtime] Connecté avec succès au canal live.');
          updateSupabaseUiStatus(true);
        } else if (status === 'CHANNEL_ERROR') {
          console.warn('[Supabase Realtime] Erreur de canal.');
          updateSupabaseUiStatus(false);
        }
      });

  } catch (err) {
    console.error('Erreur initialisation Supabase Realtime:', err);
    updateSupabaseUiStatus(false);
  }
}

function saveAndConnectSupabase() {
  const url = document.getElementById('cfgSupabaseUrl')?.value.trim();
  const key = document.getElementById('cfgSupabaseKey')?.value.trim();

  if (!url || !key) {
    showToast("Veuillez renseigner l'URL du projet et la clé publique Supabase", "warning");
    return;
  }

  localStorage.setItem('stockmaster_supabase_url', url);
  localStorage.setItem('stockmaster_supabase_key', key);

  initSupabaseRealtime();
  showToast("Paramètres Cloud enregistrés ! Tentative de connexion en direct...", "success");
}

// Navigation entre les 6 onglets
function switchTab(tabId) {
  AppState.currentTab = tabId;

  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));

  const target = document.getElementById(`tab-${tabId}`);
  if (target) target.classList.remove('hidden');

  // Sidebar desktop
  document.querySelectorAll('.side-nav-btn').forEach(btn => {
    btn.classList.remove('bg-indigo-50', 'text-indigo-600', 'font-bold', 'dark:bg-slate-800');
  });
  const activeSideBtn = document.getElementById(`sideNav-${tabId}`);
  if (activeSideBtn) {
    activeSideBtn.classList.add('bg-indigo-50', 'text-indigo-600', 'font-bold', 'dark:bg-slate-800');
  }

  // Bottom-nav mobile
  document.querySelectorAll('.nav-touch-item').forEach(btn => btn.classList.remove('active'));
  const activeMobileBtn = document.getElementById(`mobileNav-${tabId}`);
  if (activeMobileBtn) activeMobileBtn.classList.add('active');

  if (tabId === 'dashboard') {
    refreshDashboard();
  } else if (tabId === 'stock') {
    loadStockData();
  } else if (tabId === 'actions') {
    refreshActionFormSelects();
  } else if (tabId === 'movements') {
    loadMovementsData();
  } else if (tabId === 'orders') {
    loadOrdersData();
  } else if (tabId === 'settings') {
    loadSettingsData();
  } else if (tabId === 'inventory') {
    loadInventoryData();
  }

  lucide.createIcons();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Chargement des paramètres globaux (catégories, gammes, unités, cases atelier)
async function loadGlobalSettings() {
  try {
    const res = await fetch('/api/settings/all');
    if (res.ok) {
      const data = await res.json();
      AppState.categories = data.categories || [];
      AppState.gammes = data.gammes || [];
      AppState.units = data.units || [];
      AppState.workshopCases = data.cases || [];
      AppState.colors = data.colors || [];
      populateFilterDropdowns();
      if (typeof renderCreationColorSwatches === 'function') {
        renderCreationColorSwatches();
      }
      if (typeof renderSettingsColors === 'function') {
        renderSettingsColors();
      }
    }
  } catch (err) {
    console.error('Erreur chargement paramètres:', err);
  }
}

// Chargement des commandes pour les menus déroulants
async function loadOrdersList() {
  try {
    const res = await fetch('/api/orders');
    if (res.ok) {
      AppState.orders = await res.json();
      populateOrdersDropdowns();
    }
  } catch (err) {
    console.error('Erreur chargement commandes:', err);
  }
}

function populateOrdersDropdowns() {
  // Select déstockage
  const destockOrder = document.getElementById('destockOrderSelect');
  if (destockOrder) {
    let html = '<option value="NONE">-- Non assigné à une commande (Débit atelier libre) --</option>';
    AppState.orders.forEach(o => {
      const statusIcon = o.status === 'DESTOCKED' ? '✅' : (o.status === 'RESERVEE' ? '🔒' : '⏳');
      html += `<option value="${o.order_number}">${statusIcon} ${o.order_number} (${o.client_name})</option>`;
    });
    destockOrder.innerHTML = html;
  }

  // Select réservation
  const resOrder = document.getElementById('reserveOrderSelect');
  if (resOrder) {
    let html = '<option value="">-- Choisir une commande / chantier --</option>';
    AppState.orders.forEach(o => {
      html += `<option value="${o.order_number}">📋 ${o.order_number} (${o.client_name})</option>`;
    });
    resOrder.innerHTML = html;
  }

  // Select filtre chantier dans stock
  const stockChantier = document.getElementById('stockFilterChantier');
  if (stockChantier) {
    const curVal = stockChantier.value;
    let html = '<option value="ALL">Tous les Chantiers / Commandes</option>';
    AppState.orders.forEach(o => {
      html += `<option value="${o.order_number}">🏗️ ${o.order_number} (${o.client_name})</option>`;
    });
    stockChantier.innerHTML = html;
    if (curVal) stockChantier.value = curVal;
  }
}

function populateFilterDropdowns() {
  // Filtres catalogue
  const catSelect = document.getElementById('stockFilterCategory');
  if (catSelect) {
    catSelect.innerHTML = '<option value="ALL">Toutes Catégories</option>' + 
      AppState.categories.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  }

  const gammeSelect = document.getElementById('stockFilterGamme');
  if (gammeSelect) {
    gammeSelect.innerHTML = '<option value="ALL">Toutes Gammes</option>' + 
      AppState.gammes.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
  }

  // Formulaire CRÉER Article
  const newCat = document.getElementById('actionNewCategory');
  if (newCat) {
    newCat.innerHTML = AppState.categories.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  }
  const newGamme = document.getElementById('actionNewGamme');
  if (newGamme) {
    newGamme.innerHTML = AppState.gammes.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
  }
  const newUnit = document.getElementById('actionNewUnit');
  if (newUnit) {
    newUnit.innerHTML = AppState.units.map(u => `<option value="${u.symbol}">${u.name} (${u.symbol})</option>`).join('');
  }

  // Emplacements / Cases Atelier
  const newLoc = document.getElementById('actionNewLocation');
  if (newLoc) {
    let locHtml = '<option value="EN_ATTENTE_AFFECTATION">⚠️ EN_ATTENTE_AFFECTATION</option>';
    const profiles = AppState.workshopCases.filter(c => c.type === 'PROFILE');
    const access = AppState.workshopCases.filter(c => c.type === 'ACCESSOIRE');

    if (profiles.length > 0) {
      locHtml += '<optgroup label="Cases Profilés (P-xx)">';
      profiles.forEach(c => {
        locHtml += `<option value="${c.code}">${c.code} ${c.description ? '— ' + c.description : ''}</option>`;
      });
      locHtml += '</optgroup>';
    }

    if (access.length > 0) {
      locHtml += '<optgroup label="Cases Accessoires (A-xx)">';
      access.forEach(c => {
        locHtml += `<option value="${c.code}">${c.code} ${c.description ? '— ' + c.description : ''}</option>`;
      });
      locHtml += '</optgroup>';
    }

    newLoc.innerHTML = locHtml;
  }
}

// Chargement des articles du catalogue maître pour autocomplétion
async function loadReferencesForSelects() {
  try {
    const res = await fetch('/api/stock/references');
    if (res.ok) {
      const data = await res.json();
      AppState.allReferences = data.products || [];
      AppState.allVariants = data.variants || [];
      populateReferenceSelects();
    }
  } catch (err) {
    console.error('Erreur chargement références:', err);
  }
}

function populateReferenceSelects() {
  // Datalist pour le champ de recherche / coller référence
  const dl = document.getElementById('stockInRefDatalist');
  if (dl) {
    dl.innerHTML = AppState.allReferences.map(p => 
      `<option value="${p.reference}">${p.reference} — ${p.designation} (${p.category})</option>`
    ).join('');
  }

  // Select Déstockage
  const destockSelect = document.getElementById('destockVariantSelect');
  if (destockSelect) {
    destockSelect.innerHTML = '<option value="">-- Sélectionner dans le stock --</option>' +
      AppState.allVariants.map(v => `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${v.real_quantity - v.reserved_quantity} | PMP: ${formatMoney(v.pmp)})</option>`).join('');
  }

  // Select Réservation
  const resSelect = document.getElementById('reserveVariantSelect');
  if (resSelect) {
    resSelect.innerHTML = '<option value="">-- Choisir la référence alu --</option>' +
      AppState.allVariants.map(v => `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${v.real_quantity - v.reserved_quantity})</option>`).join('');
  }
}


// Notifications Toast
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-600 text-white',
    error: 'bg-rose-600 text-white',
    warning: 'bg-amber-600 text-white',
    info: 'bg-indigo-600 text-white'
  };

  const icons = {
    success: 'check-circle-2',
    error: 'alert-circle',
    warning: 'alert-triangle',
    info: 'info'
  };

  toast.className = `toast-enter pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-2xl shadow-xl ${colors[type] || colors.info} text-xs sm:text-sm font-semibold transition-all`;
  toast.innerHTML = `
    <i data-lucide="${icons[type] || 'info'}" class="w-4 h-4 shrink-0"></i>
    <span class="flex-1">${message}</span>
  `;

  container.appendChild(toast);
  lucide.createIcons();

  setTimeout(() => {
    toast.classList.remove('toast-enter');
    toast.classList.add('toast-exit');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Thème Sombre / Clair
function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  document.body.classList.toggle('dark-mode', isDark);
  localStorage.setItem('stockmaster_theme', isDark ? 'dark' : 'light');
  lucide.createIcons();
  
  if (window.timelineChartInstance) window.timelineChartInstance.update();
  if (window.categoryChartInstance) window.categoryChartInstance.update();
}

function loadThemePreference() {
  const saved = localStorage.getItem('stockmaster_theme');
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
    document.body.classList.add('dark-mode');
  } else {
    document.documentElement.classList.remove('dark');
    document.body.classList.remove('dark-mode');
  }
}
