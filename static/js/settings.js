/**
 * SETTINGS.JS - GESTION DES DONNÉES MAÎTRESSES & CASES ATELIER
 * - Cases Atelier (P-xx profilés et A-xx accessoires)
 * - Unités de mesure
 * - Catégories & Gammes/Séries
 */

async function loadSettingsData() {
  try {
    const res = await fetch('/api/settings/all');
    if (!res.ok) throw new Error('Erreur de chargement des paramètres');
    const data = await res.json();

    renderCasesList(data.cases || []);
    renderUnitsList(data.units || []);
    renderCategoriesList(data.categories || []);
    renderGammesList(data.gammes || []);
    renderSettingsColors(data.colors || []);

    // Charger et afficher les commandes dans Paramètres
    await loadSettingsOrders();

  } catch (err) {
    console.error('Erreur loadSettingsData:', err);
    showToast('Erreur chargement paramètres', 'error');
  }
}

// =========================================================================
// 1. CASES ATELIER (P-xx Profilés & A-xx Accessoires)
// =========================================================================

function renderCasesList(cases) {
  const list = document.getElementById('settingsCasesList');
  const badge = document.getElementById('casesCountBadge');
  if (badge) badge.textContent = cases.length;
  if (!list) return;

  if (cases.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2">Aucune case définie</li>';
    return;
  }

  list.innerHTML = cases.map(c => {
    const isProfile = c.type === 'PROFILE';
    const badgeColor = isProfile 
      ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300' 
      : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300';
    const typeLabel = isProfile ? 'Profilé' : 'Accessoire';

    return `
      <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded font-mono font-bold text-xs ${badgeColor}">${c.code}</span>
          <div>
            <div class="text-[11px] font-semibold text-slate-800 dark:text-slate-200">${c.description || typeLabel}</div>
          </div>
        </div>
        <button onclick="handleDeleteCase(${c.id}, '${c.code}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      </li>
    `;
  }).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleAddCase(e) {
  e.preventDefault();
  const type = document.getElementById('newCaseType')?.value;
  const num = document.getElementById('newCaseNumber')?.value.trim();
  const desc = document.getElementById('newCaseDesc')?.value.trim();

  if (!type || !num) {
    showToast("Veuillez sélectionner un type et un numéro de case", "warning");
    return;
  }

  try {
    const res = await fetch('/api/settings/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: type, number: num, description: desc })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur');

    showToast(`Case "${result.code}" ajoutée avec succès !`, 'success');
    document.getElementById('newCaseNumber').value = '';
    document.getElementById('newCaseDesc').value = '';

    await loadSettingsData();
    await loadGlobalSettings();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}





// =========================================================================
// 7. GESTION DU NUANCIER ET COULEURS RAL DANS PARAMÈTRES
// =========================================================================

function renderSettingsColors(colors) {
  const list = document.getElementById('settingsColorsList');
  const badge = document.getElementById('colorsCountBadge');
  const colorsList = colors || AppState.colors || [];

  if (badge) badge.textContent = colorsList.length;
  if (!list) return;

  if (colorsList.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2 text-center">Aucune couleur enregistrée</li>';
    return;
  }

  list.innerHTML = colorsList.map(c => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-5 h-5 rounded-full border border-slate-300 dark:border-slate-600 shadow-sm shrink-0" style="background-color: ${c.hex_code || '#474a51'};"></div>
        <div class="min-w-0">
          <div class="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">${c.name}</div>
          <div class="text-[10px] font-mono text-slate-400 font-semibold">${c.ral_code ? c.ral_code : ''} ${c.hex_code ? '• ' + c.hex_code : ''}</div>
        </div>
      </div>
      <button onclick="handleDeleteColor(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  lucide.createIcons();
}

async function handleAddColor(e) {
  e.preventDefault();
  const nameInput = document.getElementById('newColorName');
  const ralInput = document.getElementById('newColorRal');
  const hexInput = document.getElementById('newColorHex');

  const name = nameInput ? nameInput.value.trim() : '';
  const ral = ralInput ? ralInput.value.trim() : '';
  const hex = hexInput ? hexInput.value.trim() : '#474a51';

  if (!name) return;

  try {
    const res = await fetch('/api/settings/colors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ral_code: ral, hex_code: hex })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur ajout couleur');

    showToast(`Couleur "${result.name}" ajoutée avec succès !`, 'success');
    if (nameInput) nameInput.value = '';
    if (ralInput) ralInput.value = '';

    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteColor(id, name) {
  if (!confirm(`Supprimer la couleur "${name}" ?`)) return;
  try {
    const res = await fetch(`/api/settings/colors/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur suppression');
    }
    showToast('Couleur supprimée', 'info');
    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteCase(id, code) {
  if (!confirm(`Supprimer la case atelier "${code}" ?`)) return;

  try {
    const res = await fetch(`/api/settings/cases/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Erreur de suppression');

    showToast(`Case "${code}" supprimée`, 'info');
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// =========================================================================
// 2. UNITÉS DE MESURE
// =========================================================================

function renderUnitsList(units) {
  const list = document.getElementById('settingsUnitsList');
  const badge = document.getElementById('unitsCountBadge');
  if (badge) badge.textContent = units.length;
  if (!list) return;

  if (units.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2">Aucune unité</li>';
    return;
  }

  list.innerHTML = units.map(u => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2">
        <span class="px-2 py-0.5 rounded font-mono font-bold text-xs bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">${u.symbol}</span>
        <span class="text-xs font-semibold text-slate-800 dark:text-slate-200">${u.name}</span>
      </div>
      <button onclick="handleDeleteUnit(${u.id}, '${u.name}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleAddUnit(e) {
  e.preventDefault();
  const name = document.getElementById('newUnitName')?.value.trim();
  const symbol = document.getElementById('newUnitSymbol')?.value.trim();

  if (!name || !symbol) return;

  try {
    const res = await fetch('/api/settings/units', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, symbol: symbol })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur');

    showToast(`Unité "${name} (${symbol})" ajoutée`, 'success');
    document.getElementById('newUnitName').value = '';
    document.getElementById('newUnitSymbol').value = '';

    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}





// =========================================================================
// 7. GESTION DU NUANCIER ET COULEURS RAL DANS PARAMÈTRES
// =========================================================================

function renderSettingsColors(colors) {
  const list = document.getElementById('settingsColorsList');
  const badge = document.getElementById('colorsCountBadge');
  const colorsList = colors || AppState.colors || [];

  if (badge) badge.textContent = colorsList.length;
  if (!list) return;

  if (colorsList.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2 text-center">Aucune couleur enregistrée</li>';
    return;
  }

  list.innerHTML = colorsList.map(c => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-5 h-5 rounded-full border border-slate-300 dark:border-slate-600 shadow-sm shrink-0" style="background-color: ${c.hex_code || '#474a51'};"></div>
        <div class="min-w-0">
          <div class="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">${c.name}</div>
          <div class="text-[10px] font-mono text-slate-400 font-semibold">${c.ral_code ? c.ral_code : ''} ${c.hex_code ? '• ' + c.hex_code : ''}</div>
        </div>
      </div>
      <button onclick="handleDeleteColor(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  lucide.createIcons();
}

async function handleAddColor(e) {
  e.preventDefault();
  const nameInput = document.getElementById('newColorName');
  const ralInput = document.getElementById('newColorRal');
  const hexInput = document.getElementById('newColorHex');

  const name = nameInput ? nameInput.value.trim() : '';
  const ral = ralInput ? ralInput.value.trim() : '';
  const hex = hexInput ? hexInput.value.trim() : '#474a51';

  if (!name) return;

  try {
    const res = await fetch('/api/settings/colors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ral_code: ral, hex_code: hex })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur ajout couleur');

    showToast(`Couleur "${result.name}" ajoutée avec succès !`, 'success');
    if (nameInput) nameInput.value = '';
    if (ralInput) ralInput.value = '';

    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteColor(id, name) {
  if (!confirm(`Supprimer la couleur "${name}" ?`)) return;
  try {
    const res = await fetch(`/api/settings/colors/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur suppression');
    }
    showToast('Couleur supprimée', 'info');
    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteUnit(id, name) {
  if (!confirm(`Supprimer l'unité "${name}" ?`)) return;

  try {
    const res = await fetch(`/api/settings/units/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Erreur');

    showToast('Unité supprimée', 'info');
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// =========================================================================
// 3. CATÉGORIES
// =========================================================================

function renderCategoriesList(categories) {
  const list = document.getElementById('settingsCategoriesList');
  const badge = document.getElementById('catCountBadge');
  if (badge) badge.textContent = categories.length;
  if (!list) return;

  if (categories.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2">Aucune catégorie</li>';
    return;
  }

  list.innerHTML = categories.map(c => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div>
        <span class="font-bold text-slate-800 dark:text-slate-200 text-xs">${c.name}</span>
      </div>
      <button onclick="handleDeleteCategory(${c.id}, '${c.name}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleAddCategory(e) {
  e.preventDefault();
  const input = document.getElementById('newCatName');
  const name = input?.value.trim();
  if (!name) return;

  try {
    const res = await fetch('/api/settings/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, description: 'Catégorie alu' })
    });
    if (!res.ok) throw new Error('Erreur');

    showToast(`Catégorie "${name}" ajoutée`, 'success');
    input.value = '';
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function handleDeleteCategory(id, name) {
  if (!confirm(`Supprimer la catégorie "${name}" ?`)) return;
  try {
    await fetch(`/api/settings/categories/${id}`, { method: 'DELETE' });
    showToast('Catégorie supprimée', 'info');
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// =========================================================================
// 4. GAMMES & SÉRIES
// =========================================================================

function renderGammesList(gammes) {
  const list = document.getElementById('settingsGammesList');
  const badge = document.getElementById('gammeCountBadge');
  if (badge) badge.textContent = gammes.length;
  if (!list) return;

  if (gammes.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2">Aucune gamme</li>';
    return;
  }

  list.innerHTML = gammes.map(g => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div>
        <span class="font-bold text-slate-800 dark:text-slate-200 text-xs">${g.name}</span>
      </div>
      <button onclick="handleDeleteGamme(${g.id}, '${g.name}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleAddGamme(e) {
  e.preventDefault();
  const input = document.getElementById('newGammeName');
  const name = input?.value.trim();
  if (!name) return;

  try {
    const res = await fetch('/api/settings/gammes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, description: 'Série alu' })
    });
    if (!res.ok) throw new Error('Erreur');

    showToast(`Série "${name}" ajoutée`, 'success');
    input.value = '';
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function handleDeleteGamme(id, name) {
  if (!confirm(`Supprimer la gamme "${name}" ?`)) return;
  try {
    await fetch(`/api/settings/gammes/${id}`, { method: 'DELETE' });
    showToast('Gamme supprimée', 'info');
    await loadSettingsData();
    await loadGlobalSettings();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// =========================================================================
// 5. RÉINITIALISATION DÉMO MENUISERIE ALU
// =========================================================================

async function confirmResetDemo() {
  if (!confirm('Réinitialiser toutes les données aux valeurs de démonstration menuiserie alu / volets ?')) return;

  try {
    const res = await fetch('/api/settings/reset-demo', { method: 'POST' });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur');

    showToast('Base alu réinitialisée avec succès !', 'success');
    await loadGlobalSettings();
    await loadReferencesForSelects();
    await loadSettingsData();
    refreshDashboard();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// =========================================================================
// 6. GESTION DES COMMANDES & CHANTIERS DANS PARAMÈTRES
// =========================================================================

async function loadSettingsOrders() {
  try {
    const res = await fetch('/api/orders');
    if (res.ok) {
      const orders = await res.json();
      renderSettingsOrdersList(orders);
    }
  } catch (err) {
    console.error('Erreur loadSettingsOrders:', err);
  }
}

function renderSettingsOrdersList(orders) {
  const container = document.getElementById('settingsOrdersList');
  const countBadge = document.getElementById('settingsOrdersCountBadge');
  if (countBadge) countBadge.textContent = orders ? orders.length : 0;
  if (!container) return;

  if (!orders || orders.length === 0) {
    container.innerHTML = '<li class="text-slate-400 italic py-3 text-center">Aucune commande ou chantier enregistré</li>';
    return;
  }

  container.innerHTML = orders.map(o => {
    let statusBadge = '';
    if (o.status === 'DESTOCKED') {
      statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">✅ Déstocké</span>';
    } else if (o.status === 'RESERVEE') {
      statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">🔒 Réservé</span>';
    } else {
      statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300">⏳ En attente</span>';
    }

    return `
      <li class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 gap-2">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-mono font-bold text-xs text-blue-600 dark:text-blue-400">${o.order_number}</span>
            ${statusBadge}
          </div>
          <div class="text-[11px] font-semibold text-slate-800 dark:text-slate-200 truncate">${o.client_name}</div>
          <div class="text-[10px] text-slate-400">${o.created_at || ''} • ${o.items_count || 0} profilé(s)</div>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          ${o.status === 'RESERVEE' ? `
            <button onclick="handleValidateDestockOrder('${o.order_number}')" class="px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-[10px] shadow-sm flex items-center gap-1" title="Valider & Déstocker">
              <i data-lucide="check" class="w-3 h-3"></i>
              <span>Déstocker</span>
            </button>
          ` : ''}
          <button onclick="handleDeleteOrderInSettings('${o.order_number}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer la commande">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </li>
    `;
  }).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleAddOrderInSettings(e) {
  e.preventDefault();
  const numInput = document.getElementById('newOrderNumberSettings');
  const clientInput = document.getElementById('newOrderClientSettings');
  const notesInput = document.getElementById('newOrderNotesSettings');

  const orderNumber = numInput?.value.trim().toUpperCase();
  const clientName = clientInput?.value.trim();
  const notes = notesInput?.value.trim() || '';

  if (!orderNumber || !clientName) {
    showToast("Veuillez saisir un numéro de commande et un nom de client", "warning");
    return;
  }

  try {
    const res = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_number: orderNumber,
        client_name: clientName,
        notes: notes
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur lors de la création');

    showToast(`Commande ${result.order_number} créée avec succès !`, 'success');
    numInput.value = '';
    clientInput.value = '';
    if (notesInput) notesInput.value = '';

    await loadSettingsOrders();
    await loadOrdersList();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}





// =========================================================================
// 7. GESTION DU NUANCIER ET COULEURS RAL DANS PARAMÈTRES
// =========================================================================

function renderSettingsColors(colors) {
  const list = document.getElementById('settingsColorsList');
  const badge = document.getElementById('colorsCountBadge');
  const colorsList = colors || AppState.colors || [];

  if (badge) badge.textContent = colorsList.length;
  if (!list) return;

  if (colorsList.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2 text-center">Aucune couleur enregistrée</li>';
    return;
  }

  list.innerHTML = colorsList.map(c => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-5 h-5 rounded-full border border-slate-300 dark:border-slate-600 shadow-sm shrink-0" style="background-color: ${c.hex_code || '#474a51'};"></div>
        <div class="min-w-0">
          <div class="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">${c.name}</div>
          <div class="text-[10px] font-mono text-slate-400 font-semibold">${c.ral_code ? c.ral_code : ''} ${c.hex_code ? '• ' + c.hex_code : ''}</div>
        </div>
      </div>
      <button onclick="handleDeleteColor(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  lucide.createIcons();
}

async function handleAddColor(e) {
  e.preventDefault();
  const nameInput = document.getElementById('newColorName');
  const ralInput = document.getElementById('newColorRal');
  const hexInput = document.getElementById('newColorHex');

  const name = nameInput ? nameInput.value.trim() : '';
  const ral = ralInput ? ralInput.value.trim() : '';
  const hex = hexInput ? hexInput.value.trim() : '#474a51';

  if (!name) return;

  try {
    const res = await fetch('/api/settings/colors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ral_code: ral, hex_code: hex })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur ajout couleur');

    showToast(`Couleur "${result.name}" ajoutée avec succès !`, 'success');
    if (nameInput) nameInput.value = '';
    if (ralInput) ralInput.value = '';

    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteColor(id, name) {
  if (!confirm(`Supprimer la couleur "${name}" ?`)) return;
  try {
    const res = await fetch(`/api/settings/colors/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur suppression');
    }
    showToast('Couleur supprimée', 'info');
    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteOrderInSettings(orderNumber) {
  if (!confirm(`Supprimer définitivement la commande "${orderNumber}" ?`)) return;

  try {
    const res = await fetch(`/api/orders/${orderNumber}`, { method: 'DELETE' });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur');

    showToast(result.message || 'Commande supprimée', 'info');
    await loadSettingsOrders();
    await loadOrdersList();
    refreshDashboard();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

// =========================================================================
// 7. GESTION DU NUANCIER ET COULEURS RAL DANS PARAMÈTRES
// =========================================================================

function renderSettingsColors(colors) {
  const list = document.getElementById('settingsColorsList');
  const badge = document.getElementById('colorsCountBadge');
  const colorsList = colors || AppState.colors || [];

  if (badge) badge.textContent = colorsList.length;
  if (!list) return;

  if (colorsList.length === 0) {
    list.innerHTML = '<li class="text-slate-400 italic py-2 text-center">Aucune couleur enregistrée</li>';
    return;
  }

  list.innerHTML = colorsList.map(c => `
    <li class="flex items-center justify-between p-2 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-5 h-5 rounded-full border border-slate-300 dark:border-slate-600 shadow-sm shrink-0" style="background-color: ${c.hex_code || '#474a51'};"></div>
        <div class="min-w-0">
          <div class="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">${c.name}</div>
          <div class="text-[10px] font-mono text-slate-400 font-semibold">${c.ral_code ? c.ral_code : ''} ${c.hex_code ? '• ' + c.hex_code : ''}</div>
        </div>
      </div>
      <button onclick="handleDeleteColor(${c.id}, '${c.name.replace(/'/g, "\\'")}')" class="p-1 rounded-lg text-slate-400 hover:text-rose-600 transition-colors" title="Supprimer">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </li>
  `).join('');

  lucide.createIcons();
}

async function handleAddColor(e) {
  e.preventDefault();
  const nameInput = document.getElementById('newColorName');
  const ralInput = document.getElementById('newColorRal');
  const hexInput = document.getElementById('newColorHex');

  const name = nameInput ? nameInput.value.trim() : '';
  const ral = ralInput ? ralInput.value.trim() : '';
  const hex = hexInput ? hexInput.value.trim() : '#474a51';

  if (!name) return;

  try {
    const res = await fetch('/api/settings/colors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ral_code: ral, hex_code: hex })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur ajout couleur');

    showToast(`Couleur "${result.name}" ajoutée avec succès !`, 'success');
    if (nameInput) nameInput.value = '';
    if (ralInput) ralInput.value = '';

    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

async function handleDeleteColor(id, name) {
  if (!confirm(`Supprimer la couleur "${name}" ?`)) return;
  try {
    const res = await fetch(`/api/settings/colors/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur suppression');
    }
    showToast('Couleur supprimée', 'info');
    await loadGlobalSettings();
    if (typeof loadSettingsData === 'function') await loadSettingsData();
  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}
