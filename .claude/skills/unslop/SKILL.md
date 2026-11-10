---
name: unslop
description: Relit un texte français pour repérer les tics d'écriture IA (formules creuses, superlatifs vides, structures répétitives, typographie chargée) et, sur demande, le réécrit sans changer aucun fait. À utiliser quand on demande de « déslopifier », « humaniser », « rendre plus naturel » un texte, quand un texte « sonne IA » ou « sonne ChatGPT », ou avec /unslop. Audit par défaut ; réécriture seulement si elle est demandée.
user-invocable: true
argument-hint: "[audit · réécrire] [texte ou chemin de fichier]"
---

# unslop : relecture des tics d'écriture IA (français)

Ce skill sert à relire les textes du site (descriptions de sorties, README,
docs, messages de commit) et à les débarrasser des tournures typiques des
textes générés par IA. Il ne traite que le français ; pour un texte dans
une autre langue, le dire et s'arrêter.

## Choisir le mode

- **audit** (par défaut, et toujours quand on donne un fichier sans dire
  « réécris ») : relever les problèmes, ne rien modifier.
- **réécrire** (seulement sur demande explicite : `/unslop réécrire …`,
  « réécris », « corrige-le ») : diagnostic d'abord, puis réécriture.

Dans le doute, faire l'audit et proposer la réécriture.

## Contrat (à respecter dans les deux modes)

1. **Aucun fait ajouté, retiré ou changé.** Chiffres, distances, dénivelés,
   PK, horaires, noms de lieux et de commerces, dates, liens, chemins de
   fichiers et code restent identiques. Pas d'adjectif qui ajoute une
   information absente (« ombragé », « facile », « familial ») : c'est la
   règle 1 d'`AGENTS.md`, ne jamais inventer de données.
2. **Même sens, même registre.** Garder le tutoiement ou le vouvoiement,
   le ton (pratique, chaleureux, technique) et les informations utiles.
3. **Ne pas toucher** au frontmatter (`--- … ---`), aux blocs de code, aux
   tableaux de données ni aux URL.
4. **Contenu des sorties** : `rides/*/description.md` et `points.md` ne se
   modifient que sur demande explicite (règle 4 d'`AGENTS.md`). Sinon,
   audit seulement.
5. **Ne pas sur-corriger.** Un texte déjà sobre se rend tel quel, en le
   disant. Un terme technique ou un superlatif justifié par un fait n'est
   pas un tic (voir « Faux positifs » dans le catalogue).

## Méthode

1. Lire `references/tics-fr.md` (le catalogue) et, pour une réécriture,
   `references/exemples.md`.
2. **Diagnostic** : parcourir le texte et noter chaque tic avec sa ligne
   (ou sa phrase), sa catégorie du catalogue et une proposition.
3. **Réécriture** (mode réécrire seulement) : phrase par phrase, retirer
   le tic en gardant l'information. Préférer couper que paraphraser :
   souvent, la phrase sans la formule creuse suffit.
4. **Vérification** : comparer avant et après. Chaque nombre, nom propre,
   lien et élément de code de l'original doit se retrouver à l'identique.
   S'il en manque un, corriger avant de rendre.

## Format de sortie

**Audit**

```
## Problèmes relevés
- L12 · Formule creuse · « Plongez au cœur de la garrigue » → « La trace traverse la garrigue »
- …

## Appréciation
Deux phrases : le niveau global (sobre, quelques tics, très marqué) et
les deux ou trois corrections les plus utiles.
```

**Réécriture**

```
## Texte réécrit
…

## Vérification
- Faits préservés : oui (liste des chiffres et noms contrôlés)
- Tics restants : aucun / lesquels et pourquoi ils restent
- Part du texte modifiée : environ N %
```

Pour un fichier, en mode réécrire, appliquer les changements avec l'outil
d'édition et résumer ensuite ; ne pas recopier tout le fichier.

## Source

Méthode inspirée de [theclaymethod/unslop](https://github.com/theclaymethod/unslop)
(licence MIT déclarée par l'auteur) : audit avant réécriture, deux passes,
préservation des faits. Le catalogue et les exemples sont propres à ce
dépôt et écrits pour le français.
