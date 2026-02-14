// ============================================================
// DriveOperations.gs - Gestion des fichiers et dossiers Drive
// Invoice Manager V5
// ============================================================

var DriveOps = {

  /**
   * Liste les fichiers PDF/images dans un dossier.
   * @param {string} folderId - ID du dossier Drive
   * @return {Array} Liste d'objets {id, name, mimeType, size, created}
   */
  listInboxFiles: function(folderId) {
    if (!folderId) {
      throw new Error('folderId requis');
    }

    var query = "'" + folderId + "' in parents and trashed=false and (" +
      "mimeType='application/pdf' or " +
      "mimeType='image/jpeg' or " +
      "mimeType='image/png' or " +
      "mimeType='image/tiff'" +
    ")";

    var files = [];
    var pageToken = null;

    do {
      var params = {
        q: query,
        fields: 'nextPageToken, files(id, name, mimeType, size, createdTime)',
        orderBy: 'createdTime desc',
        pageSize: 100
      };
      if (pageToken) {
        params.pageToken = pageToken;
      }

      var response = Drive.Files.list(params);
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
      pageToken = response.nextPageToken;
    } while (pageToken);

    return files;
  },

  /**
   * Cree l'arborescence de dossiers Quarter si elle n'existe pas.
   * Ex: rootFolder / 2025 / Q1-2025 /
   *
   * @param {string} rootFolderId - Dossier racine de la societe
   * @param {string|number} year - Annee (ex: 2025)
   * @param {string} quarterName - Nom du quarter (ex: "Q1-2025")
   * @return {string} ID du dossier quarter
   */
  ensureQuarterFolder: function(rootFolderId, year, quarterName) {
    if (!rootFolderId) {
      throw new Error('rootFolderId requis pour creer les dossiers Quarter');
    }

    // Chercher ou creer le dossier annee
    var yearFolderId = this._findOrCreateFolder(rootFolderId, String(year));

    // Chercher ou creer le dossier quarter
    var quarterFolderId = this._findOrCreateFolder(yearFolderId, quarterName);

    return quarterFolderId;
  },

  /**
   * Deplace et renomme un fichier dans le dossier cible.
   * Gere les conflits de nom (ajoute un suffixe si necessaire).
   *
   * @param {string} fileId - ID du fichier a deplacer
   * @param {string} targetFolderId - ID du dossier cible
   * @param {string} newName - Nouveau nom du fichier
   * @return {Object} {fileId, newName, folderId}
   */
  moveAndRename: function(fileId, targetFolderId, newName) {
    if (!fileId || !targetFolderId || !newName) {
      throw new Error('fileId, targetFolderId et newName requis');
    }

    // Verifier s'il existe deja un fichier avec ce nom dans le dossier cible
    newName = this._ensureUniqueName(targetFolderId, newName);

    // Recuperer les parents actuels
    var file = Drive.Files.get(fileId, {fields: 'parents'});
    var previousParents = file.parents ? file.parents.join(',') : '';

    // Deplacer + renommer en une seule operation
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
   * Renomme un fichier sans le deplacer.
   *
   * @param {string} fileId - ID du fichier
   * @param {string} newName - Nouveau nom
   */
  rename: function(fileId, newName) {
    Drive.Files.update({name: newName}, fileId);
  },

  /**
   * Cherche un sous-dossier par nom, le cree s'il n'existe pas.
   * @private
   */
  _findOrCreateFolder: function(parentId, folderName) {
    // Echapper les guillemets dans le nom
    var safeName = folderName.replace(/'/g, "\\'");
    var query = "'" + parentId + "' in parents " +
      "and name='" + safeName + "' " +
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
    Logger.log('Dossier cree: ' + folderName + ' (ID: ' + folder.id + ')');
    return folder.id;
  },

  /**
   * S'assure que le nom est unique dans le dossier cible.
   * Si un fichier avec le meme nom existe, ajoute un suffixe _1, _2, etc.
   * @private
   */
  _ensureUniqueName: function(folderId, filename) {
    var safeName = filename.replace(/'/g, "\\'");
    var query = "'" + folderId + "' in parents " +
      "and name='" + safeName + "' " +
      "and trashed=false";

    var response = Drive.Files.list({q: query, fields: 'files(id)'});

    if (!response.files || response.files.length === 0) {
      return filename; // Nom unique, OK
    }

    // Ajouter un suffixe pour le rendre unique
    var ext = '';
    var base = filename;
    var dotIdx = filename.lastIndexOf('.');
    if (dotIdx > 0) {
      ext = filename.substring(dotIdx);
      base = filename.substring(0, dotIdx);
    }

    var counter = 1;
    var candidate = base + '_' + counter + ext;
    while (true) {
      var safeCandidate = candidate.replace(/'/g, "\\'");
      query = "'" + folderId + "' in parents " +
        "and name='" + safeCandidate + "' " +
        "and trashed=false";
      response = Drive.Files.list({q: query, fields: 'files(id)'});

      if (!response.files || response.files.length === 0) {
        Logger.log('Conflit de nom resolu: ' + filename + ' -> ' + candidate);
        return candidate;
      }
      counter++;
      candidate = base + '_' + counter + ext;

      if (counter > 100) {
        throw new Error('Impossible de trouver un nom unique pour: ' + filename);
      }
    }
  }
};
