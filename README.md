# NAS

## Contenu du projet

- **intent.json**
  Fichier JSON décrivant l'intention réseau (topologie, links, etc.).

- **create_config.py**  
  Lit le fichier intent.json, alloue les adresses IP aux interfaces et génère les fichiers de configuration dans le dossier de config.  
  À la fin du script, il invoque également la fonction d'analyse des configurations et de visualisation de la topologie.

- **addresses.py**  
  Permet d'analyser les fichiers de configuration des routeurs et de générer un résumé des interfaces avec leurs adresses IP, facilitant ainsi la gestion et la documentation du réseau.

- **create_graph.py**  
  Génère une représentation graphique de la topologie du réseau à partir du fichier JSON et du résumé d'interfaces (`interface_summary.txt`).  
  Le graphique peut être affiché ainsi qu'enregistré sous forme d'image.

- **drag_drop_bot.py**  
  Ce script déplace les fichiers de configuration générés dans le dossier de configs vers le répertoire requis par GNS3.  
  Avant de déplacer, il supprime les anciens fichiers `.cfg` et les fichiers NVRAM pour éviter les conflits.

## Prérequis

- **Python 3** doit être installé sur votre machine.
- Installation des modules Python requis :
  - `networkx`
  - `matplotlib`
- Modifier la variable destination dans le script `drag_drop_bot.py` pour pointer vers le répertoire de votre projet GNS3.

Vous pouvez installer les dépendances via pip par exemple :

```sh
pip install networkx matplotlib
```

## Utilisation
Voici les étapes à suivre pour utiliser le projet :
1. Executez le script `create_config.py` pour générer les fichiers de configuration à partir du fichier `intent.json`.
2. Executez le script `addresses.py` pour analyser les fichiers de configuration et générer un résumé des interfaces.
3. Executez le script `drag_drop_bot.py` pour déplacer les fichiers de configuration vers le répertoire requis par GNS3.
