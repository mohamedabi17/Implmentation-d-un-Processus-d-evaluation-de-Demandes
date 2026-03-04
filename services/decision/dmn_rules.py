"""
Règles de Décision DMN pour l'approbation de prêt
Basé sur la table de décision du chapitre 3 du cours BPM
"""
from shared.models import Decision


class DMNDecisionEngine:
    """
    Moteur de décision DMN pour l'évaluation des demandes de prêt
    Implémente la logique de la table de décision
    """
    
    @staticmethod
    def evaluer_demande(
        score_credit: int,
        revenu_annuel: float,
        montant_demande: float,
        ratio_dette_revenu: float,
        valeur_bien: float,
        ratio_pret_valeur: float
    ) -> tuple[Decision, str, float]:
        """
        Évalue une demande de prêt selon les règles DMN
        
        Args:
            score_credit: Score de crédit (300-850)
            revenu_annuel: Revenu annuel du client
            montant_demande: Montant du prêt demandé
            ratio_dette_revenu: Ratio dette/revenu en %
            valeur_bien: Valeur estimée du bien
            ratio_pret_valeur: Ratio prêt/valeur (LTV) en %
            
        Returns:
            Tuple (Decision, Raison, Score global)
        """
        score_global = 0.0
        raisons = []
        
        if score_credit >= 750:
            score_global += 35
            raisons.append("Excellent score de crédit")
        elif score_credit >= 700:
            score_global += 30
            raisons.append("Très bon score de crédit")
        elif score_credit >= 650:
            score_global += 20
            raisons.append("Bon score de crédit")
        elif score_credit >= 600:
            score_global += 10
            raisons.append("Score de crédit acceptable")
        else:
            score_global += 0
            raisons.append("Score de crédit insuffisant")
        
        ratio_revenu_montant = revenu_annuel / montant_demande
        
        if ratio_revenu_montant >= 5:
            score_global += 25
            raisons.append("Excellent ratio revenu/montant")
        elif ratio_revenu_montant >= 4:
            score_global += 20
            raisons.append("Très bon ratio revenu/montant")
        elif ratio_revenu_montant >= 3:
            score_global += 15
            raisons.append("Bon ratio revenu/montant")
        elif ratio_revenu_montant >= 2:
            score_global += 5
            raisons.append("Ratio revenu/montant limite")
        else:
            score_global += 0
            raisons.append("Ratio revenu/montant insuffisant")
        
        if ratio_dette_revenu <= 25:
            score_global += 20
            raisons.append("Excellent ratio dette/revenu")
        elif ratio_dette_revenu <= 30:
            score_global += 15
            raisons.append("Bon ratio dette/revenu")
        elif ratio_dette_revenu <= 35:
            score_global += 10
            raisons.append("Ratio dette/revenu acceptable")
        elif ratio_dette_revenu <= 40:
            score_global += 5
            raisons.append("Ratio dette/revenu élevé")
        else:
            score_global += 0
            raisons.append("Ratio dette/revenu trop élevé")
        
        if ratio_pret_valeur <= 70:
            score_global += 20
            raisons.append("Excellent ratio prêt/valeur")
        elif ratio_pret_valeur <= 80:
            score_global += 15
            raisons.append("Bon ratio prêt/valeur")
        elif ratio_pret_valeur <= 90:
            score_global += 10
            raisons.append("Ratio prêt/valeur acceptable")
        elif ratio_pret_valeur <= 95:
            score_global += 5
            raisons.append("Ratio prêt/valeur élevé")
        else:
            score_global += 0
            raisons.append("Ratio prêt/valeur trop élevé")
        
        raison_finale = " | ".join(raisons)
        
        # Table de décision principale
        if score_credit >= 700 and ratio_dette_revenu <= 40 and ratio_pret_valeur <= 90:
            if score_global >= 75:
                return Decision.APPROUVE, f"✓ Demande approuvée - {raison_finale}", score_global
            else:
                return Decision.ETUDE, f"⚠ Nécessite étude approfondie - {raison_finale}", score_global
        
        elif score_credit >= 650 and ratio_dette_revenu <= 35 and ratio_pret_valeur <= 85:
            if score_global >= 70:
                return Decision.APPROUVE, f"✓ Demande approuvée avec conditions - {raison_finale}", score_global
            else:
                return Decision.ETUDE, f"⚠ Nécessite étude approfondie - {raison_finale}", score_global
        
        elif score_credit >= 600 and ratio_dette_revenu <= 30 and ratio_pret_valeur <= 80:
            if score_global >= 60:
                return Decision.ETUDE, f"⚠ Demande nécessite étude - {raison_finale}", score_global
            else:
                return Decision.REJETE, f"✗ Demande rejetée - {raison_finale}", score_global
        
        else:
            return Decision.REJETE, f"✗ Critères minimums non atteints - {raison_finale}", score_global
    
    @staticmethod
    def calculer_taux_interet(score_credit: int, ratio_pret_valeur: float) -> float:
        """
        Calcule le taux d'intérêt proposé basé sur le profil de risque
        
        Args:
            score_credit: Score de crédit
            ratio_pret_valeur: Ratio prêt/valeur
            
        Returns:
            Taux d'intérêt annuel en %
        """
        taux_base = 3.5  # Taux de base
        
        # Ajustement selon le score de crédit
        if score_credit >= 750:
            ajustement_credit = -0.5
        elif score_credit >= 700:
            ajustement_credit = 0.0
        elif score_credit >= 650:
            ajustement_credit = 0.5
        elif score_credit >= 600:
            ajustement_credit = 1.0
        else:
            ajustement_credit = 2.0
        
        # Ajustement selon le LTV
        if ratio_pret_valeur <= 70:
            ajustement_ltv = -0.3
        elif ratio_pret_valeur <= 80:
            ajustement_ltv = 0.0
        elif ratio_pret_valeur <= 90:
            ajustement_ltv = 0.3
        else:
            ajustement_ltv = 0.7
        
        taux_final = taux_base + ajustement_credit + ajustement_ltv
        
        return round(max(2.0, min(8.0, taux_final)), 2)
