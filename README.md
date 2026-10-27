# Environnement personnel — macOS et Linux

Ce dépôt contient la configuration qui me suit d'une machine ou d'une entreprise à l'autre : Bash, complétions, historique, outils de développement, Git et VS Code. Les paramètres d'une organisation restent dans des fichiers locaux, hors du dépôt.

## Ce qui est installé

- Bash 5, `bash-completion`, fzf, historique en ajout (`histappend`) et prompt personnel sur trois lignes.
- Git, jq, Go et gopls ; Rust stable avec Cargo, Clippy, rustfmt et rust-analyzer si aucune installation Rust n'existe déjà.
- Terraform, Terragrunt, kubectl, Helm 3, Helmfile, k9s, Kustomize, kubeconform et kops.
- AWS CLI, authentification IAM Kubernetes, Cilium/Hubble, SOPS et Gitleaks.
- Clients Docker/Compose et helper ECR. Le moteur Docker local se choisit et s'installe séparément.
- Préférences VS Code : terminal Bash, thème Flatland Monokai, icônes Material et extensions définies dans `packages.json`.

`packages.json` est la liste de référence. Les paquets utilisent les versions disponibles chez Homebrew au moment de l'installation, sans mise à niveau volontaire des paquets déjà présents. Helm reste sur la branche 3. Ce dépôt ne constitue pas un verrouillage exact des versions pour les projets : les contraintes propres à un projet doivent rester dans celui-ci.

## Installer sur une nouvelle machine

Le socle CLI utilise [Homebrew sur macOS et Linux](https://docs.brew.sh/Homebrew-on-Linux). Linux doit être une distribution compatible avec Homebrew, avec Bash, curl, Git et ses outils de compilation installés. Sur Debian/Ubuntu, les prérequis usuels sont `build-essential procps curl file git`. Sur macOS, installer les outils de ligne de commande Apple si nécessaire (`xcode-select --install`).

```bash
git clone https://github.com/bilelaffes/dotfiles.git "$HOME/dotfiles"
cd "$HOME/dotfiles"
./bootstrap.sh
```

`bootstrap.sh` installe Homebrew depuis son installateur officiel s'il manque, puis Python 3.9+ si nécessaire, et lance l'installation. L'installation de ces prérequis peut demander des droits administrateur. Homebrew et Python sont conservés à la désinstallation.

Si Homebrew et Python sont déjà disponibles :

```bash
./install.sh --dry-run
./install.sh
```

Sur **macOS**, VS Code est installé s'il manque. Sur **Linux**, installer [VS Code](https://code.visualstudio.com/docs/setup/linux) avec le gestionnaire de la distribution avant `./install.sh` et rendre la commande `code` accessible. Le script configure alors VS Code et installe ses extensions. Si `code` manque, les autres éléments sont traités et le script indique que l'installation est incomplète : installer VS Code puis relancer.

Pour installer uniquement les fichiers de configuration, sans téléchargement de paquets ni d'extensions :

```bash
./install.sh --configs-only
```

Ajouter `--no-vscode` pour ignorer complètement VS Code. Les commandes sont à lancer avec son compte utilisateur, sans `sudo`.

Fermer puis rouvrir le terminal. Dans un terminal Bash, `printf '%s\n' "$BASH_VERSION"` doit afficher une version 5. Le shell enregistré du compte n'est pas modifié : les nouveaux terminaux Bash passent automatiquement au Bash Homebrew. Sur un compte macOS utilisant Zsh, choisir `/bin/bash -l` comme commande du terminal ; le profil intégré VS Code est configuré pour cela.

## Fichiers personnels et réglages locaux

| Source dans le dépôt | Destination |
| --- | --- |
| `shell/bashrc` | `~/.bashrc` |
| `shell/bash_profile` | `~/.bash_profile` |
| `shell/inputrc` | `~/.inputrc` |
| `shell/config/` | `~/.config/personal-shell` |
| `git/config` et `git/ignore` | `~/.config/personal-git/` |
| `vscode/settings.json` | Préférences utilisateur VS Code de la plateforme |

Les destinations sont des liens vers le dépôt. Conserver le dossier cloné tant que l'environnement est installé. Modifier un fichier lié modifie donc le fichier versionné : relire `git diff` avant de publier les changements. Les préférences VS Code existantes sont sauvegardées puis remplacées, pas fusionnées.

Les anciens fichiers sont sauvegardés dans `~/.local/state/dotfiles/backups/`. Ils ne sont pas chargés automatiquement : cela évite de réintroduire les intégrations de l'ancienne organisation.

Les hooks locaux suivants restent hors du dépôt et sont conservés lors de la désinstallation :

- `~/.bashrc.local` : alias, fonctions et intégrations shell de l'entreprise.
- `~/.bash_profile.local` : environnement spécifique à la machine, au démarrage d'un shell de connexion.
- `~/.gitconfig.local` : identité Git personnelle/professionnelle et éventuels `includeIf` par dossier.

Des modèles sont fournis dans `examples/`. L'installateur ajoute seulement un bloc `include` à un `.gitconfig` existant : il ne recopie pas l'identité professionnelle dans le dépôt. Si ce fichier est déjà un lien géré par un autre outil, il indique l'inclusion à réaliser manuellement.

Les configurations SSH, AWS, Kubernetes, Docker, les comptes, jetons, clés et historiques ne sont ni exportés dans ce dépôt ni supprimés automatiquement. Les intégrations propres à l'employeur ne sont pas importées. Les extensions VS Code sont réinstallées depuis leurs identifiants ; leurs connexions, caches et comptes ne sont pas copiés.

## Retirer l'environnement

Prévisualiser, puis restaurer les fichiers remplacés :

```bash
./uninstall.sh --dry-run
./uninstall.sh
```

Retirer également les paquets, extensions et l'installation Rust **ajoutés par ce dépôt** :

```bash
./uninstall.sh --purge-tools --dry-run
./uninstall.sh --purge-tools
```

L'inventaire de propriété est conservé dans `~/.local/state/dotfiles/state.json`. Un outil déjà présent avant l'installation n'est pas adopté et reste installé. L'état identifie aussi le préfixe Homebrew utilisé : une purge est refusée si une autre installation Homebrew a pris sa place. Les dépendances Homebrew ne sont pas supprimées globalement et les données des applications ne sont pas effacées. Un paquet encore nécessaire à un autre peut rester installé ; le script le signale et conserve son suivi pour une prochaine tentative.

Rust préexistant est conservé sans modification. Une nouvelle installation Rust appartient au dépôt uniquement lorsqu'elle a été créée dans `~/.local/share/dotfiles/rust/`, avec son marqueur de propriété. `--purge-tools` peut retirer cet environnement dédié, y compris les outils Cargo ajoutés ensuite dedans.

Si un lien a été remplacé manuellement par un fichier, la désinstallation garde ce fichier et sa sauvegarde et signale le conflit. Après avoir conservé ses modifications, déplacer le fichier en conflit hors de la destination puis relancer la désinstallation pour restaurer l'original. Ne pas effacer le dossier d'état avant d'avoir terminé.

Les sauvegardes et l'état restent hors Git. Ils peuvent contenir les anciens réglages professionnels : les examiner avant de supprimer définitivement son compte ou de rendre une machine. Le script ne révoque aucun accès et ne purge pas les trousseaux d'identifiants.

## Faire évoluer le dépôt

1. Modifier les fichiers personnels dans `shell/`, `git/` ou `vscode/`.
2. Ajouter/retirer les outils souhaités dans `packages.json`.
3. Lancer les vérifications ci-dessous et examiner `git diff`.
4. Enregistrer et pousser les changements une fois relus.
5. Sur une autre machine : `git pull --ff-only`, puis `./install.sh`.

Relancer l'installation complète uniquement ce qui manque et ne crée pas une nouvelle sauvegarde à chaque passage. Retirer un outil de `packages.json` ne le désinstalle pas immédiatement ; son suivi local est conservé pour la désinstallation. Déplacer un clone est pris en charge en relançant son `install.sh` depuis le nouveau chemin. Les versions ne sont pas mises à niveau par une commande de mise à jour implicite.

## Vérifier sans toucher à son environnement

```bash
python3 -m unittest discover -s tests -v
```

Les tests utilisent des dossiers temporaires explicites et des faux gestionnaires de paquets. Ils couvrent notamment la restauration, les réinstallations, les conflits et la propriété des outils. Ils ne téléchargent rien et ne contactent aucun cluster.

Une installation de configuration isolée peut aussi être examinée avec `--target-home CHEMIN --configs-only`. `--purge-tools` est interdit pour un domicile alternatif. Le mode `--dry-run` n'applique aucune configuration et n'installe ni ne supprime d'outils ; les commandes de lecture des gestionnaires peuvent utiliser leurs propres caches.
