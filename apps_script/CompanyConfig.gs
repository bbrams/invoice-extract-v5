// ============================================================
// CompanyConfig.gs - Configuration des societes
// Invoice Manager V5
//
// Stockee dans PropertiesService pour etre modifiable via l'UI.
// Chaque societe definit :
//   - Calendrier TVA (uae_trn, morocco_standard, etc.)
//   - Dossier racine Drive
//   - Dossier Inbox
//   - Prefixes comptables
//   - Template de dossier
// ============================================================

/**
 * Configuration par defaut des societes.
 * Utilisee lors du premier lancement.
 */
var DEFAULT_COMPANIES = [
  {
    id: 'brams_tech_llc',
    name: 'BRAMS Technologies LLC',
    country: 'UAE',
    vat_calendar: 'uae_trn_feb',
    root_folder_id: '',         // A configurer lors du setup
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
   * Recupere toutes les societes configurees.
   *
   * @return {Array<Object>} Liste des societes
   */
  getAll: function() {
    var data = PropertiesService.getScriptProperties()
      .getProperty('COMPANIES_CONFIG');
    return data ? JSON.parse(data) : DEFAULT_COMPANIES;
  },

  /**
   * Recupere les societes accessibles par un utilisateur.
   * Les admins sans restriction de societes voient tout.
   *
   * @param {string} email - Adresse email de l'utilisateur
   * @return {Array<Object>} Societes accessibles
   */
  getCompaniesForUser: function(email) {
    var userCompanyIds = UserManager.getCompanies(email);
    var allCompanies = this.getAll();

    if (userCompanyIds.length === 0) {
      // Pas de restriction = admin voit tout
      return allCompanies;
    }

    return allCompanies.filter(function(c) {
      return userCompanyIds.indexOf(c.id) !== -1;
    });
  },

  /**
   * Recupere une societe par son ID.
   *
   * @param {string} companyId - ID de la societe
   * @return {Object|null} La societe ou null
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
   * Met a jour la configuration d'une societe (admin seulement).
   *
   * @param {string} companyId - ID de la societe
   * @param {Object} updates - Champs a mettre a jour
   */
  update: function(companyId, updates) {
    var companies = this.getAll();
    var found = false;

    for (var i = 0; i < companies.length; i++) {
      if (companies[i].id === companyId) {
        Object.keys(updates).forEach(function(key) {
          companies[i][key] = updates[key];
        });
        found = true;
        break;
      }
    }

    if (!found) {
      throw new Error('Societe non trouvee: ' + companyId);
    }

    PropertiesService.getScriptProperties()
      .setProperty('COMPANIES_CONFIG', JSON.stringify(companies));
    Logger.log('Societe mise a jour: ' + companyId);
  },

  /**
   * Ajoute une nouvelle societe (admin seulement).
   *
   * @param {Object} company - Configuration de la societe
   */
  addCompany: function(company) {
    if (!company.id || !company.name) {
      throw new Error('id et name requis pour une societe');
    }

    var companies = this.getAll();

    // Verifier doublon
    for (var i = 0; i < companies.length; i++) {
      if (companies[i].id === company.id) {
        throw new Error('Societe avec ID "' + company.id + '" existe deja');
      }
    }

    companies.push(company);
    PropertiesService.getScriptProperties()
      .setProperty('COMPANIES_CONFIG', JSON.stringify(companies));
    Logger.log('Societe ajoutee: ' + company.name);
  },

  /**
   * Genere le nom du dossier quarter a partir du template de la societe.
   *
   * @param {string} companyId - ID de la societe
   * @param {string} quarter - Ex: "Q1"
   * @param {number} year - Ex: 2025
   * @return {string} Nom du dossier (ex: "Q1-2025")
   */
  getQuarterFolderName: function(companyId, quarter, year) {
    var company = this.getById(companyId);
    if (!company || !company.folder_template) {
      return quarter + '-' + year;
    }

    var quarterNum = quarter.replace('Q', '');
    return company.folder_template
      .replace('{year}', year)
      .replace('{quarter}', quarter)
      .replace('{quarter_num}', quarterNum);
  }
};
