# PDF to PLT

Convertisseur de logos PDF vectoriels en PLT pour **Lasertrace / Gravotech**.
Les traits épais deviennent de vrais contours fermés, les extrémités arrondies
sont conservées et le remplissage est constitué de segments de balayage.
Le PLT ne dépend pas des commandes d’épaisseur ou de remplissage HPGL/2.

## Télécharger pour Windows

Télécharger **PDF_to_PLT.exe** depuis la
[dernière release](https://github.com/xunalopak/PDF_to_PLT/releases/latest).
Windows 10/11 64 bits ; aucun Python ni installateur nécessaire.
L’exécutable est compilé uniquement sur les runners Windows de GitHub Actions.

1. Ouvrir `PDF_to_PLT.exe` et sélectionner un PDF vectoriel.
2. Choisir le dossier de sortie ; par défaut, un dossier `<nom du PDF>_PLT` est proposé.
3. Garder le pas de remplissage de **0,025 mm**, ou l’adapter au travail de gravure.
4. Cliquer sur **Convertir en PLT**.
5. Importer `<nom du PDF>_lasertrace_rempli.plt` dans Lasertrace à l’échelle **1:1**,
   avec **40 unités HPGL/mm**, sans ajouter un second remplissage automatique.

Le logiciel demande confirmation avant de remplacer une conversion existante.
Le PDF source reste intact. Le pas de balayage ne configure pas la puissance
ni la vitesse du laser : ces paramètres restent ceux du travail dans Lasertrace.

## Fichiers produits

| Fichier | Utilisation |
| --- | --- |
| `*_lasertrace_rempli.plt` | Contours et remplissage prêt à importer |
| `*_lasertrace_contours.plt` | Contours seuls ; remplissage à définir dans Lasertrace |
| `*_lasertrace_contours_entiers.plt` | Variante à coordonnées entières pour les anciens importeurs |
| `*_lasertrace_contours.dxf` | Polylignes fermées DXF R12, coordonnées en mm |
| `*_surfaces.pdf` | PDF simplifié avec des surfaces pleines |
| `*_surfaces.svg` | Surfaces vectorielles pour inspection |

Pour les contours seuls, le cercle extérieur du logo peut avoir deux contours :
remplir l’espace entre eux, en conservant le centre vide. La grille de coordonnées
entières est de 0,025 mm ; la version décimale conserve davantage de détails.

## PDF pris en charge

La version 1.0 reprend le moteur validé sur le logo fourni lors du développement.
Ce n’est pas encore un lecteur PDF universel. Il accepte les PDF vectoriels à
une seule page, non chiffrés, avec un flux de contenu FlateDecode, des couleurs
RGB opaques, des courbes cubiques et des translations. Les traits doivent être
lisses ; les extrémités droites ou arrondies sont prises en charge.

Les images scannées, polices, transparences, rotations, chemins complexes à
plusieurs sous-chemins et masques blancs qui recouvrent des formes sont refusés.
Un PDF non compatible affiche une erreur au lieu d’être converti silencieusement.
Les couleurs des zones gravées deviennent des tracés sur une seule plume.

Les contours vectoriels sont approximés avec une tolérance de subdivision de
**0,0002 mm** avant développement des épaisseurs. La précision réelle dépend
du logiciel d’import et du spot laser. Vérifier les dimensions après import.

## Utiliser le code source

Python **3.12 ou supérieur**, sans dépendance externe pour la conversion :

```bash
python app.py
python app.py --convert logo.pdf --output-dir sortie --spacing 0.025
python -m unittest discover -s tests -v
```

L’interface utilise Tkinter, fourni avec Python sous Windows. Certains systèmes
Linux nécessitent l’installation séparée de Tkinter pour ouvrir la fenêtre.

## CI et releases

Le workflow **Windows release** :

1. Teste la conversion sous Linux et Windows, ainsi que l’ouverture de l’interface sous Windows.
2. Compile `PDF_to_PLT.exe` avec PyInstaller sur GitHub Actions.
3. Teste l’exécutable compilé sur un PDF vectoriel synthétique et vérifie ses fichiers de sortie.
4. Publie le `.exe`, un ZIP contenant le `.exe`, cette notice et la licence, et les sommes SHA-256.

Les pushes sur `main` et les tags `v*` déclenchent le workflow ; il peut aussi
être lancé manuellement depuis **Actions**. Pour une nouvelle release, augmenter
`VERSION` dans `app.py`, puis pousser sur `main`. Le tag et la release correspondant
à cette version sont créés après les tests. Une release déjà publiée n’est pas
écrasée ; les tags existants ne sont pas déplacés. Un tag poussé manuellement doit
correspondre à `VERSION`.

## Licence

GNU Affero General Public License v3, selon le fichier [LICENSE](LICENSE)
du dépôt. Les archives source associées aux releases contiennent le code.
