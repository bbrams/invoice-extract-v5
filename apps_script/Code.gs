// ============================================================
// Code.gs - Point d'entree de l'Add-on Google Drive
// Invoice Manager V5
// ============================================================

/**
 * Affiche la carte d'accueil dans Google Drive (homepage trigger).
 */
function onDriveHomepage(e) {
  return createHomepageCard();
}

/**
 * Declenche quand l'utilisateur selectionne des fichiers dans Drive.
 */
function onDriveItemsSelected(e) {
  var items = e.drive.selectedItems;

  var invoiceItems = items.filter(function(item) {
    return item.mimeType === 'application/pdf' ||
           item.mimeType === 'image/jpeg' ||
           item.mimeType === 'image/png' ||
           item.mimeType === 'image/tiff' ||
           item.mimeType === 'image/bmp';
  });

  if (invoiceItems.length === 0) {
    return createNoPdfCard();
  }

  return createProcessCard(invoiceItems);
}

// ── Cartes UI ────────────────────────────────────────────────

/**
 * Carte d'accueil (homepage).
 */
function createHomepageCard() {
  var user = Session.getActiveUser().getEmail();
  var role = UserManager.getRole(user);

  if (!role) {
    return CardService.newCardBuilder()
      .setHeader(CardService.newCardHeader()
        .setTitle('Invoice Manager')
        .setSubtitle('Acces non autorise'))
      .addSection(CardService.newCardSection()
        .addWidget(CardService.newTextParagraph()
          .setText('Votre adresse email (' + user + ') n\'est pas configuree. ' +
                   'Contactez un administrateur.')))
      .build();
  }

  var companies = CompanyConfig.getCompaniesForUser(user);
  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader()
      .setTitle('Invoice Manager')
      .setSubtitle(user + ' (' + role + ')'));

  // Section societe
  if (companies.length > 0) {
    card.addSection(createCompanySelector(companies));
  }

  // Section actions rapides
  card.addSection(createQuickActions(role));

  return card.build();
}

/**
 * Carte quand aucun PDF/image n'est selectionne.
 */
function createNoPdfCard() {
  return CardService.newCardBuilder()
    .addSection(CardService.newCardSection()
      .addWidget(CardService.newTextParagraph()
        .setText('Aucun fichier PDF ou image selectionne.\n\n' +
                 'Selectionnez des factures (PDF, JPG, PNG, TIFF) pour les traiter.')))
    .build();
}

/**
 * Carte de traitement pour fichiers selectionnes.
 */
function createProcessCard(items) {
  var user = Session.getActiveUser().getEmail();
  var role = UserManager.getRole(user);

  // Verifier les droits de traitement
  if (!UserManager.hasPermission(user, 'process')) {
    return CardService.newCardBuilder()
      .addSection(CardService.newCardSection()
        .addWidget(CardService.newTextParagraph()
          .setText('Vous n\'avez pas la permission de traiter des factures.\n' +
                   'Role actuel : ' + (role || 'aucun'))))
      .build();
  }

  var section = CardService.newCardSection()
    .setHeader(items.length + ' fichier(s) selectionne(s)');

  // Limiter a 10 fichiers max par batch
  var maxDisplay = Math.min(items.length, 10);
  for (var i = 0; i < maxDisplay; i++) {
    section.addWidget(CardService.newDecoratedText()
      .setText(items[i].title)
      .setStartIcon(CardService.newIconImage()
        .setIconUrl('https://ssl.gstatic.com/docs/doclist/images/mediatype/icon_1_pdf_x32.png')));
  }
  if (items.length > 10) {
    section.addWidget(CardService.newTextParagraph()
      .setText('... et ' + (items.length - 10) + ' autre(s). Maximum 10 par lot.'));
  }

  // Serialiser les IDs (max 10)
  var fileIds = items.slice(0, 10).map(function(i) { return i.id; });

  // Selecteur de societe
  var companies = CompanyConfig.getCompaniesForUser(user);
  if (companies.length > 0) {
    var dropdown = CardService.newSelectionInput()
      .setType(CardService.SelectionInputType.DROPDOWN)
      .setFieldName('company_id')
      .setTitle('Societe');
    companies.forEach(function(c) {
      dropdown.addItem(c.name, c.id, companies.indexOf(c) === 0);
    });
    section.addWidget(dropdown);
  }

  // Boutons Apercu / Traiter
  var buttonSet = CardService.newButtonSet();

  buttonSet.addButton(CardService.newTextButton()
    .setText('Apercu')
    .setOnClickAction(CardService.newAction()
      .setFunctionName('previewInvoices')
      .setParameters({fileIds: JSON.stringify(fileIds)})));

  buttonSet.addButton(CardService.newTextButton()
    .setText('Traiter')
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
    .setOnClickAction(CardService.newAction()
      .setFunctionName('processInvoices')
      .setParameters({fileIds: JSON.stringify(fileIds)})));

  section.addWidget(buttonSet);

  return CardService.newCardBuilder()
    .addSection(section)
    .build();
}

// ── Selecteur societe ────────────────────────────────────────

function createCompanySelector(companies) {
  var section = CardService.newCardSection()
    .setHeader('Societe');

  var dropdown = CardService.newSelectionInput()
    .setType(CardService.SelectionInputType.DROPDOWN)
    .setFieldName('company_id')
    .setTitle('Selectionner la societe');

  companies.forEach(function(c, idx) {
    dropdown.addItem(c.name + ' (' + c.country + ')', c.id, idx === 0);
  });

  section.addWidget(dropdown);
  return section;
}

// ── Actions rapides ──────────────────────────────────────────

function createQuickActions(role) {
  var section = CardService.newCardSection()
    .setHeader('Actions');

  section.addWidget(CardService.newTextParagraph()
    .setText('Selectionnez des fichiers dans Drive pour les traiter, ' +
             'ou utilisez les actions ci-dessous.'));

  if (role === 'admin') {
    section.addWidget(CardService.newTextButton()
      .setText('Configuration')
      .setOnClickAction(CardService.newAction()
        .setFunctionName('showAdminConfig')));
  }

  return section;
}

// ── Traitement (appel backend) ───────────────────────────────

/**
 * Apercu (dry run) - affiche ce qui serait fait sans modifier.
 */
function previewInvoices(e) {
  var fileIds = JSON.parse(e.parameters.fileIds);
  var companyId = e.formInput ? e.formInput.company_id : null;

  if (!companyId) {
    var companies = CompanyConfig.getCompaniesForUser(
      Session.getActiveUser().getEmail());
    companyId = companies.length > 0 ? companies[0].id : 'brams_tech_llc';
  }

  var results = [];
  for (var i = 0; i < fileIds.length; i++) {
    try {
      var result = CloudFunction.processFile(fileIds[i], companyId, true);
      result.status = 'success';
      results.push(result);
    } catch (err) {
      results.push({
        file_id: fileIds[i],
        status: 'error',
        error: err.message
      });
    }
  }

  return createResultsCard(results, true);
}

/**
 * Traitement reel - extraction + rename + move dans Drive.
 */
function processInvoices(e) {
  var user = Session.getActiveUser().getEmail();
  if (!UserManager.hasPermission(user, 'process')) {
    return CardService.newCardBuilder()
      .addSection(CardService.newCardSection()
        .addWidget(CardService.newTextParagraph()
          .setText('Permission refusee.')))
      .build();
  }

  var fileIds = JSON.parse(e.parameters.fileIds);
  var companyId = e.formInput ? e.formInput.company_id : null;

  if (!companyId) {
    var companies = CompanyConfig.getCompaniesForUser(user);
    companyId = companies.length > 0 ? companies[0].id : 'brams_tech_llc';
  }

  var company = CompanyConfig.getById(companyId);
  var results = [];

  for (var i = 0; i < fileIds.length; i++) {
    try {
      // 1. Appeler le backend pour extraction
      var result = CloudFunction.processFile(fileIds[i], companyId, false);

      if (result.errors && result.errors.length > 0) {
        result.status = 'error';
        results.push(result);
        continue;
      }

      // 2. Creer dossier Quarter dans Drive
      var quarterFolder = result.vat_quarter || result.quarter_folder;
      if (quarterFolder && company && company.root_folder_id) {
        var year = quarterFolder.split('-')[1] || new Date().getFullYear();
        var targetFolderId = DriveOps.ensureQuarterFolder(
          company.root_folder_id, year, quarterFolder
        );

        // 3. Deplacer et renommer
        DriveOps.moveAndRename(fileIds[i], targetFolderId, result.new_filename);
        result.moved = true;
        result.renamed = true;
      }

      result.status = 'success';
      results.push(result);

    } catch (err) {
      results.push({
        file_id: fileIds[i],
        status: 'error',
        error: err.message
      });
    }
  }

  return createResultsCard(results, false);
}

/**
 * Affiche les resultats du traitement.
 */
function createResultsCard(results, isDryRun) {
  var successCount = results.filter(function(r) { return r.status === 'success'; }).length;
  var totalCount = results.length;

  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader()
      .setTitle(isDryRun ? 'Apercu' : 'Traitement termine')
      .setSubtitle(successCount + '/' + totalCount + ' traite(s)'));

  var section = CardService.newCardSection();

  results.forEach(function(r) {
    if (r.status === 'success') {
      var text = (r.supplier || 'Unknown') + '\n' +
        (r.invoice_number || '') + '\n' +
        (r.date || '') + ' | ' + (r.amount || '?') + ' ' + (r.currency || '') + '\n' +
        (r.vat_quarter || r.quarter_folder || '');

      if (!isDryRun && r.new_filename) {
        text += '\n→ ' + r.new_filename;
      }

      section.addWidget(CardService.newDecoratedText()
        .setText(text)
        .setTopLabel(r.original_filename || r.original_name || r.file_id)
        .setStartIcon(CardService.newIconImage()
          .setIcon(CardService.Icon.TICKET)));
    } else {
      section.addWidget(CardService.newDecoratedText()
        .setText('Erreur: ' + (r.error || 'Inconnue'))
        .setTopLabel(r.file_id || 'Fichier')
        .setStartIcon(CardService.newIconImage()
          .setIcon(CardService.Icon.NONE)));
    }
  });

  if (isDryRun) {
    section.addWidget(CardService.newTextParagraph()
      .setText('\nCeci est un apercu. Aucune modification n\'a ete faite.'));
  }

  card.addSection(section);
  return card.build();
}

// ── Admin config ─────────────────────────────────────────────

function showAdminConfig() {
  var user = Session.getActiveUser().getEmail();
  if (!UserManager.hasPermission(user, 'configure')) {
    return CardService.newCardBuilder()
      .addSection(CardService.newCardSection()
        .addWidget(CardService.newTextParagraph()
          .setText('Permission refusee.')))
      .build();
  }

  var companies = CompanyConfig.getAll();
  var section = CardService.newCardSection()
    .setHeader('Configuration des societes');

  companies.forEach(function(c) {
    section.addWidget(CardService.newDecoratedText()
      .setText(c.name + ' (' + c.country + ')')
      .setBottomLabel('Calendrier TVA: ' + c.vat_calendar +
                       '\nDossier racine: ' + (c.root_folder_id || 'Non configure')));
  });

  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader()
      .setTitle('Administration'))
    .addSection(section)
    .build();
}
