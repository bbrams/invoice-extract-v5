# Architecture V5 - Invoice Manager Drive Add-on

## Vue d'ensemble

Invoice Manager V5 est une solution hybride pour le traitement automatique de factures depuis Google Drive :

```
Google Drive Add-on (Apps Script)
        |
        | HTTPS + X-API-Key
        v
Cloud Function (Python 3.11)
        |
        +-- Pipeline OCR (pdfplumber + Cloud Vision)
        +-- Extraction (supplier, date, amount, invoice#)
        +-- Renommage & classement Drive
```

## Architecture hybride

### Frontend : Google Drive Add-on (Apps Script)

Fichiers dans `apps_script/` :

| Fichier                  | Role                                          |
|--------------------------|-----------------------------------------------|
| `appsscript.json`        | Manifest, scopes OAuth, triggers Drive        |
| `Code.gs`                | Entry points (homepage, selection, processing) |
| `DriveOperations.gs`     | Gestion fichiers/dossiers Drive (list, move, rename) |
| `CloudFunctionClient.gs` | Client HTTP vers le backend Python            |
| `UserManager.gs`         | RBAC (admin, finance, viewer)                 |
| `CompanyConfig.gs`       | Configuration multi-societe                   |

### Backend : Cloud Function Python (Gen 2)

| Endpoint               | Entry Point              | Description                       |
|------------------------|--------------------------|-----------------------------------|
| `process-invoice`      | `process_invoice_http`   | Traitement OCR + extraction       |
| `learn-supplier`       | `learn_supplier_http`    | Enregistrer un nouveau fournisseur |
| `health-check`         | `health_http`            | Health check monitoring           |

## Securite

### Couche 1 : IAM (Cloud Functions)
- `--no-allow-unauthenticated` sur tous les endpoints
- Service account dedie avec permissions minimales
- Workload Identity Federation pour CI/CD (pas de cle JSON)

### Couche 2 : API Key applicative
- Header `X-API-Key` sur chaque requete
- Cle stockee dans **Secret Manager** (`invoice-api-key`)
- Montee dans Cloud Function via `--set-secrets`
- Comparaison timing-safe (`hmac.compare_digest`)

### Couche 3 : Validation des entrees
- Pydantic `ProcessRequest` avec `field_validator`
- IDs sanitises : `^[A-Za-z0-9_-]{1,128}$`
- Content-Type valide (application/json ou multipart/form-data)
- Taille batch limitee a 50 fichiers max

### Couche 4 : Authentification Drive
- L'Apps Script transmet son `ScriptApp.getOAuthToken()` dans `access_token`
- Le backend utilise ce token pour acceder aux fichiers Drive de l'utilisateur
- Pas de Service Account avec acces global au Drive

## Flux de traitement

### Flux normal (depuis Drive Add-on)

```
1. Utilisateur selectionne fichier(s) dans Drive
2. Apps Script verifie les permissions (UserManager)
3. CloudFunctionClient.processFile() envoie :
   - file_id, company_id, dry_run, access_token
4. Backend telecharge le fichier via Drive API (avec le token utilisateur)
5. Pipeline extrait : supplier, date, amount, invoice_number
6. Calcul du quarter TVA selon le calendrier de la societe
7. Construction du nom : [Prefix_]Supplier_#Num_DD-MM-YYYY_Amount[_Q1-2025].ext
8. Si dry_run=false : rename + move dans Drive
9. Retour JSON avec resultats
```

### Flux batch

```
1. Utilisateur selectionne un dossier ou plusieurs fichiers
2. Apps Script appelle CloudFunction.processBatch() (max 10 par lot)
3. Backend traite sequentiellement, retourne un tableau de resultats
4. Apps Script cree les dossiers quarter (DriveOps.ensureQuarterFolder)
5. Apps Script deplace/renomme chaque fichier (DriveOps.moveAndRename)
```

## Multi-societe

### Configuration

Chaque societe definit :
```javascript
{
  id: 'brams_tech_llc',
  name: 'BRAMS Technologies LLC',
  country: 'UAE',
  vat_calendar: 'uae_trn_feb',      // Calendrier TVA specifique
  root_folder_id: '1xyz...',         // Dossier racine Drive
  inbox_folder_name: 'Inbox',
  accounting_prefixes: ['PUR', 'Pyt Vch'],
  folder_template: '{year}/{quarter}-{year}'
}
```

### Calendriers TVA supportes

| Calendar          | Q1          | Q2          | Q3          | Q4          |
|-------------------|-------------|-------------|-------------|-------------|
| `uae_trn_feb`    | Feb-Apr     | May-Jul     | Aug-Oct     | Nov-Jan     |
| `morocco_standard`| Jan-Mar    | Apr-Jun     | Jul-Sep     | Oct-Dec     |

## Roles et permissions (RBAC)

| Role      | Permissions                                    |
|-----------|-----------------------------------------------|
| `admin`   | upload, process, configure, view_history, manage_users |
| `finance` | upload, process, view_history                  |
| `viewer`  | view_history, download                         |

Stockage : `PropertiesService.getScriptProperties()` cle `USERS_CONFIG`

## Observabilite

### Structured Logging
- Format JSON compatible Cloud Logging
- Champs : `severity`, `message`, `module`, `function`, `timestamp`, `correlation_id`
- `StructuredFormatter` dans main.py

### Correlation ID
- UUID genere par requete (`correlation_id`)
- Present dans tous les logs et la reponse JSON
- Permet le suivi de bout en bout

### Health Check
- Endpoint `/health-check` retourne `{"status": "ok", "version": "5.0"}`
- Utilisable par Cloud Monitoring uptime checks

## Deploiement

### CI/CD (GitHub Actions)

```yaml
# Tests sur Python 3.11 + 3.12
# Deploiement automatique sur push main
# 3 Cloud Functions deployees separement
```

### Configuration Cloud Functions

| Endpoint          | Memory  | Timeout | Max Instances |
|-------------------|---------|---------|---------------|
| `process-invoice` | 1 Gi    | 300s    | 10            |
| `learn-supplier`  | 256 Mi  | 30s     | 3             |
| `health-check`    | 128 Mi  | 10s     | 3             |

### Secrets requis dans GitHub

| Secret                | Description                           |
|-----------------------|---------------------------------------|
| `WIF_PROVIDER`        | Workload Identity Federation provider |
| `WIF_SERVICE_ACCOUNT` | Service account for deployment        |
| `CF_SERVICE_ACCOUNT`  | Runtime service account for functions |

### Secret Manager

| Secret            | Description                  |
|-------------------|------------------------------|
| `invoice-api-key` | Cle API pour X-API-Key header |

## Structure des dossiers Drive

```
Societe Root Folder/
  Inbox/               <- Fichiers a traiter
  2025/
    Q1-2025/           <- Factures classees par quarter
    Q2-2025/
  2024/
    Q4-2024/
```

Template configurable par societe :
- UAE : `{year}/{quarter}-{year}` -> `2025/Q1-2025/`
- Maroc : `{year}/T{quarter_num}-{year}` -> `2025/T1-2025/`

## Format de nommage

```
[Prefix_]SupplierName_#InvoiceNumber_DD-MM-YYYY_AmountCurrency[_Q1-2025].extension
```

Exemples :
- `PUR_Etisalat_#B-123-456_15-01-2025_150.00AED_Q4-2024.pdf`
- `AWS_#INV-987654_01-02-2025_45.99USD_Q1-2025.pdf`
- `Hilton_#H2025-001_20-03-2025_500.00AED_Q1-2025.pdf`

## Tests

118 tests couvrant :

1. **API key security** - Rejet sans cle, mauvaise cle, acceptation bonne cle
2. **CORS** - Preflight OPTIONS, headers dans les reponses
3. **Input validation** - Body vide, IDs manquants, content-type invalide, injection SQL
4. **Dry run** - Flag dans ProcessRequest, default false
5. **Multi-company** - company_id dans requete et pipeline
6. **Correlation ID** - Present dans reponse, absent si non fourni
7. **Structured logging** - Format JSON valide
8. **Health check** - Status ok, version 5.0
9. **Learn supplier** - Securite API key, validation nom fournisseur
10. **Model defaults** - Listes mutables non partagees entre instances
