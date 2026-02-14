// ============================================================
// CloudFunctionClient.gs - Communication avec le backend Python
// Invoice Manager V5
//
// Securite:
//   - API key stockee dans Script Properties (jamais en dur)
//   - Envoyee via header X-API-Key
//   - Timeout et retry configures
// ============================================================

/**
 * URL de la Cloud Function.
 * A mettre a jour apres deploiement.
 */
var CLOUD_FUNCTION_URL = PropertiesService.getScriptProperties()
  .getProperty('CLOUD_FUNCTION_URL') ||
  'https://us-central1-brams-private.cloudfunctions.net/process-invoice';

var API_KEY_PROPERTY = 'INVOICE_API_KEY';
var MAX_RETRIES = 2;
var TIMEOUT_MS = 60000; // 60 secondes

var CloudFunction = {

  /**
   * Envoie un fichier au backend Python pour OCR + extraction.
   *
   * @param {string} fileId - ID du fichier Drive
   * @param {string} companyId - ID de la societe pour le calendrier TVA
   * @param {boolean} dryRun - true = apercu seulement, pas de rename/move
   * @return {Object} Resultat de l'extraction
   */
  processFile: function(fileId, companyId, dryRun) {
    var apiKey = this._getApiKey();
    var userEmail = Session.getActiveUser().getEmail();

    var payload = {
      file_id: fileId,
      company_id: companyId || 'brams_tech_llc',
      dry_run: dryRun || false,
      include_vat_quarter: true,
      access_token: ScriptApp.getOAuthToken()
    };

    return this._callWithRetry(payload, apiKey);
  },

  /**
   * Traite un lot de fichiers (max 10).
   *
   * @param {Array<string>} fileIds - Liste des IDs de fichiers
   * @param {string} companyId - ID de la societe
   * @param {boolean} dryRun - Mode apercu
   * @return {Array<Object>} Resultats par fichier
   */
  processBatch: function(fileIds, companyId, dryRun) {
    if (!fileIds || fileIds.length === 0) {
      return [];
    }

    // Limiter a 10 fichiers par lot
    var batch = fileIds.slice(0, 10);
    var results = [];

    for (var i = 0; i < batch.length; i++) {
      try {
        var result = this.processFile(batch[i], companyId, dryRun);
        // Si the backend returned a batch response, extract individual results
        if (result.results && Array.isArray(result.results)) {
          result = result.results[0] || result;
        }
        result.status = 'success';
        results.push(result);
      } catch (e) {
        Logger.log('Erreur traitement fichier ' + batch[i] + ': ' + e.message);
        results.push({
          file_id: batch[i],
          status: 'error',
          error: e.message
        });
      }
    }

    return results;
  },

  /**
   * Appel HTTP avec retry automatique.
   * @private
   */
  _callWithRetry: function(payload, apiKey) {
    var lastError = null;

    for (var attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        var options = {
          method: 'POST',
          contentType: 'application/json',
          headers: {
            'X-API-Key': apiKey,
            'X-Request-Source': 'drive-addon'
          },
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        };

        var response = UrlFetchApp.fetch(CLOUD_FUNCTION_URL, options);
        var statusCode = response.getResponseCode();
        var body = response.getContentText();

        // Succes
        if (statusCode === 200) {
          return JSON.parse(body);
        }

        // Erreurs non-retryables
        if (statusCode === 400 || statusCode === 401 || statusCode === 403) {
          var errorData = {};
          try { errorData = JSON.parse(body); } catch (e) {}
          throw new Error('Erreur ' + statusCode + ': ' +
            (errorData.error || body).substring(0, 200));
        }

        // Erreurs retryables (5xx, timeout)
        lastError = new Error('Erreur serveur ' + statusCode + ': ' +
          body.substring(0, 200));
        Logger.log('Tentative ' + (attempt + 1) + ' echouee: ' + statusCode);

        if (attempt < MAX_RETRIES) {
          Utilities.sleep(Math.pow(2, attempt) * 1000); // Backoff: 1s, 2s
        }

      } catch (e) {
        if (e.message && (e.message.indexOf('400') >= 0 ||
            e.message.indexOf('401') >= 0 ||
            e.message.indexOf('403') >= 0)) {
          throw e; // Ne pas retrier les erreurs client
        }
        lastError = e;
        Logger.log('Tentative ' + (attempt + 1) + ' exception: ' + e.message);
        if (attempt < MAX_RETRIES) {
          Utilities.sleep(Math.pow(2, attempt) * 1000);
        }
      }
    }

    throw lastError || new Error('Echec apres ' + (MAX_RETRIES + 1) + ' tentatives');
  },

  /**
   * Recupere l'API key depuis Script Properties.
   * @private
   */
  _getApiKey: function() {
    var key = PropertiesService.getScriptProperties()
      .getProperty(API_KEY_PROPERTY);
    if (!key) {
      throw new Error(
        'API key non configuree. Un administrateur doit definir ' +
        API_KEY_PROPERTY + ' dans Script Properties.'
      );
    }
    return key;
  }
};
