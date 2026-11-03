/**
 * ACTIONS.JS - GESTION DES 4 OPÉRATIONS ATELIER :
 * 1. [ ✨ CRÉER ]    : Création d'un article au Catalogue Maître avec nuancier RAL & pastilles
 * 2. [ 📥 STOCKER ]  : Entrée rapide (Réf, Couleur, Fournisseur, Quantité, Prix) + Calcul dynamique PMP (Sans opérateur)
 * 3. [ 📤 DESTOCKER ]: Sortie atelier (Opérateur par défaut 'Atelier', motif si non assigné à une commande, blocage stock négatif)
 * 4. [ 🔒 RESERVER ] : Blocage de profilés pour une Commande / Lot
 */

// Basculement entre les 4 sous-onglets d'action
function selectActionSubTab(subTab) {
  AppState.currentActionSubTab = subTab;

  const btnCreer = document.getElementById('btnActionCreer');
  const btnStocker = document.getElementById('btnActionStocker');
  const btnDestocker = document.getElementById('btnActionDestocker');
  const btnReserver = document.getElementById('btnActionReserver');

  const formCreer = document.getElementById('actionFormCreer');
  const formStocker = document.getElementById('actionFormStocker');
  const formDestocker = document.getElementById('actionFormDestocker');
  const formReserver = document.getElementById('actionFormReserver');

  const resetBtn = (btn) => {
    if (!btn) return;
    btn.className = 'btn-touch py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 transition-all';
  };

  resetBtn(btnCreer);
  resetBtn(btnStocker);
  resetBtn(btnDestocker);
  resetBtn(btnReserver);

  formCreer?.classList.add('hidden');
  formStocker?.classList.add('hidden');
  formDestocker?.classList.add('hidden');
  formReserver?.classList.add('hidden');

  if (subTab === 'creer') {
    if (btnCreer) btnCreer.className = 'btn-touch py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 bg-indigo-600 text-white shadow-md shadow-indigo-600/20 transition-all';
    formCreer?.classList.remove('hidden');
  } else if (subTab === 'stocker') {
    if (btnStocker) btnStocker.className = 'btn-touch py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 bg-emerald-600 text-white shadow-md shadow-emerald-600/20 transition-all';
    formStocker?.classList.remove('hidden');
  } else if (subTab === 'destocker') {
    if (btnDestocker) btnDestocker.className = 'btn-touch py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 bg-rose-600 text-white shadow-md shadow-rose-600/20 transition-all';
    formDestocker?.classList.remove('hidden');
    onDestockOrderSelectChange();
    renderDestockItemsList();
  } else if (subTab === 'reserver') {
    if (btnReserver) btnReserver.className = 'btn-touch py-3 px-3 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 bg-amber-600 text-white shadow-md shadow-amber-600/20 transition-all';
    formReserver?.classList.remove('hidden');
    renderReserveItemsList();
  }

  if (window.lucide) {
    lucide.createIcons();
  }
}

async function refreshActionFormSelects() {
  await loadGlobalSettings();
  await loadReferencesForSelects();
  onDestockOrderSelectChange();
}

// =========================================================================
// 1. [ ✨ CRÉER ] : GESTION DU NUANCIER RAL & CRÉATION ARTICLE
// =========================================================================

function renderCreationColorSwatches() {
  const container = document.getElementById('ralSwatchesContainer');
  if (!container) return;

  const colors = AppState.colors || [];
  if (colors.length === 0) {
    container.innerHTML = '<div class="col-span-full p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 text-xs text-center">Aucune couleur enregistrée. Rendez-vous dans <b>Paramètres > Nuancier</b> pour ajouter vos couleurs.</div>';
    return;
  }

  // Vérifier la sélection courante ou défaut sur RAL 7024 ou première couleur
  const currentColorInput = document.getElementById('actionNewColor');
  let currentVal = currentColorInput ? currentColorInput.value.trim() : '';
  if (!currentVal) {
    const defaultCol = colors.find(c => (c.ral_code && c.ral_code.includes('7024')) || c.name.includes('7024')) || colors[0];
    if (defaultCol) {
      currentVal = defaultCol.name;
      selectRalColor(defaultCol.ral_code || defaultCol.name, defaultCol.name, defaultCol.hex_code || '#474a51');
    }
  }

  container.innerHTML = colors.map(c => {
    const isSelected = currentVal === c.name || currentVal === c.ral_code;
    const borderCls = isSelected ? 'border-2 border-indigo-600 active-swatch shadow-md scale-105' : 'border border-slate-300 dark:border-slate-600';
    const textCls = isSelected ? 'text-indigo-600 dark:text-indigo-400 font-bold' : 'text-slate-700 dark:text-slate-300 font-semibold';
    const displayLabel = c.ral_code || c.name;
    const safeName = (c.name || '').replace(/'/g, "\\'");
    const safeRal = (c.ral_code || c.name || '').replace(/'/g, "\\'");
    const safeHex = (c.hex_code || '#474a51').replace(/'/g, "\\'");

    return `
      <button type="button" onclick="selectRalColor('${safeRal}', '${safeName}', '${safeHex}')" class="ral-swatch p-2 rounded-xl ${borderCls} bg-white dark:bg-slate-900 hover:scale-105 transition-all text-center flex flex-col items-center gap-1 cursor-pointer">
        <div class="w-7 h-7 rounded-full border border-slate-300 dark:border-slate-700 shadow-sm" style="background-color: ${c.hex_code || '#474a51'};"></div>
        <span class="text-[10px] font-mono ${textCls} truncate max-w-full" title="${c.name}">${displayLabel}</span>
      </button>
    `;
  }).join('');
}

function selectRalColor(ralCode, colorName, colorHex) {
  const ralCodeInput = document.getElementById('actionNewRalCode');
  const colorInput = document.getElementById('actionNewColor');
  const colorHexInput = document.getElementById('actionNewColorHex');
  const displayBadge = document.getElementById('selectedRalDisplay');

  if (ralCodeInput) ralCodeInput.value = ralCode;
  if (colorInput) colorInput.value = colorName;
  if (colorHexInput) colorHexInput.value = colorHex;
  if (displayBadge) displayBadge.textContent = ralCode || colorName;

  // Mise à jour visuelle des pastilles du nuancier
  const container = document.getElementById('ralSwatchesContainer');
  if (container) {
    const swatches = container.querySelectorAll('.ral-swatch');
    swatches.forEach(swatch => {
      const titleSpan = swatch.querySelector('span');
      const titleText = titleSpan ? (titleSpan.getAttribute('title') || titleSpan.textContent.trim()) : '';
      if (titleText === colorName || (titleSpan && titleSpan.textContent.trim() === ralCode)) {
        swatch.classList.add('border-2', 'border-indigo-600', 'active-swatch', 'scale-105');
        swatch.classList.remove('border-slate-300', 'dark:border-slate-600');
        if (titleSpan) {
          titleSpan.classList.add('text-indigo-600', 'dark:text-indigo-400', 'font-bold');
          titleSpan.classList.remove('text-slate-700', 'dark:text-slate-300');
        }
      } else {
        swatch.classList.remove('border-2', 'border-indigo-600', 'active-swatch', 'scale-105');
        swatch.classList.add('border-slate-300', 'dark:border-slate-600');
        if (titleSpan) {
          titleSpan.classList.remove('text-indigo-600', 'dark:text-indigo-400', 'font-bold');
          titleSpan.classList.add('text-slate-700', 'dark:text-slate-300');
        }
      }
    });
  }
}

// Upload d'image local pour un article
async function handleArticleImageUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  const label = document.getElementById('uploadImageLabel');
  if (label) label.textContent = 'Envoi...';

  try {
    const res = await fetch('/api/stock/upload-image', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      document.getElementById('actionNewImage').value = data.url;
      const previewCont = document.getElementById('imagePreviewContainer');
      const thumb = document.getElementById('imagePreviewThumb');
      if (previewCont && thumb) {
        thumb.src = data.url;
        previewCont.classList.remove('hidden');
        previewCont.classList.add('flex');
      }
      if (label) label.textContent = (file.name.length > 15 ? file.name.substring(0, 12) + '...' : file.name);
      showToast('Image envoyée avec succès !', 'success');
    } else {
      showToast(data.detail || "Erreur lors de l'upload de l'image", 'error');
      if (label) label.textContent = 'Choisir un fichier';
    }
  } catch (err) {
    console.error('Erreur upload:', err);
    showToast("Erreur réseau lors de l'upload", 'error');
    if (label) label.textContent = 'Choisir un fichier';
  }
}

function cancelUploadedImage() {
  const imgInput = document.getElementById('actionNewImage');
  if (imgInput) imgInput.value = '';
  const fileInput = document.getElementById('actionNewImageFile');
  if (fileInput) fileInput.value = '';
  const previewCont = document.getElementById('imagePreviewContainer');
  if (previewCont) {
    previewCont.classList.add('hidden');
    previewCont.classList.remove('flex');
  }
  const label = document.getElementById('uploadImageLabel');
  if (label) label.textContent = 'Choisir un fichier';
}

async function handleCreerArticleSubmit(e) {
  e.preventDefault();

  const ref = document.getElementById('actionNewRef').value.trim().toUpperCase();
  const designation = document.getElementById('actionNewDesignation').value.trim();
  const category = document.getElementById('actionNewCategory').value;
  const gamme = document.getElementById('actionNewGamme').value;
  const unit = document.getElementById('actionNewUnit').value;
  const color = document.getElementById('actionNewColor').value.trim();
  const ralCode = document.getElementById('actionNewRalCode').value.trim();
  const colorHex = document.getElementById('actionNewColorHex').value.trim();
  const supplier = document.getElementById('actionNewSupplier').value.trim();
  const threshold = parseFloat(document.getElementById('actionNewThreshold').value) || 10;
  const location = document.getElementById('actionNewLocation').value;
  const imageUrl = document.getElementById('actionNewImage').value.trim();
  const initialQty = parseFloat(document.getElementById('actionNewInitialQty').value) || 0;
  const initialPrice = parseFloat(document.getElementById('actionNewPrice').value) || 0;

  if (!ref || !designation || !category || !gamme || !color) {
    showToast("Veuillez renseigner les champs obligatoires (Référence, Désignation, Gamme, Teinte)", "warning");
    return;
  }

  // Contrôle anti-doublon strict en amont [Référence + Teinte]
  const duplicate = AppState.allVariants.find(v => 
    v.product_reference.toUpperCase() === ref && v.color.toUpperCase() === color.toUpperCase()
  );
  if (duplicate) {
    showToast(`⛔ Création bloquée : L'article ${ref} existe déjà dans le coloris '${color}'.`, 'error');
    return;
  }

  const payload = {
    reference: ref,
    designation: designation,
    category: category,
    gamme: gamme,
    unit: unit,
    color: color,
    ral_code: ralCode,
    color_hex: colorHex,
    supplier: supplier,
    threshold: threshold,
    location: location,
    image_url: imageUrl,
    initial_quantity: initialQty,
    unit_price: initialPrice
  };

  try {
    const res = await fetch('/api/stock/catalog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || "Erreur lors de la création de l'article");

    showToast(`✨ ${result.message || 'Article enregistré au Catalogue Maître !'}`, 'success');
    cancelUploadedImage();

    // Recharger les données du catalogue et rafraîchir
    await loadReferencesForSelects();
    await loadGlobalSettings();
    refreshDashboard();

    // Rediriger immédiatement vers l'onglet [ 📥 STOCKER ] avec cette référence
    const stockInRefInput = document.getElementById('stockInSearchRef');
    if (stockInRefInput) {
      stockInRefInput.value = ref;
      selectActionSubTab('stocker');
      onStockInSearchRef(ref);
    }

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

// Redirection depuis l'alerte "Article inexistant" vers [ ✨ CRÉER ]
function redirectCreerWithRef() {
  const typedRef = document.getElementById('stockInSearchRef')?.value.trim().toUpperCase();
  if (typedRef) {
    const newRefInput = document.getElementById('actionNewRef');
    if (newRefInput) newRefInput.value = typedRef;
  }
  selectActionSubTab('creer');
}


// =========================================================================
// 2. [ 📥 STOCKER ] : ENTRÉE EN STOCK RAPIDE & CALCUL DYNAMIQUE PMP
// =========================================================================

function onStockInSearchRef(query) {
  const q = (query || '').trim().toUpperCase();
  const alertEl = document.getElementById('stockInNotFoundAlert');
  const matchedInfoEl = document.getElementById('stockInMatchedInfo');
  const colorSelect = document.getElementById('stockInColorSelect');

  if (!q) {
    alertEl?.classList.add('hidden');
    matchedInfoEl?.classList.add('hidden');
    if (colorSelect) {
      colorSelect.innerHTML = '<option value="">-- Sélectionner d\'abord une référence valide --</option>';
    }
    resetStockInPmpPreview();
    return;
  }

  // Recherche dans le catalogue maître
  const matchedProduct = AppState.allReferences.find(p => p.reference.toUpperCase() === q);

  if (matchedProduct) {
    // Article trouvé
    alertEl?.classList.add('hidden');
    if (matchedInfoEl) {
      matchedInfoEl.classList.remove('hidden');
      document.getElementById('stockInMatchedName').textContent = `${matchedProduct.reference} — ${matchedProduct.designation}`;
      document.getElementById('stockInMatchedCategory').textContent = matchedProduct.category || 'Aluminium';
    }

    // Récupération des variantes existantes pour ce produit
    const variants = AppState.allVariants.filter(v => v.product_reference.toUpperCase() === matchedProduct.reference.toUpperCase());

    if (colorSelect) {
      if (variants.length > 0) {
        colorSelect.innerHTML = variants.map(v => 
          `<option value="${v.id}" data-color="${v.color}" data-supplier="${v.supplier || ''}" data-stock="${v.real_quantity}" data-pmp="${v.pmp}">
            ${v.color} ${v.ral_code ? ' (' + v.ral_code + ')' : ''} — Stock: ${v.real_quantity} | PMP: ${formatMoney(v.pmp)}
          </option>`
        ).join('');

        // Pré-remplir le fournisseur
        const firstVariant = variants[0];
        const supplierInput = document.getElementById('stockInSupplier');
        if (supplierInput && (firstVariant.supplier || matchedProduct.supplier)) {
          supplierInput.value = firstVariant.supplier || matchedProduct.supplier || '';
        }
      } else {
        colorSelect.innerHTML = '<option value="">Aucune variante trouvée</option>';
      }
    }

    updateStockInPmpPreview();

  } else {
    // Vérifier si un produit commence par ce préfixe
    const prefixMatches = AppState.allReferences.some(p => p.reference.toUpperCase().startsWith(q));

    matchedInfoEl?.classList.add('hidden');

    if (!prefixMatches && q.length >= 3) {
      alertEl?.classList.remove('hidden');
      if (colorSelect) {
        colorSelect.innerHTML = '<option value="">⛔ Référence inexistante au catalogue</option>';
      }
      resetStockInPmpPreview();
    } else {
      alertEl?.classList.add('hidden');
    }
  }
}

function onStockInColorChange() {
  const colorSelect = document.getElementById('stockInColorSelect');
  if (!colorSelect) return;

  const selectedOpt = colorSelect.options[colorSelect.selectedIndex];
  if (selectedOpt) {
    const supp = selectedOpt.getAttribute('data-supplier');
    if (supp) {
      const supplierInput = document.getElementById('stockInSupplier');
      if (supplierInput) supplierInput.value = supp;
    }
  }
  updateStockInPmpPreview();
}

function resetStockInPmpPreview() {
  document.getElementById('previewStockActuel').textContent = '0';
  document.getElementById('previewPmpActuel').textContent = '0,00 DZD';
  document.getElementById('previewStockNouveau').textContent = '0';
  document.getElementById('previewPmpNouveau').textContent = '0,00 DZD';
}

function updateStockInPmpPreview() {
  const colorSelect = document.getElementById('stockInColorSelect');
  const variantId = parseInt(colorSelect?.value);
  if (!variantId) {
    resetStockInPmpPreview();
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (!v) {
    resetStockInPmpPreview();
    return;
  }

  const currentStock = parseFloat(v.real_quantity) || 0;
  const currentPmp = parseFloat(v.pmp) || parseFloat(v.current_price) || 0;

  const inQty = parseFloat(document.getElementById('stockInQty')?.value) || 0;
  const inPrice = parseFloat(document.getElementById('stockInPrice')?.value) || 0;

  const newStock = currentStock + inQty;
  let newPmp = currentPmp;

  if (newStock > 0 && inQty > 0) {
    newPmp = ((currentStock * currentPmp) + (inQty * inPrice)) / newStock;
  }

  document.getElementById('previewStockActuel').textContent = currentStock;
  document.getElementById('previewPmpActuel').textContent = formatMoney(currentPmp);
  document.getElementById('previewStockNouveau').textContent = newStock;
  document.getElementById('previewPmpNouveau').textContent = formatMoney(newPmp);
}

async function handleStockInSubmit(e) {
  e.preventDefault();

  const colorSelect = document.getElementById('stockInColorSelect');
  const variantId = parseInt(colorSelect?.value);
  const searchRef = document.getElementById('stockInSearchRef').value.trim().toUpperCase();

  if (!variantId || !searchRef) {
    showToast("⛔ Impossible de stocker : Article inexistant dans le catalogue. Veuillez d'abord le créer.", "error");
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (!v) {
    showToast("Article introuvable au catalogue maître.", "error");
    return;
  }

  const qty = parseFloat(document.getElementById('stockInQty').value);
  const price = parseFloat(document.getElementById('stockInPrice').value);
  const supplier = document.getElementById('stockInSupplier').value.trim();
  const notes = document.getElementById('stockInNotes').value.trim();

  if (isNaN(qty) || qty <= 0) {
    showToast("Veuillez saisir une quantité entrante valide", "warning");
    return;
  }

  let allowZero = false;
  if (price === 0 || isNaN(price)) {
    const confirmZero = confirm("⚠️ Attention : Le prix d'achat saisi est de 0 DZD.\nConfirmez-vous cette entrée à coût nul ?");
    if (!confirmZero) {
      showToast("Opération annulée : Veuillez renseigner un prix d'achat valide", "warning");
      return;
    }
    allowZero = true;
  }

  // Pas d'opérateur lors du stockage selon les spécifications strictes
  const payload = {
    variant_id: v.id,
    reference: v.product_reference,
    color: v.color,
    quantity: qty,
    unit_price: isNaN(price) ? 0 : price,
    supplier: supplier,
    allow_zero_price: allowZero,
    notes: notes,
    user: 'Admin'
  };

  try {
    const res = await fetch('/api/actions/stock-in', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur lors du stockage');

    showToast(`✅ ${result.message}`, 'success');

    // Réinitialiser les champs de saisie
    document.getElementById('stockInQty').value = '';
    document.getElementById('stockInPrice').value = '';
    document.getElementById('stockInNotes').value = '';

    await loadReferencesForSelects();
    onStockInSearchRef(searchRef);
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}


// =========================================================================
// 3. [ 📤 DESTOCKER ] : SORTIE ATELIER MULTI-ARTICLES (AVEC LISTE PLIABLE À DROITE)
// =========================================================================

function onDestockSearchRef(query) {
  const q = (query || '').trim().toUpperCase();
  const select = document.getElementById('destockVariantSelect');
  if (!select) return;

  if (!q) {
    select.innerHTML = '<option value="">-- Sélectionner dans le stock --</option>' +
      AppState.allVariants.map(v => `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${Math.max(0, v.real_quantity - v.reserved_quantity)} | PMP: ${formatMoney(v.pmp)})</option>`).join('');
    return;
  }

  const filtered = AppState.allVariants.filter(v => 
    v.product_reference.toUpperCase().includes(q) || v.color.toUpperCase().includes(q)
  );

  if (filtered.length > 0) {
    select.innerHTML = filtered.map(v => 
      `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${Math.max(0, v.real_quantity - v.reserved_quantity)} | PMP: ${formatMoney(v.pmp)})</option>`
    ).join('');
    select.value = filtered[0].id;
    onDestockVariantChange();
  } else {
    select.innerHTML = '<option value="">Aucun article correspondant en stock</option>';
  }
}

function onDestockVariantChange() {
  const variantId = parseInt(document.getElementById('destockVariantSelect')?.value);
  const infoEl = document.getElementById('destockStockInfo');
  if (!variantId || !infoEl) {
    if (infoEl) infoEl.innerHTML = '';
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (v) {
    const dispo = Math.max(0, v.real_quantity - v.reserved_quantity);
    infoEl.innerHTML = `
      <div class="text-[11px] text-slate-500 mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
        <span>Physique: <b class="text-slate-900 dark:text-white">${v.real_quantity}</b></span>
        <span>Réservé: <b class="text-amber-600">${v.reserved_quantity}</b></span>
        <span>Dispo: <b class="text-emerald-600 font-bold">${dispo}</b></span>
        <span>PMP: <b class="text-emerald-600">${formatMoney(v.pmp)}</b></span>
      </div>
    `;
  }
}

function onDestockOrderSelectChange() {
  const orderSelect = document.getElementById('destockOrderSelect');
  const unassignedGroup = document.getElementById('destockUnassignedGroup');
  if (!orderSelect || !unassignedGroup) return;

  if (orderSelect.value === 'NONE') {
    unassignedGroup.classList.remove('hidden');
  } else {
    unassignedGroup.classList.add('hidden');
  }
}

// Ajouter un article au lot de déstockage
function addDestockItemToList() {
  const variantSelect = document.getElementById('destockVariantSelect');
  const variantId = parseInt(variantSelect?.value);
  const qtyInput = document.getElementById('destockQty');
  const qty = parseFloat(qtyInput?.value);

  if (!variantId) {
    showToast("Veuillez sélectionner un profilé à déstocker", "warning");
    variantSelect?.focus();
    return;
  }

  if (isNaN(qty) || qty <= 0) {
    showToast("Veuillez renseigner une quantité valide (> 0)", "warning");
    qtyInput?.focus();
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (!v) {
    showToast("Variante introuvable dans le catalogue", "error");
    return;
  }

  // Calcul du cumul déjà présent dans la liste
  const existingIndex = AppState.destockBatchItems.findIndex(item => item.variant_id === variantId);
  const currentInList = existingIndex >= 0 ? AppState.destockBatchItems[existingIndex].quantity : 0;
  const newTotal = currentInList + qty;

  // Contrôle local de sécurité stock négatif
  if (v.real_quantity < newTotal) {
    showToast(`⛔ Stock insuffisant : Quantité en atelier (${v.real_quantity}) inférieure au total demandé (${newTotal}).`, 'error');
    return;
  }

  const p = AppState.allReferences.find(prod => prod.reference === v.product_reference);
  const designation = p?.designation || v.designation || v.product_reference;

  if (existingIndex >= 0) {
    AppState.destockBatchItems[existingIndex].quantity = newTotal;
    showToast(`Quantité cumulée pour ${v.product_reference} (${v.color}) : ${newTotal} ${v.unit || 'barre(s)'}`, 'success');
  } else {
    AppState.destockBatchItems.push({
      variant_id: v.id,
      product_reference: v.product_reference,
      designation: designation,
      color: v.color,
      color_hex: v.color_hex || '#64748b',
      unit: v.unit || 'barre',
      quantity: qty,
      real_quantity: v.real_quantity,
      pmp: v.pmp
    });
    showToast(`➕ Article ajouté : ${v.product_reference} (${qty} ${v.unit || 'barres'})`, 'success');
  }

  // Vider le champ quantité pour la saisie suivante
  if (qtyInput) qtyInput.value = '';
  renderDestockItemsList();

  // Si la liste était pliée, la déplier pour montrer l'article ajouté
  if (AppState.destockCollapsed) {
    toggleDestockListCollapse();
  }
}

function removeDestockItem(index) {
  if (index >= 0 && index < AppState.destockBatchItems.length) {
    AppState.destockBatchItems.splice(index, 1);
    renderDestockItemsList();
  }
}

function clearDestockItemsList() {
  if (AppState.destockBatchItems.length === 0) return;
  if (confirm("Voulez-vous vider tous les articles de ce lot de déstockage ?")) {
    AppState.destockBatchItems = [];
    renderDestockItemsList();
  }
}

function toggleDestockListCollapse() {
  AppState.destockCollapsed = !AppState.destockCollapsed;
  const body = document.getElementById('destockCollapsibleBody');
  const icon = document.getElementById('destockCollapseIcon');
  if (!body) return;

  if (AppState.destockCollapsed) {
    body.classList.add('hidden');
    if (icon) icon.style.transform = 'rotate(180deg)';
  } else {
    body.classList.remove('hidden');
    if (icon) icon.style.transform = 'rotate(0deg)';
  }
}

function renderDestockItemsList() {
  const listEl = document.getElementById('destockItemsList');
  const countBadge = document.getElementById('destockItemsBadgeCount');
  const summaryText = document.getElementById('destockItemsSummaryText');
  const clearBtn = document.getElementById('btnDestockClear');
  const submitBtnLabel = document.getElementById('destockSubmitBtnLabel');

  const count = AppState.destockBatchItems.length;
  const totalQty = AppState.destockBatchItems.reduce((acc, it) => acc + it.quantity, 0);

  if (countBadge) countBadge.textContent = count;
  if (summaryText) summaryText.textContent = `${totalQty} barre(s) / unité(s) au total`;
  if (clearBtn) clearBtn.classList.toggle('hidden', count === 0);

  if (submitBtnLabel) {
    submitBtnLabel.textContent = count > 0 
      ? `Valider le Déstockage (${count} article${count > 1 ? 's' : ''} • ${totalQty} barres)` 
      : 'Valider le Déstockage';
  }

  if (!listEl) return;

  if (count === 0) {
    listEl.innerHTML = `
      <div id="destockEmptyMsg" class="p-6 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
        <i data-lucide="package-plus" class="w-8 h-8 text-slate-300 dark:text-slate-600"></i>
        <span>Aucun article dans ce lot.<br>Renseignez un profilé et sa quantité à gauche, puis cliquez sur <b>Ajouter</b>.</span>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  listEl.innerHTML = AppState.destockBatchItems.map((item, idx) => `
    <div class="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 flex items-center justify-between gap-3 shadow-sm hover:border-rose-300 dark:hover:border-rose-900 transition-colors">
      <div class="flex items-center gap-2.5 min-w-0">
        <span class="color-bubble" style="background-color: ${item.color_hex};"></span>
        <div class="min-w-0">
          <div class="font-bold text-xs text-slate-900 dark:text-white truncate">
            <span class="text-indigo-600 font-mono">${item.product_reference}</span> • ${item.color}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400 truncate">${item.designation}</div>
          <div class="text-[10px] text-slate-400">Stock atelier: <b>${item.real_quantity}</b> ${item.unit}</div>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <div class="flex items-center gap-1 bg-rose-50 dark:bg-rose-950/60 border border-rose-200/60 dark:border-rose-900/40 px-2 py-1 rounded-lg">
          <span class="text-xs font-extrabold text-rose-600 dark:text-rose-400">${item.quantity}</span>
          <span class="text-[10px] text-slate-500">${item.unit}</span>
        </div>
        <button type="button" onclick="removeDestockItem(${idx})" class="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950 text-slate-400 hover:text-rose-600 transition-colors" title="Retirer de la liste">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      </div>
    </div>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleDestockSubmit(e) {
  e.preventDefault();

  // Si la liste est vide mais qu'un article et une quantité ont été saisis dans le formulaire, on l'ajoute automatiquement
  if (AppState.destockBatchItems.length === 0) {
    const vId = parseInt(document.getElementById('destockVariantSelect')?.value);
    const q = parseFloat(document.getElementById('destockQty')?.value);
    if (vId && !isNaN(q) && q > 0) {
      addDestockItemToList();
    }
  }

  if (AppState.destockBatchItems.length === 0) {
    showToast('Veuillez ajouter au moins un profilé à déstocker dans la liste à droite', 'warning');
    return;
  }

  const orderVal = document.getElementById('destockOrderSelect').value;
  const lotNumber = document.getElementById('destockLotNumber')?.value.trim();
  const unassignedReason = document.getElementById('destockUnassignedReason')?.value.trim();
  const operator = document.getElementById('destockOperator').value.trim() || 'Atelier';
  const notes = document.getElementById('destockNotes').value.trim();

  const payload = {
    items: AppState.destockBatchItems.map(it => ({ variant_id: it.variant_id, quantity: it.quantity })),
    order_number: (orderVal && orderVal !== 'NONE') ? orderVal : null,
    lot_number: (orderVal && orderVal !== 'NONE') ? (lotNumber || null) : null,
    unassigned_reason: (orderVal === 'NONE') ? (unassignedReason || 'Chutes atelier libre') : null,
    operator: operator,
    notes: notes,
    user: 'Admin'
  };

  try {
    const res = await fetch('/api/actions/destock-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur lors du déstockage groupé');

    if (result.warning) {
      showToast(`⚠️ ${result.message} (${result.warning})`, 'warning');
    } else {
      showToast(`✅ ${result.message}`, 'success');
    }

    // Réinitialisation de la liste et des champs
    AppState.destockBatchItems = [];
    renderDestockItemsList();

    document.getElementById('destockQty').value = '';
    document.getElementById('destockNotes').value = '';
    if (document.getElementById('destockLotNumber')) {
      document.getElementById('destockLotNumber').value = '';
    }
    if (document.getElementById('destockUnassignedReason')) {
      document.getElementById('destockUnassignedReason').value = '';
    }

    await loadReferencesForSelects();
    onDestockVariantChange();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}


// =========================================================================
// 4. [ 🔒 RESERVER ] : RÉSERVATION POUR COMMANDE / LOT MULTI-ARTICLES
// =========================================================================

function onReserveSearchRef(query) {
  const q = (query || '').trim().toUpperCase();
  const select = document.getElementById('reserveVariantSelect');
  if (!select) return;

  if (!q) {
    select.innerHTML = '<option value="">-- Choisir la référence alu --</option>' +
      AppState.allVariants.map(v => `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${Math.max(0, v.real_quantity - v.reserved_quantity)})</option>`).join('');
    return;
  }

  const filtered = AppState.allVariants.filter(v => 
    v.product_reference.toUpperCase().includes(q) || v.color.toUpperCase().includes(q)
  );

  if (filtered.length > 0) {
    select.innerHTML = filtered.map(v => 
      `<option value="${v.id}">${v.product_reference} • ${v.color} (Dispo: ${Math.max(0, v.real_quantity - v.reserved_quantity)})</option>`
    ).join('');
    select.value = filtered[0].id;
    onReserveVariantChange();
  } else {
    select.innerHTML = '<option value="">Aucun article correspondant</option>';
  }
}

function onReserveVariantChange() {
  const variantId = parseInt(document.getElementById('reserveVariantSelect')?.value);
  const infoEl = document.getElementById('reserveStockInfo');
  if (!variantId || !infoEl) {
    if (infoEl) infoEl.innerHTML = '';
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (v) {
    const avail = Math.max(0, v.real_quantity - v.reserved_quantity);
    infoEl.innerHTML = `Stock physique : <b>${v.real_quantity}</b> | Disponible pour réservation : <b class="text-emerald-600 font-bold">${avail}</b>`;
  }
}

// Ajouter un article à la réservation
function addReserveItemToList() {
  const variantSelect = document.getElementById('reserveVariantSelect');
  const variantId = parseInt(variantSelect?.value);
  const qtyInput = document.getElementById('reserveQty');
  const qty = parseFloat(qtyInput?.value);

  if (!variantId) {
    showToast("Veuillez choisir un profilé à réserver", "warning");
    variantSelect?.focus();
    return;
  }

  if (isNaN(qty) || qty <= 0) {
    showToast("Veuillez saisir une quantité à réserver valide (> 0)", "warning");
    qtyInput?.focus();
    return;
  }

  const v = AppState.allVariants.find(item => item.id === variantId);
  if (!v) {
    showToast("Variante introuvable dans le catalogue", "error");
    return;
  }

  const avail = Math.max(0, v.real_quantity - v.reserved_quantity);
  const existingIndex = AppState.reserveBatchItems.findIndex(item => item.variant_id === variantId);
  const currentInList = existingIndex >= 0 ? AppState.reserveBatchItems[existingIndex].quantity : 0;
  const newTotal = currentInList + qty;

  if (avail < newTotal) {
    showToast(`⛔ Disponibilité insuffisante : Seulement ${avail} barres disponibles en atelier (${newTotal} demandées au total).`, 'error');
    return;
  }

  const p = AppState.allReferences.find(prod => prod.reference === v.product_reference);
  const designation = p?.designation || v.designation || v.product_reference;

  if (existingIndex >= 0) {
    AppState.reserveBatchItems[existingIndex].quantity = newTotal;
    showToast(`Quantité réservée mise à jour pour ${v.product_reference} : ${newTotal} ${v.unit || 'barre(s)'}`, 'success');
  } else {
    AppState.reserveBatchItems.push({
      variant_id: v.id,
      product_reference: v.product_reference,
      designation: designation,
      color: v.color,
      color_hex: v.color_hex || '#64748b',
      unit: v.unit || 'barre',
      quantity: qty,
      available_quantity: avail
    });
    showToast(`🔒 Profilé ajouté à la réservation : ${v.product_reference} (${qty} ${v.unit || 'barres'})`, 'success');
  }

  if (qtyInput) qtyInput.value = '';
  renderReserveItemsList();

  if (AppState.reserveCollapsed) {
    toggleReserveListCollapse();
  }
}

function removeReserveItem(index) {
  if (index >= 0 && index < AppState.reserveBatchItems.length) {
    AppState.reserveBatchItems.splice(index, 1);
    renderReserveItemsList();
  }
}

function clearReserveItemsList() {
  if (AppState.reserveBatchItems.length === 0) return;
  if (confirm("Voulez-vous vider tous les profilés de cette réservation ?")) {
    AppState.reserveBatchItems = [];
    renderReserveItemsList();
  }
}

function toggleReserveListCollapse() {
  AppState.reserveCollapsed = !AppState.reserveCollapsed;
  const body = document.getElementById('reserveCollapsibleBody');
  const icon = document.getElementById('reserveCollapseIcon');
  if (!body) return;

  if (AppState.reserveCollapsed) {
    body.classList.add('hidden');
    if (icon) icon.style.transform = 'rotate(180deg)';
  } else {
    body.classList.remove('hidden');
    if (icon) icon.style.transform = 'rotate(0deg)';
  }
}

function renderReserveItemsList() {
  const listEl = document.getElementById('reserveItemsList');
  const countBadge = document.getElementById('reserveItemsBadgeCount');
  const summaryText = document.getElementById('reserveItemsSummaryText');
  const clearBtn = document.getElementById('btnReserveClear');
  const submitBtnLabel = document.getElementById('reserveSubmitBtnLabel');

  const count = AppState.reserveBatchItems.length;
  const totalQty = AppState.reserveBatchItems.reduce((acc, it) => acc + it.quantity, 0);

  if (countBadge) countBadge.textContent = count;
  if (summaryText) summaryText.textContent = `${totalQty} barre(s) / unité(s) au total`;
  if (clearBtn) clearBtn.classList.toggle('hidden', count === 0);

  if (submitBtnLabel) {
    submitBtnLabel.textContent = count > 0 
      ? `Confirmer la Réservation (${count} profilé${count > 1 ? 's' : ''} • ${totalQty} barres)` 
      : 'Confirmer la Réservation';
  }

  if (!listEl) return;

  if (count === 0) {
    listEl.innerHTML = `
      <div id="reserveEmptyMsg" class="p-6 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
        <i data-lucide="package-plus" class="w-8 h-8 text-slate-300 dark:text-slate-600"></i>
        <span>Aucun profilé dans cette réservation.<br>Sélectionnez un profilé et sa quantité à gauche, puis cliquez sur <b>Ajouter</b>.</span>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  listEl.innerHTML = AppState.reserveBatchItems.map((item, idx) => `
    <div class="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 flex items-center justify-between gap-3 shadow-sm hover:border-amber-300 dark:hover:border-amber-900 transition-colors">
      <div class="flex items-center gap-2.5 min-w-0">
        <span class="color-bubble" style="background-color: ${item.color_hex};"></span>
        <div class="min-w-0">
          <div class="font-bold text-xs text-slate-900 dark:text-white truncate">
            <span class="text-indigo-600 font-mono">${item.product_reference}</span> • ${item.color}
          </div>
          <div class="text-[11px] text-slate-500 dark:text-slate-400 truncate">${item.designation}</div>
          <div class="text-[10px] text-slate-400">Disponible: <b>${item.available_quantity}</b> ${item.unit}</div>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <div class="flex items-center gap-1 bg-amber-50 dark:bg-amber-950/60 border border-amber-200/60 dark:border-amber-900/40 px-2 py-1 rounded-lg">
          <span class="text-xs font-extrabold text-amber-600 dark:text-amber-400">${item.quantity}</span>
          <span class="text-[10px] text-slate-500">${item.unit}</span>
        </div>
        <button type="button" onclick="removeReserveItem(${idx})" class="p-1.5 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-950 text-slate-400 hover:text-amber-600 transition-colors" title="Retirer de la réservation">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      </div>
    </div>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

async function handleReserveSubmit(e) {
  e.preventDefault();

  // Si la liste est vide mais qu'un article et une quantité ont été saisis dans le formulaire, on l'ajoute automatiquement
  if (AppState.reserveBatchItems.length === 0) {
    const vId = parseInt(document.getElementById('reserveVariantSelect')?.value);
    const q = parseFloat(document.getElementById('reserveQty')?.value);
    if (vId && !isNaN(q) && q > 0) {
      addReserveItemToList();
    }
  }

  if (AppState.reserveBatchItems.length === 0) {
    showToast('Veuillez ajouter au moins un profilé à réserver dans la liste à droite', 'warning');
    return;
  }

  const orderNumber = document.getElementById('reserveOrderSelect').value;
  const lotNumber = document.getElementById('reserveLotNumber')?.value.trim();
  const notes = document.getElementById('reserveNotes').value.trim();

  if (!orderNumber) {
    showToast('Veuillez sélectionner une commande / lot', 'warning');
    return;
  }

  const payload = {
    items: AppState.reserveBatchItems.map(it => ({ variant_id: it.variant_id, quantity: it.quantity })),
    order_number: orderNumber,
    lot_number: lotNumber || null,
    client_name: `Commande ${orderNumber}`,
    notes: notes,
    user: 'Admin'
  };

  try {
    const res = await fetch('/api/actions/reserve-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur lors de la réservation groupée');

    showToast(`🔒 ${result.message}`, 'success');

    AppState.reserveBatchItems = [];
    renderReserveItemsList();

    document.getElementById('reserveQty').value = '';
    if (document.getElementById('reserveLotNumber')) {
      document.getElementById('reserveLotNumber').value = '';
    }
    document.getElementById('reserveNotes').value = '';

    await loadReferencesForSelects();
    onReserveVariantChange();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}
