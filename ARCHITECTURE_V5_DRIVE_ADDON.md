# Invoice Manager V5 - Architecture Hybride Google Drive Add-on

## Vision

L'outil est **integre directement dans Google Drive** : chaque utilisateur (admin, finance, comptable externe) voit un menu/sidebar dans Drive pour traiter les factures. Le backend Python tourne sur **Google Cloud Functions** pour l'OCR et l'extraction.

**Aucun lien externe, aucune app a installer** : tout se passe dans Google Drive.

---

## PARTIE 1 : Vue d'ensemble

### 1.1 Architecture Hybride (Option C)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GOOGLE DRIVE                                  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              GOOGLE APPS SCRIPT (Frontend)                     │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │
│  │  │ Sidebar UI   │  │ Menu Drive   │  │ Declencheur auto    │  │  │
│  │  │ (HTML/CSS/JS)│  │ "Factures"   │  │ (onFileUpload)      │  │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘  │  │
│  │         │                 │                      │             │  │
│  │         └────────────┬────┘──────────────────────┘             │  │
│  │                      ▼                                         │  │
│  │  ┌────────────────────────────────────────────────────────┐    │  │
│  │  │ Apps Script Backend (.gs)                               │    │  │
│  │  │                                                         │    │  │
│  │  │ • Auth / session utilisateur (Google natif)             │    │  │
│  │  │ • Lecture dossiers Drive (DriveApp)                     │    │  │
│  │  │ • Appel HTTP vers Cloud Function                        │    │  │
│  │  │ • Deplacement / renommage fichiers (DriveApp)           │    │  │
│  │  │ • Creation dossiers Quarter (DriveApp)                  │    │  │
│  │  │ • Gestion roles utilisateurs (PropertiesService)        │    │  │
│  │  └──────────────────────┬─────────────────────────────────┘    │  │
│  └─────────────────────────┼──────────────────────────────────────┘  │
│                            │                                         │
└────────────────────────────┼─────────────────────────────────────────┘
                             │ HTTPS (UrlFetchApp)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GOOGLE CLOUD PLATFORM                             │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              CLOUD FUNCTION (Backend Python)                   │  │
│  │                                                                │  │
│  │  POST /process-invoice                                        │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │ 1. Recevoir file_id + company_id                         │  │  │
│  │  │ 2. Telecharger le fichier via Drive API (service account)│  │  │
│  │  │ 3. OCR via Google Cloud Vision API                       │  │  │
│  │  │ 4. Extraction (supplier, date, amount, invoice#, devise) │  │  │
│  │  │ 5. Classification Quarter TVA                            │  │  │
│  │  │ 6. Generer le nouveau nom                                │  │  │
│  │  │ 7. Retourner le resultat JSON                            │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  Modules reutilises de V3 :                                   │  │
│  │  ├── extractors/ (supplier, date, amount, invoice#, currency) │  │
│  │  ├── classifier.py (quarter TVA multi-calendrier)             │  │
│  │  ├── naming.py (generation nom de fichier)                    │  │
│  │  └── ocr/ (Google Vision API)                                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Aussi utilise :                                                     │
│  ├── Cloud Vision API (OCR)                                         │
│  ├── Drive API v3 (lecture fichier par service account)              │
│  └── Secret Manager (cles API)                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Separation des responsabilites

| Composant | Technologie | Responsabilite |
|-----------|-------------|----------------|
| **Menu / Sidebar** | Apps Script (HTML Service) | Interface utilisateur dans Drive |
| **Logique Drive** | Apps Script (.gs) | Lister/deplacer/renommer fichiers, creer dossiers |
| **Auth utilisateur** | Google natif (Session) | Qui est connecte, quels droits |
| **OCR + Extraction** | Cloud Function (Python) | Toute la logique metier lourde |
| **Classification** | Cloud Function (Python) | Quarter TVA, generation de nom |
| **Config societes** | Apps Script (PropertiesService) | Societes, calendriers, roles |

### 1.3 Pourquoi cette separation ?

```
Apps Script sait bien faire          Cloud Function sait bien faire
─────────────────────────            ────────────────────────────
✅ Manipuler les fichiers Drive      ✅ Python (code existant V3)
✅ Afficher une UI dans Drive        ✅ OCR lourd (Vision API)
✅ Connaitre l'utilisateur connecte  ✅ Regex complexes d'extraction
✅ Menus, boutons, interactions      ✅ Calculs, logique metier
✅ Declencheurs automatiques         ✅ Pas de limite 6min
❌ Python (que JavaScript)           ❌ Pas d'acces UI Drive
❌ Limite 6min d'execution           ❌ Pas de session utilisateur
```

---

## PARTIE 2 : Experience Utilisateur dans Google Drive

### 2.1 Menu contextuel Drive

Quand un utilisateur fait clic-droit sur un fichier PDF dans Drive :

```
┌─────────────────────────────────────────┐
│ 📄 scan_etisalat_feb.pdf                │
│                                         │
│  Ouvrir avec ▸                          │
│  Partager...                            │
│  ──────────────                         │
│  📋 Invoice Manager ▸                   │  ← Notre Add-on
│     ├─ Traiter cette facture            │
│     ├─ Apercu (dry run)                 │
│     └─ Historique                       │
│  ──────────────                         │
│  Telecharger                            │
│  Supprimer                              │
└─────────────────────────────────────────┘
```

### 2.2 Sidebar principale (ouverte depuis le menu)

```
┌──────────────────────────────────────────────────────────────────┐
│ Google Drive                                           👤 Ahmed │
│                                                                  │
│ 📁 BRAMS Tech LLC > Inbox                                       │
│   📄 scan_etisalat_feb.pdf                                      │
│   📄 aws_invoice_jan.pdf                                        │
│   📄 cursor_receipt.pdf                                         │
│                                                                  │
│ ┌──────────────────────────────┐                                │
│ │  📋 Invoice Manager    v5.0  │  ← SIDEBAR (notre add-on)     │
│ │                              │                                │
│ │  👤 Ahmed (Finance)          │  ← Role detecte automatiquement│
│ │                              │                                │
│ │  Societe :                   │                                │
│ │  ┌────────────────────────┐  │                                │
│ │  │ BRAMS Tech LLC (UAE) ▼│  │  ← Dropdown societes          │
│ │  └────────────────────────┘  │                                │
│ │                              │                                │
│ │  Source : Inbox/             │                                │
│ │  3 fichiers detectes         │                                │
│ │                              │                                │
│ │  ┌────────────────────────┐  │                                │
│ │  │ ☐ scan_etisalat_feb   │  │                                │
│ │  │ ☐ aws_invoice_jan     │  │                                │
│ │  │ ☐ cursor_receipt      │  │                                │
│ │  └────────────────────────┘  │                                │
│ │                              │                                │
│ │  [☑ Tout selectionner]       │                                │
│ │                              │                                │
│ │  [  Apercu  ] [ Traiter  ]   │                                │
│ │                              │                                │
│ └──────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 Resultat apres traitement

```
│ ┌──────────────────────────────┐ │
│ │  📋 Invoice Manager          │ │
│ │                              │ │
│ │  ✅ Traitement termine       │ │
│ │  3/3 factures traitees       │ │
│ │                              │ │
│ │  ┌────────────────────────┐  │ │
│ │  │ ✅ scan_etisalat_feb   │  │ │
│ │  │   → Etisalat           │  │ │
│ │  │   → #INV1965257146     │  │ │
│ │  │   → 15-02-2025         │  │ │
│ │  │   → 960.34 AED         │  │ │
│ │  │   → Q1-2025/           │  │ │
│ │  │   Nouveau nom :        │  │ │
│ │  │   Etisalat_#INV196..   │  │ │
│ │  │   _15-02-2025_960.34   │  │ │
│ │  │   AED_Q1-2025.pdf      │  │ │
│ │  ├────────────────────────┤  │ │
│ │  │ ✅ aws_invoice_jan     │  │ │
│ │  │   → AWS                │  │ │
│ │  │   → #2030491957        │  │ │
│ │  │   → 15-01-2025         │  │ │
│ │  │   → 592.37 USD         │  │ │
│ │  │   → Q4-2024/ ⚠️        │  │ │
│ │  │   (Annee precedente)   │  │ │
│ │  ├────────────────────────┤  │ │
│ │  │ ✅ cursor_receipt      │  │ │
│ │  │   → Cursor             │  │ │
│ │  │   → #HK7WPHRD-0001    │  │ │
│ │  │   → 01-02-2025         │  │ │
│ │  │   → 40.00 USD          │  │ │
│ │  │   → Q1-2025/           │  │ │
│ │  └────────────────────────┘  │ │
│ │                              │ │
│ │  [Voir dans Drive]  [Fermer] │ │
│ │                              │ │
│ └──────────────────────────────┘ │
```

### 2.4 Declencheur automatique (optionnel)

L'add-on peut surveiller le dossier "Inbox" et **notifier** quand de nouveaux fichiers arrivent :

```
┌─────────────────────────────────────────┐
│ 🔔 Invoice Manager                      │
│                                          │
│ 2 nouvelles factures dans               │
│ BRAMS Tech LLC / Inbox                  │
│                                          │
│ [Traiter maintenant]  [Plus tard]       │
└─────────────────────────────────────────┘
```

---

## PARTIE 3 : Architecture technique detaillee

### 3.1 Structure du projet

```
invoice_manager_v5/
│
├── apps_script/                          # FRONTEND - Google Apps Script
│   ├── appsscript.json                   # Manifest (scopes, add-on config)
│   ├── Code.gs                           # Point d'entree, menus, declencheurs
│   ├── DriveOperations.gs                # Lister, deplacer, renommer, creer dossiers
│   ├── CloudFunctionClient.gs            # Appel HTTP vers la Cloud Function
│   ├── UserManager.gs                    # Gestion roles, permissions
│   ├── CompanyConfig.gs                  # Configuration societes (PropertiesService)
│   ├── sidebar.html                      # UI principale (sidebar)
│   ├── sidebar_css.html                  # Styles CSS
│   ├── sidebar_js.html                   # JavaScript client-side
│   └── notification.html                 # Template notification
│
├── cloud_function/                       # BACKEND - Python Cloud Function
│   ├── main.py                           # Point d'entree HTTP (Flask)
│   ├── requirements.txt                  # Dependances Python
│   │
│   ├── core/                             # Moteur reutilise de V3
│   │   ├── __init__.py
│   │   ├── models.py                     # Dataclasses (Invoice, Company, Quarter)
│   │   ├── pipeline.py                   # ProcessingPipeline
│   │   │
│   │   ├── ocr/
│   │   │   ├── __init__.py
│   │   │   └── google_vision.py          # OCR via Vision API
│   │   │
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── supplier.py               # Extracteur fournisseur
│   │   │   ├── invoice_number.py         # Extracteur numero facture
│   │   │   ├── date_extractor.py         # Extracteur date
│   │   │   ├── amount.py                 # Extracteur montant
│   │   │   └── currency.py               # Extracteur devise
│   │   │
│   │   ├── classifier.py                 # QuarterClassifier (calendrier TVA)
│   │   └── naming.py                     # FileNamingEngine
│   │
│   ├── config/
│   │   └── companies.json                # Config societes (backup / reference)
│   │
│   └── tests/
│       ├── test_extractors.py
│       ├── test_classifier.py
│       └── test_pipeline.py
│
├── deploy/                               # Scripts de deploiement
│   ├── deploy_cloud_function.sh          # gcloud functions deploy
│   ├── deploy_apps_script.sh             # clasp push
│   └── setup_permissions.sh              # IAM, service accounts
│
└── docs/
    └── SETUP.md                          # Guide d'installation
```

### 3.2 Manifest Apps Script (appsscript.json)

```json
{
  "timeZone": "Asia/Dubai",
  "dependencies": {
    "enabledAdvancedServices": [
      {
        "userSymbol": "Drive",
        "version": "v3",
        "serviceId": "drive"
      }
    ]
  },
  "oauthScopes": [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/userinfo.email"
  ],
  "addOns": {
    "common": {
      "name": "Invoice Manager",
      "logoUrl": "https://storage.googleapis.com/invoice-manager-assets/logo.png",
      "layoutProperties": {
        "primaryColor": "#2196F3"
      }
    },
    "drive": {
      "homepageTrigger": {
        "runFunction": "onDriveHomepage"
      },
      "onItemsSelectedTrigger": {
        "runFunction": "onDriveItemsSelected"
      }
    }
  },
  "exceptionLogging": "STACKDRIVER"
}
```

### 3.3 Apps Script - Code principal (Code.gs)

```javascript
// ============================================================
// Code.gs - Point d'entree de l'Add-on Google Drive
// ============================================================

/**
 * Affiche le menu dans Google Drive
 */
function onDriveHomepage(e) {
  return createHomepageCard();
}

/**
 * Quand l'utilisateur selectionne des fichiers dans Drive
 */
function onDriveItemsSelected(e) {
  var items = e.drive.selectedItems;
  var pdfItems = items.filter(function(item) {
    return item.mimeType === 'application/pdf' ||
           item.mimeType.startsWith('image/');
  });

  if (pdfItems.length === 0) {
    return createNoPdfCard();
  }

  return createProcessCard(pdfItems);
}

/**
 * Carte d'accueil (homepage)
 */
function createHomepageCard() {
  var user = Session.getActiveUser().getEmail();
  var role = UserManager.getRole(user);
  var companies = CompanyConfig.getCompaniesForUser(user);

  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader()
      .setTitle('Invoice Manager')
      .setSubtitle(user + ' (' + role + ')'))
    .addSection(createCompanySelector(companies))
    .addSection(createQuickActions())
    .build();

  return card;
}

/**
 * Carte de traitement pour fichiers selectionnes
 */
function createProcessCard(items) {
  var section = CardService.newCardSection()
    .setHeader(items.length + ' fichier(s) selectionne(s)');

  items.forEach(function(item) {
    section.addWidget(CardService.newDecoratedText()
      .setText(item.title)
      .setStartIcon(CardService.newIconImage()
        .setIconUrl('https://ssl.gstatic.com/docs/doclist/images/mediatype/icon_1_pdf_x32.png')));
  });

  section.addWidget(CardService.newButtonSet()
    .addButton(CardService.newTextButton()
      .setText('Apercu')
      .setOnClickAction(CardService.newAction()
        .setFunctionName('previewInvoices')
        .setParameters({fileIds: JSON.stringify(items.map(function(i) { return i.id; }))})))
    .addButton(CardService.newTextButton()
      .setText('Traiter')
      .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
      .setOnClickAction(CardService.newAction()
        .setFunctionName('processInvoices')
        .setParameters({fileIds: JSON.stringify(items.map(function(i) { return i.id; }))}))));

  return CardService.newCardBuilder()
    .addSection(section)
    .build();
}
```

### 3.4 Apps Script - Operations Drive (DriveOperations.gs)

```javascript
// ============================================================
// DriveOperations.gs - Gestion des fichiers et dossiers Drive
// ============================================================

var DriveOps = {

  /**
   * Liste les fichiers PDF/images dans un dossier
   */
  listInboxFiles: function(folderId) {
    var query = "'" + folderId + "' in parents and trashed=false and (" +
      "mimeType='application/pdf' or " +
      "mimeType='image/jpeg' or " +
      "mimeType='image/png' or " +
      "mimeType='image/tiff'" +
    ")";

    var files = [];
    var response = Drive.Files.list({
      q: query,
      fields: 'files(id,name,mimeType,size,createdTime)',
      orderBy: 'createdTime desc'
    });

    if (response.files) {
      response.files.forEach(function(file) {
        files.push({
          id: file.id,
          name: file.name,
          mimeType: file.mimeType,
          size: file.size,
          created: file.createdTime
        });
      });
    }
    return files;
  },

  /**
   * Cree l'arborescence de dossiers Quarter si elle n'existe pas
   * Ex: BRAMS Tech LLC / 2025 / Q1-2025 /
   */
  ensureQuarterFolder: function(rootFolderId, year, quarterName) {
    // Chercher ou creer le dossier annee
    var yearFolderId = this._findOrCreateFolder(
      rootFolderId, String(year)
    );

    // Chercher ou creer le dossier quarter
    var quarterFolderId = this._findOrCreateFolder(
      yearFolderId, quarterName
    );

    return quarterFolderId;
  },

  /**
   * Deplace et renomme un fichier dans le dossier cible
   */
  moveAndRename: function(fileId, targetFolderId, newName) {
    // Recuperer les parents actuels
    var file = Drive.Files.get(fileId, {fields: 'parents'});
    var previousParents = file.parents.join(',');

    // Deplacer + renommer
    Drive.Files.update(
      {name: newName},
      fileId,
      null,
      {
        addParents: targetFolderId,
        removeParents: previousParents,
        fields: 'id, name, parents'
      }
    );

    return {fileId: fileId, newName: newName, folderId: targetFolderId};
  },

  /**
   * Cherche un sous-dossier par nom, le cree s'il n'existe pas
   */
  _findOrCreateFolder: function(parentId, folderName) {
    var query = "'" + parentId + "' in parents " +
      "and name='" + folderName + "' " +
      "and mimeType='application/vnd.google-apps.folder' " +
      "and trashed=false";

    var response = Drive.Files.list({q: query, fields: 'files(id)'});

    if (response.files && response.files.length > 0) {
      return response.files[0].id;
    }

    // Creer le dossier
    var metadata = {
      name: folderName,
      mimeType: 'application/vnd.google-apps.folder',
      parents: [parentId]
    };
    var folder = Drive.Files.create(metadata, null, {fields: 'id'});
    return folder.id;
  }
};
```

### 3.5 Apps Script - Appel Cloud Function (CloudFunctionClient.gs)

```javascript
// ============================================================
// CloudFunctionClient.gs - Communication avec le backend Python
// ============================================================

var CLOUD_FUNCTION_URL = 'https://REGION-PROJECT_ID.cloudfunctions.net/process-invoice';
var API_KEY_PROPERTY = 'CLOUD_FUNCTION_API_KEY';

var CloudFunction = {

  /**
   * Envoie un fichier au backend Python pour OCR + extraction
   */
  processFile: function(fileId, companyId) {
    var apiKey = PropertiesService.getScriptProperties()
      .getProperty(API_KEY_PROPERTY);

    var payload = {
      file_id: fileId,
      company_id: companyId,
      user_email: Session.getActiveUser().getEmail()
    };

    var options = {
      method: 'POST',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + apiKey,
        'X-Request-Source': 'drive-addon'
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    var response = UrlFetchApp.fetch(CLOUD_FUNCTION_URL, options);
    var statusCode = response.getResponseCode();

    if (statusCode !== 200) {
      throw new Error('Backend error (' + statusCode + '): ' +
        response.getContentText());
    }

    return JSON.parse(response.getContentText());
  },

  /**
   * Traite un lot de fichiers
   */
  processBatch: function(fileIds, companyId) {
    var results = [];
    for (var i = 0; i < fileIds.length; i++) {
      try {
        var result = this.processFile(fileIds[i], companyId);
        result.status = 'success';
        results.push(result);
      } catch (e) {
        results.push({
          file_id: fileIds[i],
          status: 'error',
          error: e.message
        });
      }
    }
    return results;
  }
};
```

### 3.6 Apps Script - Gestion utilisateurs (UserManager.gs)

```javascript
// ============================================================
// UserManager.gs - Roles et permissions
// ============================================================

var ROLES = {
  admin:   ['upload', 'process', 'configure', 'view_history', 'manage_users'],
  finance: ['upload', 'process', 'view_history'],
  viewer:  ['view_history', 'download']
};

var UserManager = {

  /**
   * Recupere le role d'un utilisateur
   */
  getRole: function(email) {
    var users = this._getUsers();
    if (users[email]) {
      return users[email].role;
    }
    return null; // Utilisateur non autorise
  },

  /**
   * Verifie si l'utilisateur a une permission specifique
   */
  hasPermission: function(email, action) {
    var role = this.getRole(email);
    if (!role) return false;
    return ROLES[role] && ROLES[role].indexOf(action) !== -1;
  },

  /**
   * Recupere les societes accessibles par un utilisateur
   */
  getCompanies: function(email) {
    var users = this._getUsers();
    if (users[email]) {
      return users[email].companies || [];
    }
    return [];
  },

  /**
   * Ajoute ou modifie un utilisateur (admin seulement)
   */
  setUser: function(adminEmail, targetEmail, role, companies) {
    if (!this.hasPermission(adminEmail, 'manage_users')) {
      throw new Error('Permission refusee : vous n\'etes pas admin');
    }
    var users = this._getUsers();
    users[targetEmail] = {role: role, companies: companies};
    this._saveUsers(users);
  },

  _getUsers: function() {
    var data = PropertiesService.getScriptProperties()
      .getProperty('USERS_CONFIG');
    return data ? JSON.parse(data) : {};
  },

  _saveUsers: function(users) {
    PropertiesService.getScriptProperties()
      .setProperty('USERS_CONFIG', JSON.stringify(users));
  }
};
```

### 3.7 Apps Script - Configuration societes (CompanyConfig.gs)

```javascript
// ============================================================
// CompanyConfig.gs - Configuration des societes
// ============================================================

/**
 * Configuration par defaut des societes
 * Stockee dans PropertiesService pour pouvoir etre modifiee via l'UI
 */
var DEFAULT_COMPANIES = [
  {
    id: 'brams_tech_llc',
    name: 'BRAMS Technologies LLC',
    country: 'UAE',
    vat_calendar: 'uae_trn_feb',
    root_folder_id: '',        // A configurer lors du setup
    inbox_folder_name: 'Inbox',
    accounting_prefixes: ['PUR', 'Pyt Vch'],
    folder_template: '{year}/{quarter}-{year}'
    // Ex: 2025/Q1-2025/
  },
  {
    id: 'brams_sa',
    name: 'BRAMS SA',
    country: 'Morocco',
    vat_calendar: 'morocco_standard',
    root_folder_id: '',
    inbox_folder_name: 'Inbox',
    accounting_prefixes: [],
    folder_template: '{year}/T{quarter_num}-{year}'
    // Ex: 2025/T1-2025/
  }
];

var CompanyConfig = {

  /**
   * Recupere toutes les societes configurees
   */
  getAll: function() {
    var data = PropertiesService.getScriptProperties()
      .getProperty('COMPANIES_CONFIG');
    return data ? JSON.parse(data) : DEFAULT_COMPANIES;
  },

  /**
   * Recupere les societes accessibles par un utilisateur
   */
  getCompaniesForUser: function(email) {
    var userCompanyIds = UserManager.getCompanies(email);
    var allCompanies = this.getAll();

    if (userCompanyIds.length === 0) {
      return allCompanies; // Admin voit tout
    }

    return allCompanies.filter(function(c) {
      return userCompanyIds.indexOf(c.id) !== -1;
    });
  },

  /**
   * Recupere une societe par ID
   */
  getById: function(companyId) {
    var companies = this.getAll();
    for (var i = 0; i < companies.length; i++) {
      if (companies[i].id === companyId) {
        return companies[i];
      }
    }
    return null;
  },

  /**
   * Met a jour la configuration d'une societe
   */
  update: function(companyId, updates) {
    var companies = this.getAll();
    for (var i = 0; i < companies.length; i++) {
      if (companies[i].id === companyId) {
        Object.keys(updates).forEach(function(key) {
          companies[i][key] = updates[key];
        });
        break;
      }
    }
    PropertiesService.getScriptProperties()
      .setProperty('COMPANIES_CONFIG', JSON.stringify(companies));
  }
};
```

### 3.8 Cloud Function - Backend Python (main.py)

```python
"""
Cloud Function - Backend de traitement des factures.
Recoit un file_id Google Drive, effectue l'OCR et l'extraction,
retourne le resultat en JSON.
"""
import json
import os
import tempfile
import functions_framework
from flask import jsonify, request

from core.ocr.google_vision import GoogleVisionOCR
from core.extractors.supplier import SupplierExtractor
from core.extractors.invoice_number import InvoiceNumberExtractor
from core.extractors.date_extractor import DateExtractor
from core.extractors.amount import AmountExtractor
from core.extractors.currency import CurrencyExtractor
from core.classifier import QuarterClassifier
from core.naming import FileNamingEngine
from core.models import InvoiceData

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io


# --- Configuration ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
API_KEY = os.environ.get('API_KEY', '')


def get_drive_service():
    """Initialise le client Drive API avec le service account."""
    # En Cloud Function, utilise les credentials par defaut du projet
    from google.auth import default
    creds, _ = default(scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def download_file(drive_service, file_id):
    """Telecharge un fichier depuis Drive dans un fichier temporaire."""
    # Recuperer les metadonnees
    file_meta = drive_service.files().get(
        fileId=file_id,
        fields='name,mimeType'
    ).execute()

    # Telecharger le contenu
    request_dl = drive_service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request_dl)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer.getvalue(), file_meta['name'], file_meta['mimeType']


def load_companies_config():
    """Charge la configuration des societes."""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'companies.json')
    with open(config_path, 'r') as f:
        return json.load(f)


@functions_framework.http
def process_invoice(request):
    """
    Point d'entree HTTP de la Cloud Function.

    POST /process-invoice
    Body JSON:
    {
        "file_id": "abc123...",
        "company_id": "brams_tech_llc",
        "user_email": "ahmed@brams.com",
        "dry_run": false
    }

    Response JSON:
    {
        "supplier": "Etisalat",
        "invoice_number": "#INV1965257146",
        "date": "15-02-2025",
        "amount": 960.34,
        "currency": "AED",
        "quarter": "Q1",
        "vat_year": 2025,
        "quarter_folder": "Q1-2025",
        "new_filename": "Etisalat_#INV1965257146_15-02-2025_960.34AED_Q1-2025.pdf",
        "accounting_prefix": null
    }
    """
    # --- Validation ---
    # Verifier l'API key
    auth_header = request.headers.get('Authorization', '')
    if API_KEY and not auth_header.endswith(API_KEY):
        return jsonify({'error': 'Unauthorized'}), 401

    # Parser le body
    data = request.get_json(silent=True)
    if not data or 'file_id' not in data:
        return jsonify({'error': 'file_id required'}), 400

    file_id = data['file_id']
    company_id = data.get('company_id', 'brams_tech_llc')

    try:
        # --- 1. Telecharger le fichier depuis Drive ---
        drive_service = get_drive_service()
        file_bytes, filename, mime_type = download_file(drive_service, file_id)

        # --- 2. OCR ---
        ocr = GoogleVisionOCR()
        raw_text = ocr.extract_text(file_bytes, mime_type)

        # --- 3. Extraction ---
        invoice = InvoiceData(
            source_path=filename,
            raw_text=raw_text
        )

        extractors = [
            SupplierExtractor(),
            InvoiceNumberExtractor(),
            DateExtractor(),
            AmountExtractor(),
            CurrencyExtractor(),
        ]

        for extractor in extractors:
            extractor.extract(invoice)

        # --- 4. Classification Quarter ---
        companies_config = load_companies_config()
        classifier = QuarterClassifier(companies_config)
        company = classifier.get_company(company_id)
        quarter, vat_year = classifier.classify(invoice.date, company)

        # --- 5. Generation du nom ---
        naming = FileNamingEngine()
        new_filename = naming.generate(invoice, quarter, vat_year)

        # --- 6. Construire la reponse ---
        result = {
            'file_id': file_id,
            'original_name': filename,
            'supplier': invoice.supplier,
            'invoice_number': invoice.invoice_number,
            'date': invoice.date.strftime('%d-%m-%Y') if invoice.date else None,
            'amount': invoice.amount,
            'currency': invoice.currency,
            'quarter': quarter,
            'vat_year': vat_year,
            'quarter_folder': f'{quarter}-{vat_year}',
            'new_filename': new_filename,
            'accounting_prefix': invoice.accounting_prefix,
            'confidence_scores': invoice.confidence_scores,
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'error': str(e),
            'file_id': file_id
        }), 500
```

---

## PARTIE 4 : Flux de traitement complet

### 4.1 Flux principal : traitement d'une facture

```
Utilisateur dans Google Drive
         │
         │ 1. Selectionne des PDFs dans Drive
         │    et clique "Traiter" dans le sidebar
         ▼
┌─────────────────────────┐
│ Apps Script (Code.gs)   │
│                         │
│ 2. Verifie les droits   │
│    de l'utilisateur     │
│    (UserManager)        │
│                         │
│ 3. Recupere la config   │
│    societe selectionnee │
│    (CompanyConfig)      │
│                         │
│ 4. Pour chaque fichier: │
│    ┌───────────────────────────────────────────────┐
│    │                                               │
│    │  a. Appel Cloud Function                      │
│    │     (CloudFunctionClient.processFile)          │
│    │                                               │
│    │         │                                     │
│    │         ▼                                     │
│    │  ┌─────────────────────────┐                  │
│    │  │ Cloud Function (Python) │                  │
│    │  │                         │                  │
│    │  │ • Download depuis Drive │                  │
│    │  │ • OCR (Vision API)      │                  │
│    │  │ • Extraction donnees    │                  │
│    │  │ • Classification Q TVA  │                  │
│    │  │ • Generation nom        │                  │
│    │  │                         │                  │
│    │  │ Retourne JSON :         │                  │
│    │  │ {supplier, date, amount │                  │
│    │  │  quarter, new_filename} │                  │
│    │  └────────────┬────────────┘                  │
│    │               │                               │
│    │               ▼                               │
│    │  b. Creer dossier Quarter dans Drive           │
│    │     (DriveOps.ensureQuarterFolder)             │
│    │                                               │
│    │  c. Deplacer + renommer le fichier             │
│    │     (DriveOps.moveAndRename)                   │
│    │                                               │
│    └───────────────────────────────────────────────┘
│                         │
│ 5. Afficher les         │
│    resultats dans       │
│    le sidebar           │
└─────────────────────────┘
```

### 4.2 Flux apercu (dry run)

Meme flux, mais sans l'etape 4b et 4c. L'utilisateur voit ce qui **serait** fait sans rien modifier.

### 4.3 Flux automatique (declencheur)

```
Polling toutes les heures (Apps Script Trigger)
         │
         ▼
┌─────────────────────────┐
│ Trigger: checkNewFiles() │
│                          │
│ Pour chaque societe:     │
│   1. Lister le dossier   │
│      Inbox               │
│   2. Si nouveaux fichiers│
│      → Traiter auto      │
│      OU                  │
│      → Envoyer notif     │
│        a l'admin         │
└──────────────────────────┘
```

---

## PARTIE 5 : Gestion des droits multi-utilisateurs

### 5.1 Matrice des roles

```
┌──────────────────┬────────┬─────────┬────────┐
│ Action           │ Admin  │ Finance │ Viewer │
├──────────────────┼────────┼─────────┼────────┤
│ Voir sidebar     │   ✅   │   ✅    │   ✅   │
│ Voir historique  │   ✅   │   ✅    │   ✅   │
│ Telecharger      │   ✅   │   ✅    │   ✅   │
│ Apercu (dry run) │   ✅   │   ✅    │   ❌   │
│ Traiter factures │   ✅   │   ✅    │   ❌   │
│ Upload dans Inbox│   ✅   │   ✅    │   ❌   │
│ Config societes  │   ✅   │   ❌    │   ❌   │
│ Gerer les users  │   ✅   │   ❌    │   ❌   │
└──────────────────┴────────┴─────────┴────────┘
```

### 5.2 Acces par societe

```json
{
  "brahim@brams.com": {
    "role": "admin",
    "companies": ["brams_tech_llc", "brams_sa"]
  },
  "ahmed@brams.com": {
    "role": "finance",
    "companies": ["brams_tech_llc"]
  },
  "fatima@brams.com": {
    "role": "finance",
    "companies": ["brams_sa"]
  },
  "cabinet@external-comptable.com": {
    "role": "viewer",
    "companies": ["brams_tech_llc", "brams_sa"]
  }
}
```

Le comptable externe :
- **Voit** les factures classees dans les dossiers Quarter
- **Telecharge** ce dont il a besoin
- **Ne peut pas** modifier, deplacer, ou traiter des factures
- Acces via les droits de partage Google Drive existants

---

## PARTIE 6 : Deploiement

### 6.1 Pre-requis

| Composant | Requis |
|-----------|--------|
| Projet Google Cloud | `filesautomationrename` (deja existant) |
| Cloud Vision API | Deja active |
| Cloud Functions API | A activer |
| Drive API | Deja active (service account existant) |
| Apps Script | Via Google Workspace |
| clasp CLI | Pour deployer les fichiers Apps Script |

### 6.2 Deploiement Cloud Function

```bash
# Deployer la Cloud Function
cd cloud_function/

gcloud functions deploy process-invoice \
  --runtime python311 \
  --trigger-http \
  --allow-unauthenticated=false \
  --entry-point process_invoice \
  --region me-central1 \
  --memory 512MB \
  --timeout 120s \
  --project filesautomationrename \
  --set-env-vars API_KEY=VOTRE_CLE_SECRETE

# Tester
curl -X POST https://me-central1-filesautomationrename.cloudfunctions.net/process-invoice \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VOTRE_CLE" \
  -d '{"file_id": "abc123", "company_id": "brams_tech_llc"}'
```

### 6.3 Deploiement Apps Script (clasp)

```bash
# Installer clasp
npm install -g @google/clasp

# Se connecter
clasp login

# Creer le projet Apps Script
cd apps_script/
clasp create --type standalone --title "Invoice Manager"

# Pousser le code
clasp push

# Deployer comme Add-on
clasp deploy --description "Invoice Manager v5.0"

# Ouvrir dans l'editeur
clasp open
```

### 6.4 Etapes de configuration initiale

```
1. Deployer la Cloud Function
2. Noter l'URL de la Cloud Function
3. Dans Apps Script :
   a. Renseigner l'URL dans CloudFunctionClient.gs
   b. Ajouter l'API key dans Script Properties
   c. Configurer les societes (root_folder_id pour chaque societe)
   d. Ajouter les utilisateurs et leurs roles
4. Installer l'Add-on :
   a. Publier en mode "interne" (organisation Google Workspace)
   b. OU partager le lien d'installation avec l'equipe
5. Chaque utilisateur installe l'Add-on dans son Drive
```

---

## PARTIE 7 : Couts estimes

| Service | Usage estime | Cout mensuel |
|---------|-------------|-------------|
| Cloud Vision API | ~200 factures/mois | ~$0.30 |
| Cloud Functions | ~200 invocations, 512MB, 30s avg | ~$0.05 |
| Drive API | Inclus dans Workspace | $0 |
| Apps Script | Gratuit (quotas genereux) | $0 |
| **Total** | | **~$0.35/mois** |

Pratiquement **gratuit** pour un usage PME.

---

## PARTIE 8 : Plan de migration

### Phase 1 : Backend Python (Cloud Function)
**Duree estimee : extraction + adaptation du code V3**

| Etape | Action |
|-------|--------|
| 1.1 | Restructurer le code V3 en modules (`core/`, `extractors/`, etc.) |
| 1.2 | Creer `main.py` Cloud Function avec endpoint HTTP |
| 1.3 | Adapter l'OCR pour recevoir des bytes (au lieu de paths) |
| 1.4 | Ajouter le `QuarterClassifier` multi-calendrier |
| 1.5 | Ajouter le `FileNamingEngine` |
| 1.6 | Ecrire les tests unitaires |
| 1.7 | Deployer sur Cloud Functions |
| 1.8 | Tester avec un fichier Drive reel |

### Phase 2 : Frontend Apps Script (Add-on Drive)
**Duree estimee : creation de l'interface Drive**

| Etape | Action |
|-------|--------|
| 2.1 | Creer le projet Apps Script + manifest |
| 2.2 | Implementer `Code.gs` (menus, sidebar) |
| 2.3 | Implementer `DriveOperations.gs` |
| 2.4 | Implementer `CloudFunctionClient.gs` |
| 2.5 | Creer l'interface sidebar (HTML/CSS/JS) |
| 2.6 | Tester le flux complet (select → process → move) |
| 2.7 | Deployer l'Add-on en mode test |

### Phase 3 : Multi-utilisateurs
**Duree estimee : ajout roles et config**

| Etape | Action |
|-------|--------|
| 3.1 | Implementer `UserManager.gs` |
| 3.2 | Implementer `CompanyConfig.gs` |
| 3.3 | Creer l'interface d'administration |
| 3.4 | Configurer les societes (folder IDs) |
| 3.5 | Ajouter les utilisateurs et tester les roles |
| 3.6 | Partager l'Add-on avec l'equipe |

### Phase 4 : Automatisation
**Duree estimee : declencheurs et notifications**

| Etape | Action |
|-------|--------|
| 4.1 | Trigger automatique (polling Inbox) |
| 4.2 | Notifications email/Drive |
| 4.3 | Historique de traitement (Spreadsheet log) |
| 4.4 | Dashboard statistiques |

---

## PARTIE 9 : Limitations et solutions

| Limitation | Impact | Solution |
|------------|--------|----------|
| Apps Script limite 6min/execution | Pas de traitement de +50 fichiers d'un coup | Traitement par lots de 10, avec continuation |
| Apps Script 20k appels URL/jour | ~20k factures/jour max | Largement suffisant pour PME |
| Cloud Function cold start | 2-5s de delai au premier appel | Garder min_instances=1 si besoin |
| Taille fichier Drive | 10MB max pour download direct | Suffisant pour 99% des factures |
| Add-on non publie sur Marketplace | Installation manuelle par utilisateur | Publier en mode "interne" organisation |
