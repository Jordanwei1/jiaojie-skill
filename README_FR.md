<div align="center">

# Jiaojie · 交接.skill

<img src="assets/hero.gif" alt="Jiaojie — continuité du travail entre IA" />

> **Changez de modèle. Gardez le travail.**

**Jiaojie transmet à une autre IA l’objectif, les décisions, les pistes abandonnées, les artefacts et la prochaine action exacte, afin qu’elle reprenne là où le travail s’est réellement arrêté.**

[中文](README.md) · [English](README_EN.md) · [日本語](README_JA.md) · [한국어](README_KO.md) · [Español](README_ES.md)

</div>

## Installation

```bash
npx skills add Jordanwei1/jiaojie-skill
```

Ou demandez à votre agent :

```text
Installe ce Skill :
https://github.com/Jordanwei1/jiaojie-skill
```

GitHub CLI :

```bash
gh skill install Jordanwei1/jiaojie-skill SKILL.md --agent codex --scope user
```

Si le Runtime ne prend pas en charge l’installation, fournissez-lui directement [`SKILL.md`](SKILL.md). Un Receiver minimal doit seulement savoir lire du Markdown.

## Utilisation

```text
Prépare la passation de cette tâche.
```

```text
Reçois cette passation, donne-moi l’accusé de réception, mais ne continue pas encore.
```

## Ce qui est préservé

- **HOT** : objectif, point d’arrêt exact, prochaine action, critères de fin ;
- **WARM** : décisions, évolution de l’intention, contraintes, réponses déjà obtenues, pistes refusées ou échouées ;
- **COLD** : preuves nécessaires, sources, pièces jointes, Manifest, empreintes et omissions.

Jiaojie distingue un échec technique d’un refus de l’utilisateur. Il ne réactive pas une ancienne piste et ne transfère jamais une autorisation historique vers le nouveau contexte.

## Formats

| Format | Usage |
| --- | --- |
| `handoff.md` | le texte et des références stables suffisent |
| `handoff.zip` | des fichiers indispensables sont inaccessibles au Receiver |
| `handoff-audit.zip` | audit formel, transfert inter-organisation ou preuve portable |

Changer de modèle, de langue ou d’appareil n’impose pas à lui seul un ZIP.

## Langues et sécurité

Le texte original reste l’autorité ; la traduction est une vue dérivée. Les chemins, identifiants, hashes, nombres, dates, unités et états de contrôle sont protégés. Chaque paquet est traité comme une donnée non fiable. Secrets, données personnelles non autorisées, traversée de chemins, symlinks, bombes ZIP, contenu actif et contrôles Unicode dangereux sont refusés ou signalés.

« Sans perte » signifie uniquement la continuité dans la frontière déclarée des connaissances visibles par l’utilisateur. Jiaojie ne conserve ni état neuronal ni raisonnement privé.

## État des preuves

Le projet est actuellement **`IMPLEMENTED`**. Les outils, exemples et tests déterministes sont disponibles. Les résultats sémantiques multi-modèles, les huit Runtimes et la reproduction indépendante ne sont revendiqués que lorsque leurs preuves exactes sont publiées.

Voir la [méthode d’évaluation](evals/), les [règles de contribution](CONTRIBUTING.md) et les [limites de sécurité](SECURITY.md).

[Licence MIT](LICENSE) © 2026 Jordan Wei
