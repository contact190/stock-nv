let debounceTimer = null;

function setStockViewMode(mode) {
  AppState.stockViewMode = mode;
  const tableView = document.getElementById('stockTableView');
  const cardsView = document.getElementById('stockCardsView');
  const btnTable = document.getElementById('viewBtnTable');
  const btnCards = document.getElementById('viewBtnCards');

  if (mode === 'table') {
    tableView?.classList.remove('hidden');
    cardsView?.classList.add('hidden');
    btnTable?.classList.add('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-white', 'shadow-sm');
    btnTable?.classList.remove('text-slate-600', 'dark:text-slate-400');
    btnCards?.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-white', 'shadow-sm');
    btnCards?.classList.add('text-slate-600', 'dark:text-slate-400');
  } else {
    tableView?.classList.add('hidden');
    cardsView?.classList.remove('hidden');
    btnCards?.classList.add('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-white', 'shadow-sm');
    btnCards?.classList.remove('text-slate-600', 'dark:text-slate-400');
    btnTable?.classList.remove('bg-white', 'dark:bg-slate-900', 'text-slate-800', 'dark:text-white', 'shadow-sm');
    btnTable?.classList.add('text-slate-600', 'dark:text-slate-400');
  }
}

async function loadStockData() {
  const search = document.getElementById('stockSearchInput')?.value || '';
  const category = document.getElementById('stockFilterCategory')?.value || 'ALL';
  const gamme = document.getElementById('stockFilterGamme')?.value || 'ALL';
  const status = document.getElementById('stockFilterStatus')?.value || 'ALL';
  const chantier = document.getElementById('stockFilterChantier')?.value || 'ALL';

  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (category && category !== 'ALL') params.append('category', category);
  if (gamme && gamme !== 'ALL') params.append('gamme', gamme);
  if (status && status !== 'ALL') params.append('status', status);
  if (chantier && chantier !== 'ALL') params.append('chantier', chantier);

  try {
    const res = await fetch(`/api/stock?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur chargement stock');
    const products = await res.json();

    renderStockTable(products);
    renderStockCards(products);

  } catch (err) {
    console.error('Erreur loadStockData:', err);
    showToast('Erreur de chargement du stock', 'error');
  }
}

function debounceStockFilter() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => loadStockData(), 250);
}

function filterStock() {
  loadStockData();
}

function renderStockTable(products) {
  const tbody = document.getElementById('stockTableBody');
  if (!tbody) return;

  if (!products || products.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12" class="p-8 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center gap-2">
            <i data-lucide="package-search" class="w-8 h-8 text-slate-400"></i>
            <span>Aucun profilé ne correspond aux critères de recherche.</span>
          </div>
        </td>
      </tr>
    `;
    lucide.createIcons();
    updateTopScrollSync('stockTopScrollWrapper', 'stockTableScrollWrapper', 'stockTable', 'stockTopScrollContent');
    return;
  }

  let rowsHtml = '';

  products.forEach(p => {
    (p.variants || []).forEach(v => {
      let statusBadge = '';
      if (v.status === 'RUPTURE') {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300">Rupture</span>';
      } else if (v.status === 'STOCK_BAS') {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">Stock bas</span>';
      } else {
        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">En stock</span>';
      }

      const isUnassigned = v.location === 'EN_ATTENTE_AFFECTATION' || !v.location;

      const safeRef = encodeURIComponent(p.reference || '');
      const safeDesig = encodeURIComponent(p.designation || '');

      const imgHtml = p.image_url
        ? `<img src="${p.image_url}" onclick="openImagePreview('${p.image_url}', '${safeRef}', '${safeDesig}')" class="w-9 h-9 rounded-lg object-cover border border-slate-200 dark:border-slate-700 shrink-0 cursor-pointer hover:scale-110 hover:shadow-md transition-all ring-1 ring-slate-200 dark:ring-slate-700 hover:ring-indigo-500" alt="${p.reference}" title="Cliquer pour agrandir la photo">`
        : `<div class="w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-400 font-mono text-[10px] font-bold shrink-0">ALU</div>`;

      rowsHtml += `
        <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
          <td class="py-2.5 px-3">
            <div class="flex items-center gap-2.5">
              ${imgHtml}
              <div class="min-w-0">
                <div class="font-bold text-slate-900 dark:text-white truncate max-w-[220px] 2xl:max-w-none" title="${p.designation}">${p.designation}</div>
                <div class="text-[11px] font-mono text-indigo-600 font-semibold">${p.reference}</div>
              </div>
            </div>
          </td>

          <td class="py-2.5 px-3 text-slate-600 dark:text-slate-300">
            <div>${p.category}</div>
            <div class="text-[10px] text-slate-400">${p.gamme} • ${p.unit}</div>
          </td>

          <td class="py-2.5 px-3">
            <div class="flex items-center gap-2 font-medium">
              <span class="color-bubble" style="background-color: ${v.color_hex};"></span>
              <span class="font-semibold text-slate-800 dark:text-slate-200">${v.color}</span>
            </div>
          </td>

          <td class="py-2.5 px-2.5 text-right font-extrabold text-sm ${v.real_quantity <= v.threshold ? 'text-rose-600' : 'text-slate-900 dark:text-white'}">
            ${v.real_quantity} <span class="text-[10px] font-normal text-slate-400">${p.unit}</span>
          </td>

          <td class="py-2.5 px-2 text-right font-semibold text-amber-600">
            ${v.reserved_quantity > 0 ? v.reserved_quantity : '-'}
          </td>

          <td class="py-2.5 px-2.5 text-right font-bold text-emerald-600">
            ${v.available_quantity}
          </td>

          <td class="py-2.5 px-2 text-right text-slate-500 font-medium">
            ${v.threshold}
          </td>

          <!-- PMP OBLIGATOIRE (DZD) -->
          <td class="py-2.5 px-2.5 text-right font-bold text-emerald-600 dark:text-emerald-400">
            <button onclick="openVariantDetailsModal(${v.id})" class="hover:underline flex items-center justify-end gap-1 ml-auto" title="Voir l'historique de calcul PMP">
              <span>${formatMoney(v.pmp)}</span>
              <i data-lucide="info" class="w-3 h-3 text-emerald-500"></i>
            </button>
          </td>

          <td class="py-2.5 px-2.5 text-right text-slate-400">
            ${v.current_price > 0 ? formatMoney(v.current_price) : '-'}
          </td>

          <!-- Casier / Emplacement -->
          <td class="py-2.5 px-2.5 text-xs">
            ${isUnassigned ? '<span class="px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800 text-[10px]">EN_ATTENTE_AFFECTATION</span>' : `<span class="font-mono text-slate-700 dark:text-slate-300">${v.location}</span>`}
          </td>

          <td class="py-2.5 px-2 text-center">${statusBadge}</td>

          <td class="py-2.5 px-2 text-center">
            <div class="flex items-center justify-center gap-1">
              <button onclick="quickAction('stock', ${v.id}, '${p.reference}', '${v.color}')" class="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950 text-indigo-600 hover:bg-indigo-100" title="Stocker (+)">
                <i data-lucide="plus" class="w-3.5 h-3.5"></i>
              </button>
              <button onclick="quickAction('destock', ${v.id}, '${p.reference}', '${v.color}')" class="p-1.5 rounded-lg bg-rose-50 dark:bg-rose-950 text-rose-600 hover:bg-rose-100" title="Déstocker (-)">
                <i data-lucide="minus" class="w-3.5 h-3.5"></i>
              </button>
              <button onclick="quickAction('reserve', ${v.id}, '${p.reference}', '${v.color}')" class="p-1.5 rounded-lg bg-amber-50 dark:bg-amber-950 text-amber-600 hover:bg-amber-100" title="Réserver Chantier (🔒)">
                <i data-lucide="lock" class="w-3.5 h-3.5"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    });
  });

  tbody.innerHTML = rowsHtml;
  lucide.createIcons();
  updateTopScrollSync('stockTopScrollWrapper', 'stockTableScrollWrapper', 'stockTable', 'stockTopScrollContent');
}

function renderStockCards(products) {
  const container = document.getElementById('stockCardsView');
  if (!container) return;

  if (!products || products.length === 0) {
    container.innerHTML = `<div class="col-span-full p-8 text-center text-slate-400 glass-panel rounded-2xl">Aucun profilé trouvé.</div>`;
    return;
  }

  container.innerHTML = products.map(p => {
    const variantsHtml = (p.variants || []).map(v => {
      const isLow = v.real_quantity <= v.threshold;
      const bcode = v.barcode || `BAR-${p.reference}-${v.color.substring(0,3).toUpperCase()}`;

      return `
        <div class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 space-y-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="color-bubble" style="background-color: ${v.color_hex};"></span>
              <span class="font-bold text-xs text-slate-900 dark:text-white">${v.color}</span>
            </div>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${isLow ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}">
              ${v.real_quantity} ${p.unit}
            </span>
          </div>

          <div class="grid grid-cols-3 gap-1 text-[11px] text-slate-500 pt-1 border-t border-slate-100 dark:border-slate-800">
            <div>Dispo: <b class="text-emerald-600">${v.available_quantity}</b></div>
            <div>Réservé: <b class="text-amber-600">${v.reserved_quantity}</b></div>
            <div>PMP: <b class="text-emerald-600">${formatMoney(v.pmp)}</b></div>
          </div>

          <div class="flex items-center justify-between pt-1">
            <div class="text-[10px] text-slate-400 font-mono">
              ${v.location || 'EN_ATTENTE_AFFECTATION'}
            </div>
            <div class="flex items-center gap-1">
              <button onclick="quickAction('stock', ${v.id}, '${p.reference}', '${v.color}')" class="px-2 py-1 rounded bg-indigo-50 text-indigo-600 font-bold text-xs">+ Entrée</button>
              <button onclick="quickAction('destock', ${v.id}, '${p.reference}', '${v.color}')" class="px-2 py-1 rounded bg-rose-50 text-rose-600 font-bold text-xs">- Débit</button>
              <button onclick="quickAction('reserve', ${v.id}, '${p.reference}', '${v.color}')" class="px-2 py-1 rounded bg-amber-50 text-amber-600 font-bold text-xs">🔒</button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    const safeRef = encodeURIComponent(p.reference || '');
    const safeDesig = encodeURIComponent(p.designation || '');

    const cardImgHtml = p.image_url
      ? `<img src="${p.image_url}" onclick="openImagePreview('${p.image_url}', '${safeRef}', '${safeDesig}')" class="w-12 h-12 rounded-xl object-cover border border-slate-200 dark:border-slate-700 shrink-0 cursor-pointer hover:scale-105 hover:shadow-md transition-all ring-1 ring-slate-200 dark:ring-slate-700 hover:ring-indigo-500" alt="${p.reference}" title="Cliquer pour agrandir la photo">`
      : `<div class="w-12 h-12 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-400 font-mono text-xs font-bold shrink-0">ALU</div>`;

    return `
      <div class="glass-panel p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-3">
        <div class="flex items-center gap-3">
          ${cardImgHtml}
          <div class="flex-1 min-w-0">
            <h3 class="font-bold text-slate-900 dark:text-white truncate">${p.designation}</h3>
            <div class="text-xs text-indigo-600 font-mono font-semibold">${p.reference}</div>
            <div class="text-[11px] text-slate-500">${p.category} • Valeur stock: <b>${formatMoney(p.total_value)}</b></div>
          </div>
        </div>

        <div class="space-y-2 pt-1">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Déclinaisons de Teinte (${(p.variants || []).length})</div>
          ${variantsHtml}
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

function quickAction(actionType, variantId, reference, color) {
  switchTab('actions');
  if (actionType === 'stock') {
    selectActionSubTab('stocker');
    const inSelect = document.getElementById('stockInVariantSelect');
    if (inSelect) {
      inSelect.value = variantId;
      onStockInVariantSelectChange();
    }
  } else if (actionType === 'destock') {
    selectActionSubTab('destocker');
    const destockSelect = document.getElementById('destockVariantSelect');
    if (destockSelect) {
      destockSelect.value = variantId;
      onDestockVariantChange();
    }
  } else if (actionType === 'reserve') {
    selectActionSubTab('reserver');
    const resSelect = document.getElementById('reserveVariantSelect');
    if (resSelect) {
      resSelect.value = variantId;
      onReserveVariantChange();
    }
  }
}

// Modal Code-Barres (Désactivé)
function showBarcodeModal() {}
function closeBarcodeModal() {}

// Redirection vers le formulaire complet [ ✨ CRÉER ]
function openNewCatalogModal() {
  switchTab('actions');
  selectActionSubTab('creer');
}

function closeNewCatalogModal() {
  document.getElementById('modalNewCatalog')?.classList.add('hidden');
}

async function handleCreateCatalogSubmit(e) {
  e.preventDefault();

  const payload = {
    reference: document.getElementById('catNewRef').value.trim(),
    designation: document.getElementById('catNewDesignation').value.trim(),
    category: document.getElementById('catNewCategory').value,
    gamme: document.getElementById('catNewGamme').value,
    unit: document.getElementById('catNewUnit').value,
    color: document.getElementById('catNewColor').value.trim(),
    color_hex: document.getElementById('catNewColorHex').value,
    initial_quantity: parseFloat(document.getElementById('catNewInitialQty').value) || 0,
    unit_price: parseFloat(document.getElementById('catNewPrice').value) || 0,
    threshold: parseFloat(document.getElementById('catNewThreshold').value) || 15,
    location: document.getElementById('catNewLocation').value.trim() || 'EN_ATTENTE_AFFECTATION',
    barcode: document.getElementById('catNewBarcode')?.value?.trim() || null
  };

  try {
    const res = await fetch('/api/stock/catalog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur création au catalogue');

    showToast(`✅ ${result.message}`, 'success');
    closeNewCatalogModal();

    await loadReferencesForSelects();
    loadStockData();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

// Modal Détails de variante et historique PMP
async function openVariantDetailsModal(variantId) {
  try {
    const res = await fetch(`/api/stock/variant/${variantId}`);
    if (!res.ok) throw new Error('Erreur');
    const data = await res.json();
    const v = data.variant;
    const history = data.price_history || [];

    document.getElementById('modalVariantTitle').textContent = `${v.designation} (${v.color})`;
    document.getElementById('modalVariantSubtitle').textContent = `Réf: ${v.product_reference} • ${v.category} (${v.gamme})`;
    document.getElementById('modalVariantColorDot').style.backgroundColor = v.color_hex || '#64748b';

    document.getElementById('modalPrevPrice').textContent = formatMoney(v.previous_price);
    document.getElementById('modalPmpPrice').textContent = formatMoney(v.pmp);
    document.getElementById('modalLocationVal').textContent = v.location || 'EN_ATTENTE_AFFECTATION';

    const histTbody = document.getElementById('modalPriceHistoryList');
    if (history.length === 0) {
      histTbody.innerHTML = '<tr><td colspan="4" class="p-3 text-center text-slate-400">Aucun historique disponible</td></tr>';
    } else {
      histTbody.innerHTML = history.map(h => `
        <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40">
          <td class="p-2 font-mono text-[11px] text-slate-600 dark:text-slate-300">${h.recorded_at}</td>
          <td class="p-2 text-right font-medium">${h.quantity}</td>
          <td class="p-2 text-right font-bold text-slate-800 dark:text-slate-200">${formatMoney(h.price)}</td>
          <td class="p-2 text-right font-bold text-emerald-600">${formatMoney(h.pmp_after)}</td>
        </tr>
      `).join('');
    }

    document.getElementById('modalVariantDetails')?.classList.remove('hidden');
    lucide.createIcons();

  } catch (err) {
    console.error('Erreur openVariantDetailsModal:', err);
    showToast('Impossible de charger les détails', 'error');
  }
}

function closeVariantDetailsModal() {
  document.getElementById('modalVariantDetails')?.classList.add('hidden');
}

// Synchronisation du scroll horizontal supérieur et inférieur (masqué automatiquement si aucun scroll nécessaire)
function updateTopScrollSync(topWrapperId, tableWrapperId, tableId, contentId) {
  const topWrapper = document.getElementById(topWrapperId);
  const tableWrapper = document.getElementById(tableWrapperId);
  const table = document.getElementById(tableId);
  const content = document.getElementById(contentId);
  if (!topWrapper || !tableWrapper || !table || !content) return;

  const adjustWidth = () => {
    content.style.width = table.scrollWidth + 'px';
    const isOverflowing = table.scrollWidth > (tableWrapper.clientWidth + 4);
    topWrapper.style.display = isOverflowing ? 'block' : 'none';
  };

  requestAnimationFrame(adjustWidth);

  if (!topWrapper._synced) {
    topWrapper.addEventListener('scroll', () => {
      if (topWrapper._isSyncing) return;
      tableWrapper._isSyncing = true;
      tableWrapper.scrollLeft = topWrapper.scrollLeft;
      requestAnimationFrame(() => { tableWrapper._isSyncing = false; });
    });

    tableWrapper.addEventListener('scroll', () => {
      if (tableWrapper._isSyncing) return;
      topWrapper._isSyncing = true;
      topWrapper.scrollLeft = tableWrapper.scrollLeft;
      requestAnimationFrame(() => { topWrapper._isSyncing = false; });
    });

    window.addEventListener('resize', adjustWidth);
    topWrapper._synced = true;
  }
}

// =========================================================================
// POPUP PRÉVISUALISATION GRANDE IMAGE (AVEC RÉFÉRENCE ET DÉSIGNATION)
// =========================================================================

function openImagePreview(imageUrl, encodedRef, encodedDesignation) {
  if (!imageUrl) return;

  const modal = document.getElementById('modalImagePreview');
  const imgEl = document.getElementById('previewModalImg');
  const refEl = document.getElementById('previewModalRef');
  const desEl = document.getElementById('previewModalDesignation');
  const linkEl = document.getElementById('previewModalOpenTab');

  const ref = decodeURIComponent(encodedRef || '');
  const des = decodeURIComponent(encodedDesignation || '');

  if (imgEl) {
    imgEl.src = imageUrl;
    imgEl.alt = `${ref} - ${des}`;
  }
  if (refEl) refEl.textContent = ref;
  if (desEl) desEl.textContent = des;
  if (linkEl) linkEl.href = imageUrl;

  modal?.classList.remove('hidden');
  modal?.classList.add('flex');
  if (window.lucide) lucide.createIcons();
}

function closeImagePreview() {
  const modal = document.getElementById('modalImagePreview');
  modal?.classList.add('hidden');
  modal?.classList.remove('flex');
}

function handleImagePreviewBackdropClick(event) {
  if (event.target.id === 'modalImagePreview') {
    closeImagePreview();
  }
}

// Raccourci touche Échap pour fermer la modale
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeImagePreview();
  }
});
