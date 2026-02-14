// ============================================================
// UserManager.gs - Roles et permissions
// Invoice Manager V5
//
// Roles:
//   admin   - Tout acceder, configurer, gerer les utilisateurs
//   finance - Traiter et voir l'historique
//   viewer  - Consultation seule
// ============================================================

var ROLES = {
  admin:   ['upload', 'process', 'configure', 'view_history', 'manage_users'],
  finance: ['upload', 'process', 'view_history'],
  viewer:  ['view_history', 'download']
};

var UserManager = {

  /**
   * Recupere le role d'un utilisateur.
   *
   * @param {string} email - Adresse email
   * @return {string|null} Role ('admin', 'finance', 'viewer') ou null
   */
  getRole: function(email) {
    if (!email) return null;
    var users = this._getUsers();
    var normalizedEmail = email.toLowerCase().trim();
    if (users[normalizedEmail]) {
      return users[normalizedEmail].role;
    }
    return null;
  },

  /**
   * Verifie si l'utilisateur a une permission specifique.
   *
   * @param {string} email - Adresse email
   * @param {string} action - Action a verifier (ex: 'process', 'configure')
   * @return {boolean}
   */
  hasPermission: function(email, action) {
    var role = this.getRole(email);
    if (!role) return false;
    return ROLES[role] && ROLES[role].indexOf(action) !== -1;
  },

  /**
   * Recupere les IDs des societes accessibles par un utilisateur.
   *
   * @param {string} email - Adresse email
   * @return {Array<string>} Liste des company IDs
   */
  getCompanies: function(email) {
    if (!email) return [];
    var users = this._getUsers();
    var normalizedEmail = email.toLowerCase().trim();
    if (users[normalizedEmail]) {
      return users[normalizedEmail].companies || [];
    }
    return [];
  },

  /**
   * Ajoute ou modifie un utilisateur (admin seulement).
   *
   * @param {string} adminEmail - Email de l'admin effectuant la modification
   * @param {string} targetEmail - Email de l'utilisateur a modifier
   * @param {string} role - Role a assigner ('admin', 'finance', 'viewer')
   * @param {Array<string>} companies - IDs des societes accessibles
   */
  setUser: function(adminEmail, targetEmail, role, companies) {
    if (!this.hasPermission(adminEmail, 'manage_users')) {
      throw new Error('Permission refusee : vous n\'etes pas admin');
    }

    if (!ROLES[role]) {
      throw new Error('Role invalide : ' + role +
        '. Roles valides : ' + Object.keys(ROLES).join(', '));
    }

    var users = this._getUsers();
    users[targetEmail.toLowerCase().trim()] = {
      role: role,
      companies: companies || []
    };
    this._saveUsers(users);
    Logger.log('Utilisateur mis a jour: ' + targetEmail + ' -> ' + role);
  },

  /**
   * Supprime un utilisateur (admin seulement).
   *
   * @param {string} adminEmail - Email de l'admin
   * @param {string} targetEmail - Email de l'utilisateur a supprimer
   */
  removeUser: function(adminEmail, targetEmail) {
    if (!this.hasPermission(adminEmail, 'manage_users')) {
      throw new Error('Permission refusee');
    }

    var users = this._getUsers();
    var normalizedTarget = targetEmail.toLowerCase().trim();

    // Empecher un admin de se supprimer lui-meme
    if (normalizedTarget === adminEmail.toLowerCase().trim()) {
      throw new Error('Vous ne pouvez pas supprimer votre propre compte');
    }

    delete users[normalizedTarget];
    this._saveUsers(users);
    Logger.log('Utilisateur supprime: ' + targetEmail);
  },

  /**
   * Liste tous les utilisateurs (admin seulement).
   *
   * @param {string} adminEmail - Email de l'admin
   * @return {Object} Map email -> {role, companies}
   */
  listUsers: function(adminEmail) {
    if (!this.hasPermission(adminEmail, 'manage_users')) {
      throw new Error('Permission refusee');
    }
    return this._getUsers();
  },

  /**
   * Charge la config utilisateurs depuis Script Properties.
   * @private
   */
  _getUsers: function() {
    var data = PropertiesService.getScriptProperties()
      .getProperty('USERS_CONFIG');
    return data ? JSON.parse(data) : {};
  },

  /**
   * Sauvegarde la config utilisateurs dans Script Properties.
   * @private
   */
  _saveUsers: function(users) {
    PropertiesService.getScriptProperties()
      .setProperty('USERS_CONFIG', JSON.stringify(users));
  }
};
