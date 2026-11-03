// =========================================================================
// GESTION DE L'INVENTAIRE CROISÉ & ANOMALIES (DOUBLE COMPTAGE 2 PERSONNES)
// =========================================================================

const InventoryState = {
  items: [],
  anomalies: [],
  currentSubTab: 'counting', // 'counting' ou 'anomalies'
  person1GlobalName: 'Opérateur 1',
  person2GlobalName: 'Opérateur 2',
  searchQuery: '',
  statusFilter: 'ALL',
  selectedOnly: false,
  selectedVariantIds: new Set(),
  pendingChanges: new Map(), // variant_id -> { count1, count2 }
  currentAdjustVariant: null,
  debounceTimer: null
};

// Initialisation au chargement de l'onglet
async function loadInventoryData() {
  await fetchInventoryItems();
  if (InventoryState.currentSubTab === 'anomalies') {
    await fetchInventoryAnomalies();
  }
}

// Bascule entre sous-onglets Inventaire
function switchInventorySubTab(subTab) {
  InventoryState.currentSubTab = subTab;
  const tabCounting = document.getElementById('inventorySubTabCounting');
  const tabAnomalies = document.getElementById('inventorySubTabAnomalies');
  const btnCounting = document.getElementById('btnSubTabCounting');
  const btnAnomalies = document.getElementById('btnSubTabAnomalies');

  if (subTab === 'counting') {
    tabCounting?.classList.remove('hidden');
    tabAnomalies?.classList.add('hidden');
    btnCounting?.classList.add('bg-indigo-600', 'text-white', 'shadow-sm');
    btnCounting?.classList.remove('text-slate-600', 'dark:text-slate-400', 'hover:bg-slate-100', 'dark:hover:bg-slate-800');
    btnAnomalies?.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm');
    btnAnomalies?.classList.add('text-slate-600', 'dark:text-slate-400', 'hover:bg-slate-100', 'dark:hover:bg-slate-800');
    fetchInventoryItems();
  } else {
    tabCounting?.classList.add('hidden');
    tabAnomalies?.classList.remove('hidden');
    btnAnomalies?.classList.add('bg-indigo-600', 'text-white', 'shadow-sm');
    btnAnomalies?.classList.remove('text-slate-600', 'dark:text-slate-400', 'hover:bg-slate-100', 'dark:hover:bg-slate-800');
    btnCounting?.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm');
    btnCounting?.classList.add('text-slate-600', 'dark:text-slate-400', 'hover:bg-slate-100', 'dark:hover:bg-slate-800');
    fetchInventoryAnomalies();
  }
  lucide.createIcons();
}

// Récupération des articles pour l'inventaire
async function fetchInventoryItems() {
  const searchInput = document.getElementById('inventorySearchInput');
  const statusSelect = document.getElementById('inventoryFilterStatus');
  const p1Input = document.getElementById('inventoryGlobalPerson1');
  const p2Input = document.getElementById('inventoryGlobalPerson2');

  InventoryState.searchQuery = searchInput?.value.trim() || '';
  InventoryState.statusFilter = statusSelect?.value || 'ALL';
  if (p1Input && p1Input.value.trim()) InventoryState.person1GlobalName = p1Input.value.trim();
  if (p2Input && p2Input.value.trim()) InventoryState.person2GlobalName = p2Input.value.trim();

  const params = new URLSearchParams();
  if (InventoryState.searchQuery) params.append('search', InventoryState.searchQuery);
  if (InventoryState.statusFilter && InventoryState.statusFilter !== 'ALL') {
    params.append('status', InventoryState.statusFilter);
  }
  if (InventoryState.selectedOnly) {
    params.append('selected_only', 'true');
  }

  try {
    const res = await fetch(`/api/inventory/items?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur récupération articles inventaire');
    const data = await res.json();
    InventoryState.items = data.items || [];
    renderInventoryStats(data.stats);
    renderInventoryTable(InventoryState.items);
  } catch (err) {
    console.error('Erreur fetchInventoryItems:', err);
    showToast('Erreur de chargement des articles d\'inventaire', 'error');
  }
}

// Mise à jour des cartes statistiques
function renderInventoryStats(stats) {
  if (!stats) return;
  const totalEl = document.getElementById('invStatTotal');
  const anomaliesEl = document.getElementById('invStatAnomalies');
  const conformeEl = document.getElementById('invStatConforme');
  const notInvEl = document.getElementById('invStatNotInventoried');
  const badgeAnomaliesTab = document.getElementById('badgeSubTabAnomalies');

  if (totalEl) totalEl.textContent = stats.total || 0;
  if (anomaliesEl) anomaliesEl.textContent = stats.total_anomalies || 0;
  if (conformeEl) conformeEl.textContent = stats.conforme || 0;
  if (notInvEl) notInvEl.textContent = stats.not_inventoried || 0;
  if (badgeAnomaliesTab) {
    badgeAnomaliesTab.textContent = stats.adjusted || 0;
  }
}

// Rendu du tableau d'inventaire
function renderInventoryTable(items) {
  const tbody = document.getElementById('inventoryTableBody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="p-8 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center gap-2">
            <i data-lucide="clipboard-list" class="w-8 h-8 text-slate-400"></i>
            <span>Aucun profilé ne correspond aux critères de filtre ou de recherche.</span>
          </div>
        </td>
      </tr>
    `;
    lucide.createIcons();
    return;
  }

  let html = '';
  items.forEach(item => {
    const vId = item.variant_id;
    const isSelected = InventoryState.selectedVariantIds.has(vId) || item.is_selected;
    const isRed = item.is_red;

    // Classe de ligne (Rouge vif si désaccord entre les deux ou écart avec stock réel)
    let rowBgClass = 'hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors';
    if (isRed) {
      rowBgClass = 'bg-rose-50/70 dark:bg-rose-950/30 border-l-4 border-l-rose-500 font-medium text-rose-950 dark:text-rose-100';
    } else if (item.status === 'CONFORME') {
      rowBgClass = 'bg-emerald-50/40 dark:bg-emerald-950/20 border-l-4 border-l-emerald-500';
    }

    // Badge de statut d'inventaire
    let statusBadge = '';
    if (item.status === 'DISCREPANCY_PERSONS') {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 border border-rose-300 dark:border-rose-700">
          <i data-lucide="alert-triangle" class="w-3.5 h-3.5 text-rose-600"></i>
          Désaccord (P1 ≠ P2)
        </span>
      `;
    } else if (item.status === 'DISCREPANCY_STOCK') {
      const diffFormatted = (item.discrepancy_diff > 0 ? '+' : '') + item.discrepancy_diff;
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 border border-rose-300 dark:border-rose-700">
          <i data-lucide="alert-circle" class="w-3.5 h-3.5 text-rose-600"></i>
          Écart Stock (${diffFormatted})
        </span>
      `;
    } else if (item.status === 'RECOUNT_NEEDED') {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200 border border-amber-300 dark:border-amber-700">
          <i data-lucide="rotate-ccw" class="w-3.5 h-3.5 text-amber-600"></i>
          Recomptage Requis
        </span>
      `;
    } else if (item.status === 'CONFORME') {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">
          <i data-lucide="check-circle" class="w-3.5 h-3.5 text-emerald-600"></i>
          Conforme
        </span>
      `;
    } else if (item.status === 'ADJUSTED') {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200">
          <i data-lucide="check-check" class="w-3.5 h-3.5 text-blue-600"></i>
          Mis à niveau
        </span>
      `;
    } else if (item.status === 'IN_PROGRESS') {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
          <i data-lucide="clock" class="w-3.5 h-3.5 text-amber-500"></i>
          Comptage 1/2
        </span>
      `;
    } else {
      statusBadge = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          <i data-lucide="help-circle" class="w-3.5 h-3.5 text-slate-400"></i>
          Non inventorié
        </span>
      `;
    }

    // Date du dernier inventaire
    let dateDisplay = '';
    if (item.last_inventory_date) {
      dateDisplay = `<span class="text-xs font-mono font-medium text-slate-700 dark:text-slate-300">${item.last_inventory_date.substring(0, 16)}</span>`;
    } else {
      dateDisplay = `<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-500 italic">Pas passé par inventaire</span>`;
    }

    // Valeurs courantes de comptage
    const count1Val = item.count1 !== null && item.count1 !== undefined ? item.count1 : '';
    const count2Val = item.count2 !== null && item.count2 !== undefined ? item.count2 : '';

    html += `
      <tr id="inv-row-${vId}" class="${rowBgClass} border-b border-slate-200/80 dark:border-slate-800">
        <!-- Checkbox de sélection pour lancer inventaire -->
        <td class="p-3 text-center">
          <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectInventoryItem(${vId}, this.checked)" class="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer">
        </td>

        <!-- Réf & Désignation -->
        <td class="p-3">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center font-bold text-xs text-slate-700 dark:text-slate-300 shrink-0 border border-slate-200 dark:border-slate-700">
              ${item.reference.substring(0, 3)}
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-sm tracking-tight text-slate-900 dark:text-white font-mono">${item.reference}</span>
                <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500">${item.unit}</span>
              </div>
              <p class="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[200px]" title="${item.designation}">${item.designation}</p>
            </div>
          </div>
        </td>

        <!-- Couleur & Casier -->
        <td class="p-3">
          <div class="flex items-center gap-2">
            <span class="w-3.5 h-3.5 rounded-full border border-slate-300 dark:border-slate-600 shrink-0 shadow-sm" style="background-color: ${item.color_hex};"></span>
            <span class="font-medium text-xs text-slate-800 dark:text-slate-200">${item.color}</span>
          </div>
          <div class="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1">
            <i data-lucide="map-pin" class="w-3 h-3 text-slate-400"></i>
            <span>${item.location}</span>
          </div>
        </td>

        <!-- Quantité Réelle en Stock -->
        <td class="p-3 text-right">
          <div class="font-mono font-extrabold text-sm text-slate-900 dark:text-white">${item.real_quantity}</div>
          <div class="text-[10px] text-slate-400">PMP: ${formatMoney(item.pmp)}</div>
        </td>

        <!-- Date Dernier Inventaire -->
        <td class="p-3 text-center">
          ${dateDisplay}
        </td>

        <!-- Case Quantité Personne 1 -->
        <td class="p-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between text-[11px] text-slate-500 font-medium">
              <span id="p1-label-${vId}">${item.person1_name || InventoryState.person1GlobalName}</span>
            </div>
            <input 
              type="number" 
              step="any" 
              min="0" 
              id="input-p1-${vId}" 
              value="${count1Val}" 
              placeholder="Qté P1"
              oninput="onCountInputChange(${vId}, ${item.real_quantity})"
              class="w-24 sm:w-28 px-2.5 py-1.5 text-sm font-mono font-bold rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 shadow-sm transition-all"
            >
          </div>
        </td>

        <!-- Case Quantité Personne 2 -->
        <td class="p-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between text-[11px] text-slate-500 font-medium">
              <span id="p2-label-${vId}">${item.person2_name || InventoryState.person2GlobalName}</span>
            </div>
            <input 
              type="number" 
              step="any" 
              min="0" 
              id="input-p2-${vId}" 
              value="${count2Val}" 
              placeholder="Qté P2"
              oninput="onCountInputChange(${vId}, ${item.real_quantity})"
              class="w-24 sm:w-28 px-2.5 py-1.5 text-sm font-mono font-bold rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 shadow-sm transition-all"
            >
          </div>
        </td>

        <!-- Statut & Alerte Anomalie -->
        <td class="p-3 text-center" id="status-cell-${vId}">
          ${statusBadge}
        </td>

        <!-- Actions Rapides -->
        <td class="p-3 text-right">
          <div class="flex items-center justify-end gap-1.5">
            <!-- Bouton Sauvegarder ce comptage -->
            <button 
              onclick="saveSingleInventoryCount(${vId})" 
              class="p-2 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 dark:bg-indigo-950/60 dark:text-indigo-300 hover:scale-105 transition-transform" 
              title="Enregistrer ce comptage"
            >
              <i data-lucide="save" class="w-4 h-4"></i>
            </button>

            <!-- Bouton Refaire l'inventaire (Recomptage) -->
            <button 
              onclick="recountInventoryItemPrompt(${vId})" 
              class="p-2 rounded-lg bg-amber-50 text-amber-600 hover:bg-amber-100 dark:bg-amber-950/60 dark:text-amber-300 hover:scale-105 transition-transform" 
              title="Refaire l'inventaire (Recomptage)"
            >
              <i data-lucide="rotate-ccw" class="w-4 h-4"></i>
            </button>

            <!-- Bouton Mettre à niveau le stock (Arbitrage anomalie) -->
            <button 
              onclick="openAdjustStockModal(${vId})" 
              class="px-2.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-sm flex items-center gap-1 hover:scale-105 transition-transform" 
              title="Mettre à niveau le stock vers la quantité d'inventaire"
            >
              <i data-lucide="scale" class="w-3.5 h-3.5"></i>
              <span class="hidden sm:inline">Mettre à niveau</span>
            </button>
          </div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  lucide.createIcons();
}

// Calcul en temps réel lors de la frappe dans les inputs P1 et P2
function onCountInputChange(variantId, realQuantity) {
  const p1Input = document.getElementById(`input-p1-${variantId}`);
  const p2Input = document.getElementById(`input-p2-${variantId}`);
  const row = document.getElementById(`inv-row-${variantId}`);
  const statusCell = document.getElementById(`status-cell-${variantId}`);

  if (!p1Input || !p2Input || !row || !statusCell) return;

  const v1 = p1Input.value.trim() !== '' ? parseFloat(p1Input.value) : null;
  const v2 = p2Input.value.trim() !== '' ? parseFloat(p2Input.value) : null;
  const rq = parseFloat(realQuantity);

  // Mémoriser le changement
  InventoryState.pendingChanges.set(variantId, { count1: v1, count2: v2 });

  // Règle d'or : si les deux calculs ne correspondent pas entre eux OU ne correspondent pas avec la quantité réelle
  // l'article se met en rouge
  if (v1 !== null && v2 !== null) {
    if (v1 !== v2) {
      // Désaccord P1 != P2
      row.className = 'bg-rose-50 dark:bg-rose-950/40 border-l-4 border-l-rose-500 font-medium text-rose-950 dark:text-rose-100 border-b border-slate-200/80 dark:border-slate-800';
      statusCell.innerHTML = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 border border-rose-300 dark:border-rose-700">
          <i data-lucide="alert-triangle" class="w-3.5 h-3.5 text-rose-600"></i>
          Désaccord (P1 ≠ P2)
        </span>
      `;
    } else if (v1 !== rq) {
      // Accord entre P1 et P2 mais différent du stock réel
      const diff = v1 - rq;
      const diffFormatted = (diff > 0 ? '+' : '') + diff;
      row.className = 'bg-rose-50 dark:bg-rose-950/40 border-l-4 border-l-rose-500 font-medium text-rose-950 dark:text-rose-100 border-b border-slate-200/80 dark:border-slate-800';
      statusCell.innerHTML = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 border border-rose-300 dark:border-rose-700">
          <i data-lucide="alert-circle" class="w-3.5 h-3.5 text-rose-600"></i>
          Écart Stock (${diffFormatted})
        </span>
      `;
    } else {
      // Conforme parfait
      row.className = 'bg-emerald-50/40 dark:bg-emerald-950/20 border-l-4 border-l-emerald-500 border-b border-slate-200/80 dark:border-slate-800';
      statusCell.innerHTML = `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">
          <i data-lucide="check-circle" class="w-3.5 h-3.5 text-emerald-600"></i>
          Conforme
        </span>
      `;
    }
  } else if (v1 !== null || v2 !== null) {
    row.className = 'hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors border-b border-slate-200/80 dark:border-slate-800';
    statusCell.innerHTML = `
      <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
        <i data-lucide="clock" class="w-3.5 h-3.5 text-amber-500"></i>
        Comptage 1/2
      </span>
    `;
  }
  lucide.createIcons();
}

// Recherche avec debounce
function debounceInventorySearch() {
  clearTimeout(InventoryState.debounceTimer);
  InventoryState.debounceTimer = setTimeout(() => {
    fetchInventoryItems();
  }, 250);
}

// Changement de filtre d'état
function onInventoryStatusFilterChange() {
  fetchInventoryItems();
}

// Sélection / Désélection d'un article
function toggleSelectInventoryItem(variantId, isChecked) {
  if (isChecked) {
    InventoryState.selectedVariantIds.add(variantId);
  } else {
    InventoryState.selectedVariantIds.delete(variantId);
  }
}

// Sélectionner tous les articles visibles
function selectAllFilteredInventory(isChecked) {
  document.querySelectorAll('#inventoryTableBody input[type="checkbox"]').forEach(cb => {
    cb.checked = isChecked;
  });
  InventoryState.items.forEach(it => {
    if (isChecked) {
      InventoryState.selectedVariantIds.add(it.variant_id);
    } else {
      InventoryState.selectedVariantIds.delete(it.variant_id);
    }
  });
}

// Lancer l'inventaire sur les articles sélectionnés
async function launchInventoryForSelection() {
  if (InventoryState.selectedVariantIds.size === 0) {
    showToast('Veuillez cocher au moins un article dans la liste pour lancer l\'inventaire ciblé.', 'warning');
    return;
  }

  const ids = Array.from(InventoryState.selectedVariantIds);
  try {
    const res = await fetch('/api/inventory/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variant_ids: ids, is_selected: true })
    });
    if (res.ok) {
      showToast(`Inventaire initié pour ${ids.length} article(s) sélectionné(s).`, 'success');
      InventoryState.selectedOnly = true;
      const btnFilterSel = document.getElementById('btnFilterOnlySelected');
      if (btnFilterSel) {
        btnFilterSel.classList.add('bg-indigo-600', 'text-white');
        btnFilterSel.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-700', 'dark:text-slate-300');
      }
      fetchInventoryItems();

      // Proposer immédiatement la génération du document d'inventaire
      setTimeout(() => {
        const wantPrint = confirm(`Inventaire lancé pour ${ids.length} article(s) sélectionné(s) !\n\nSouhaitez-vous générer et imprimer la fiche de comptage d'atelier maintenant ?`);
        if (wantPrint) {
          printInventorySheet(true);
        }
      }, 200);
    }
  } catch (err) {
    console.error('Erreur launchInventoryForSelection:', err);
    showToast('Erreur lors du lancement de l\'inventaire', 'error');
  }
}

// Génération et impression de la Fiche de Comptage d'Inventaire
function printInventorySheet(autoprint = false) {
  const p1Global = document.getElementById('inventoryGlobalPerson1')?.value.trim() || 'Opérateur 1';
  const p2Global = document.getElementById('inventoryGlobalPerson2')?.value.trim() || 'Opérateur 2';

  let selectedIds = Array.from(InventoryState.selectedVariantIds);

  // Si aucun n'est expressément coché, vérifier les articles actuellement affichés / filtrés
  if (selectedIds.length === 0) {
    if (InventoryState.items && InventoryState.items.length > 0) {
      const confirmAll = confirm(`Aucun article n'est spécifiquement coché.\n\nVoulez-vous générer la fiche d'inventaire pour les ${InventoryState.items.length} article(s) actuellement affichés ?`);
      if (!confirmAll) return;
      selectedIds = InventoryState.items.map(it => it.variant_id);
    } else {
      showToast('Aucun article à inclure dans la fiche d\'inventaire.', 'warning');
      return;
    }
  }

  const params = new URLSearchParams();
  params.set('variant_ids', selectedIds.join(','));
  params.set('person1', p1Global);
  params.set('person2', p2Global);
  if (autoprint) {
    params.set('autoprint', '1');
  }

  const printUrl = `/api/inventory/print-sheet?${params.toString()}`;
  window.open(printUrl, '_blank');
}

// Téléchargement direct du PDF vectoriel natif
function exportInventoryPdf(hideStock = false) {
  const p1Global = document.getElementById('inventoryGlobalPerson1')?.value.trim() || 'Opérateur 1';
  const p2Global = document.getElementById('inventoryGlobalPerson2')?.value.trim() || 'Opérateur 2';

  let selectedIds = Array.from(InventoryState.selectedVariantIds);
  if (selectedIds.length === 0) {
    if (InventoryState.items && InventoryState.items.length > 0) {
      selectedIds = InventoryState.items.map(it => it.variant_id);
    } else {
      showToast('Aucun article sélectionné pour l\'export PDF.', 'warning');
      return;
    }
  }

  const params = new URLSearchParams();
  params.set('variant_ids', selectedIds.join(','));
  params.set('person1', p1Global);
  params.set('person2', p2Global);
  if (hideStock) {
    params.set('hide_stock', 'true');
  }

  const pdfUrl = `/api/inventory/export-pdf?${params.toString()}`;
  window.open(pdfUrl, '_blank');
}

// Basculer l'affichage "Uniquement les sélectionnés"
function toggleOnlySelectedFilter() {
  InventoryState.selectedOnly = !InventoryState.selectedOnly;
  const btn = document.getElementById('btnFilterOnlySelected');
  if (btn) {
    if (InventoryState.selectedOnly) {
      btn.classList.add('bg-indigo-600', 'text-white');
      btn.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-700', 'dark:text-slate-300');
    } else {
      btn.classList.remove('bg-indigo-600', 'text-white');
      btn.classList.add('bg-white', 'dark:bg-slate-900', 'text-slate-700', 'dark:text-slate-300');
    }
  }
  fetchInventoryItems();
}

// Enregistrer le comptage d'une seule ligne
async function saveSingleInventoryCount(variantId) {
  const p1Input = document.getElementById(`input-p1-${variantId}`);
  const p2Input = document.getElementById(`input-p2-${variantId}`);
  const p1Global = document.getElementById('inventoryGlobalPerson1')?.value.trim() || 'Personne 1';
  const p2Global = document.getElementById('inventoryGlobalPerson2')?.value.trim() || 'Personne 2';

  const v1 = p1Input && p1Input.value.trim() !== '' ? parseFloat(p1Input.value) : null;
  const v2 = p2Input && p2Input.value.trim() !== '' ? parseFloat(p2Input.value) : null;

  if (v1 === null && v2 === null) {
    showToast('Veuillez saisir au moins un comptage pour enregistrer.', 'warning');
    return;
  }

  const payload = {
    items: [
      {
        variant_id: variantId,
        person1_name: p1Global,
        count1: v1,
        person2_name: p2Global,
        count2: v2
      }
    ],
    person1_name: p1Global,
    person2_name: p2Global
  };

  try {
    const res = await fetch('/api/inventory/save-counts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur enregistrement');

    showToast('Comptage enregistré avec succès.', 'success');
    InventoryState.pendingChanges.delete(variantId);
    fetchInventoryItems();
    refreshDashboard();
  } catch (err) {
    console.error('Erreur saveSingleInventoryCount:', err);
    showToast(err.message, 'error');
  }
}

// Enregistrer tous les comptages en une seule fois
async function saveAllInventoryCounts() {
  const p1Global = document.getElementById('inventoryGlobalPerson1')?.value.trim() || 'Personne 1';
  const p2Global = document.getElementById('inventoryGlobalPerson2')?.value.trim() || 'Personne 2';

  const itemsToSave = [];
  InventoryState.items.forEach(it => {
    const vId = it.variant_id;
    const p1Input = document.getElementById(`input-p1-${vId}`);
    const p2Input = document.getElementById(`input-p2-${vId}`);
    const v1 = p1Input && p1Input.value.trim() !== '' ? parseFloat(p1Input.value) : null;
    const v2 = p2Input && p2Input.value.trim() !== '' ? parseFloat(p2Input.value) : null;

    if (v1 !== null || v2 !== null) {
      itemsToSave.push({
        variant_id: vId,
        person1_name: p1Global,
        count1: v1,
        person2_name: p2Global,
        count2: v2
      });
    }
  });

  if (itemsToSave.length === 0) {
    showToast('Aucun comptage saisi à enregistrer.', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/inventory/save-counts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: itemsToSave,
        person1_name: p1Global,
        person2_name: p2Global
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur enregistrement global');

    showToast(result.message || 'Comptages enregistrés.', 'success');
    InventoryState.pendingChanges.clear();
    fetchInventoryItems();
    refreshDashboard();
  } catch (err) {
    console.error('Erreur saveAllInventoryCounts:', err);
    showToast(err.message, 'error');
  }
}

// Demande de recomptage / refaire l'inventaire
async function recountInventoryItemPrompt(variantId) {
  const item = InventoryState.items.find(i => i.variant_id === variantId);
  const refText = item ? `${item.reference} (${item.color})` : `l'article #${variantId}`;

  const confirmed = confirm(`Voulez-vous marquer ${refText} pour refaire l'inventaire (recomptage physique en atelier) ?\nLes anciens comptages seront réinitialisés.`);
  if (!confirmed) return;

  try {
    const res = await fetch('/api/inventory/recount', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        variant_id: variantId,
        notes: 'Recomptage demandé par opérateur'
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur demande recomptage');

    showToast(result.message || 'Demande de recomptage enregistrée.', 'success');
    fetchInventoryItems();
    refreshDashboard();
  } catch (err) {
    console.error('Erreur recountInventoryItemPrompt:', err);
    showToast(err.message, 'error');
  }
}

// =========================================================================
// MODALE DE MISE À NIVEAU DU STOCK VERS QUANTITÉ D'INVENTAIRE (ARBITRAGE)
// =========================================================================

function openAdjustStockModal(variantId) {
  const item = InventoryState.items.find(i => i.variant_id === variantId);
  if (!item) {
    showToast('Article introuvable.', 'error');
    return;
  }

  InventoryState.currentAdjustVariant = item;

  // Remplissage des champs de la modale
  const modal = document.getElementById('inventoryAdjustModal');
  const refEl = document.getElementById('adjustModalRef');
  const desEl = document.getElementById('adjustModalDesignation');
  const colorEl = document.getElementById('adjustModalColor');
  const stockEl = document.getElementById('adjustModalRealStock');
  const p1Btn = document.getElementById('adjustBtnChooseP1');
  const p2Btn = document.getElementById('adjustBtnChooseP2');
  const qtyInput = document.getElementById('adjustModalChosenQty');
  const reasonSelect = document.getElementById('adjustModalReasonSelect');
  const notesText = document.getElementById('adjustModalNotes');

  if (refEl) refEl.textContent = item.reference;
  if (desEl) desEl.textContent = `${item.designation} (${item.unit})`;
  if (colorEl) {
    colorEl.innerHTML = `
      <span class="w-3.5 h-3.5 rounded-full inline-block border border-slate-300 dark:border-slate-600 shadow-sm" style="background-color: ${item.color_hex};"></span>
      <span class="font-bold text-sm">${item.color} ${item.ral_code ? `(${item.ral_code})` : ''}</span>
    `;
  }
  if (stockEl) stockEl.textContent = `${item.real_quantity} ${item.unit}`;

  // Récupération des valeurs actuelles saisies ou enregistrées
  const p1Val = item.count1 !== null && item.count1 !== undefined ? item.count1 : '';
  const p2Val = item.count2 !== null && item.count2 !== undefined ? item.count2 : '';

  if (p1Btn) {
    p1Btn.textContent = `Retenir Personne 1 (${p1Val !== '' ? p1Val : '—'})`;
    p1Btn.onclick = () => { if (p1Val !== '') qtyInput.value = p1Val; calculateAdjustDiff(); };
  }
  if (p2Btn) {
    p2Btn.textContent = `Retenir Personne 2 (${p2Val !== '' ? p2Val : '—'})`;
    p2Btn.onclick = () => { if (p2Val !== '') qtyInput.value = p2Val; calculateAdjustDiff(); };
  }

  if (qtyInput) {
    qtyInput.value = p1Val !== '' ? p1Val : (p2Val !== '' ? p2Val : item.real_quantity);
  }
  if (reasonSelect) reasonSelect.value = '';
  if (notesText) notesText.value = '';

  calculateAdjustDiff();

  modal?.classList.remove('hidden');
  modal?.classList.add('flex');
  lucide.createIcons();
}

function closeAdjustStockModal() {
  const modal = document.getElementById('inventoryAdjustModal');
  modal?.classList.add('hidden');
  modal?.classList.remove('flex');
  InventoryState.currentAdjustVariant = null;
}

function calculateAdjustDiff() {
  const item = InventoryState.currentAdjustVariant;
  if (!item) return;

  const qtyInput = document.getElementById('adjustModalChosenQty');
  const diffDisplay = document.getElementById('adjustModalDiffDisplay');
  const finDisplay = document.getElementById('adjustModalFinancialImpact');

  const chosen = parseFloat(qtyInput?.value || 0);
  const diff = roundNum(chosen - item.real_quantity, 2);
  const fin = roundNum(diff * item.pmp, 2);

  if (diffDisplay) {
    const sign = diff > 0 ? '+' : '';
    diffDisplay.textContent = `${sign}${diff} ${item.unit}`;
    diffDisplay.className = diff < 0 
      ? 'font-bold font-mono text-rose-600 dark:text-rose-400'
      : (diff > 0 ? 'font-bold font-mono text-emerald-600 dark:text-emerald-400' : 'font-bold font-mono text-slate-500');
  }

  if (finDisplay) {
    finDisplay.textContent = formatMoney(fin);
  }
}

async function submitAdjustStock() {
  const item = InventoryState.currentAdjustVariant;
  if (!item) return;

  const qtyInput = document.getElementById('adjustModalChosenQty');
  const reasonSelect = document.getElementById('adjustModalReasonSelect');
  const customReasonInput = document.getElementById('adjustModalCustomReason');
  const notesText = document.getElementById('adjustModalNotes');
  const operatorInput = document.getElementById('adjustModalOperator');

  const chosenQty = parseFloat(qtyInput?.value);
  if (isNaN(chosenQty) || chosenQty < 0) {
    showToast('Quantité invalide. Doit être positive ou nulle.', 'warning');
    return;
  }

  let reason = reasonSelect?.value || '';
  if (reason === 'AUTRE' || !reason) {
    reason = customReasonInput?.value.trim() || '';
  }
  if (!reason || reason.length < 3) {
    showToast('Le motif de l\'anomalie est obligatoire pour enregistrer la mise à niveau.', 'warning');
    reasonSelect?.focus();
    return;
  }

  const payload = {
    variant_id: item.variant_id,
    chosen_quantity: chosenQty,
    reason: reason,
    notes: notesText?.value.trim() || '',
    operator: operatorInput?.value.trim() || 'Admin'
  };

  try {
    const res = await fetch('/api/inventory/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur mise à niveau');

    showToast(result.message || 'Mise à niveau du stock effectuée avec succès.', 'success');
    closeAdjustStockModal();
    fetchInventoryItems();
    refreshDashboard();
  } catch (err) {
    console.error('Erreur submitAdjustStock:', err);
    showToast(err.message, 'error');
  }
}

function onAdjustReasonSelectChange() {
  const select = document.getElementById('adjustModalReasonSelect');
  const customWrapper = document.getElementById('adjustCustomReasonWrapper');
  if (select?.value === 'AUTRE') {
    customWrapper?.classList.remove('hidden');
  } else {
    customWrapper?.classList.add('hidden');
  }
}

// =========================================================================
// SOUS-ONGLET 2 : HISTORIQUE DES ANOMALIES RÉGULARISÉES
// =========================================================================

async function fetchInventoryAnomalies() {
  const searchInput = document.getElementById('anomaliesSearchInput');
  const term = searchInput?.value.trim() || '';

  const params = new URLSearchParams();
  if (term) params.append('search', term);

  try {
    const res = await fetch(`/api/inventory/anomalies?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur chargement anomalies');
    const data = await res.json();
    InventoryState.anomalies = data.anomalies || [];
    renderAnomaliesTable(InventoryState.anomalies);
  } catch (err) {
    console.error('Erreur fetchInventoryAnomalies:', err);
    showToast('Erreur chargement historique des anomalies', 'error');
  }
}

function renderAnomaliesTable(anomalies) {
  const tbody = document.getElementById('anomaliesTableBody');
  if (!tbody) return;

  if (!anomalies || anomalies.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="p-8 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center gap-2">
            <i data-lucide="check-check" class="w-8 h-8 text-emerald-500"></i>
            <span>Aucune anomalie d'inventaire archivée. Toutes les mises à niveau sont régulières.</span>
          </div>
        </td>
      </tr>
    `;
    lucide.createIcons();
    return;
  }

  let html = '';
  anomalies.forEach(a => {
    const diffSign = a.discrepancy_quantity > 0 ? '+' : '';
    const diffColorClass = a.discrepancy_quantity < 0 
      ? 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/50 border-rose-200 dark:border-rose-800'
      : (a.discrepancy_quantity > 0 
        ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-800'
        : 'text-slate-600 bg-slate-50 border-slate-200');

    html += `
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40 border-b border-slate-200/80 dark:border-slate-800 transition-colors">
        <!-- Date -->
        <td class="p-3 text-xs font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap">
          ${a.created_at.substring(0, 16)}
        </td>

        <!-- Réf & Article -->
        <td class="p-3">
          <div class="flex items-center gap-2">
            <span class="font-bold text-sm font-mono text-slate-900 dark:text-white">${a.reference}</span>
            <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500">${a.unit}</span>
          </div>
          <p class="text-xs text-slate-500 truncate max-w-[200px]" title="${a.designation}">${a.designation}</p>
        </td>

        <!-- Couleur -->
        <td class="p-3">
          <div class="flex items-center gap-2">
            <span class="w-3 h-3 rounded-full border border-slate-300 dark:border-slate-600 shrink-0 shadow-sm" style="background-color: ${a.color_hex};"></span>
            <span class="font-medium text-xs text-slate-800 dark:text-slate-200">${a.color}</span>
          </div>
        </td>

        <!-- Quantité Avant vs Retenue -->
        <td class="p-3 text-right text-xs">
          <div class="text-slate-500">Avant: <span class="font-mono font-bold text-slate-700 dark:text-slate-300">${a.real_quantity_before}</span></div>
          <div class="text-slate-900 dark:text-white font-semibold">Mis à niveau: <span class="font-mono font-extrabold text-indigo-600 dark:text-indigo-400">${a.counted_quantity}</span></div>
        </td>

        <!-- Quantité d'anomalie (Écart) -->
        <td class="p-3 text-center">
          <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold font-mono border ${diffColorClass}">
            ${diffSign}${a.discrepancy_quantity} ${a.unit}
          </span>
        </td>

        <!-- Impact Financier -->
        <td class="p-3 text-right font-mono text-xs font-bold ${a.financial_impact < 0 ? 'text-rose-600' : 'text-slate-700 dark:text-slate-300'}">
          ${formatMoney(a.financial_impact)}
        </td>

        <!-- Motif Obligatoire de l'anomalie -->
        <td class="p-3">
          <span class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-800 dark:text-rose-200 border border-rose-200 dark:border-rose-900 block truncate max-w-[250px]" title="${a.reason}">
            ${a.reason}
          </span>
          ${a.notes ? `<p class="text-[11px] text-slate-400 mt-0.5 truncate max-w-[250px]" title="${a.notes}">${a.notes}</p>` : ''}
        </td>

        <!-- Opérateurs & Validateur -->
        <td class="p-3 text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
          <div class="flex items-center gap-1">
            <i data-lucide="users" class="w-3.5 h-3.5 text-slate-400"></i>
            <span>${a.person1_name || 'P1'} & ${a.person2_name || 'P2'}</span>
          </div>
          <div class="text-[11px] text-slate-400">Validé par: <span class="font-medium text-slate-600 dark:text-slate-300">${a.adjusted_by}</span></div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  lucide.createIcons();
}

function debounceAnomaliesSearch() {
  clearTimeout(InventoryState.debounceTimer);
  InventoryState.debounceTimer = setTimeout(() => {
    fetchInventoryAnomalies();
  }, 250);
}

// Fonction utilitaire d'arrondi
function roundNum(val, dec = 2) {
  const p = Math.pow(10, dec);
  return Math.round((Number(val) + Number.EPSILON) * p) / p;
}
