# DocEdit

**DocEdit** permet de modifier les textes, chiffres et dates de vos documents, depuis votre ordinateur **ou votre téléphone** :

1. **Importer un fichier** (PDF, Word `.docx`, Excel `.xlsx`, photo JPG / PNG / HEIC) et modifier ses écritures ;
2. **Scanner un document** avec la caméra (bords détectés automatiquement, page recadrée, redressée et éclaircie, plusieurs pages à la suite), puis le modifier de la même façon ;
3. **Télécharger** le document modifié, dans son format d'origine ou en PDF.

Votre fichier d'origine n'est **jamais modifié** : DocEdit travaille sur une copie et vous fait télécharger un nouveau fichier nommé « … (modifié) ».
Tout se passe **sur votre ordinateur** : aucun document n'est envoyé sur Internet.

---

## Sommaire

- [Installation sur Windows](#installation-sur-windows)
- [Installation sur Mac](#installation-sur-mac)
- [Installer Tesseract (lecture des scans et des photos)](#installer-tesseract)
- [Lancer DocEdit](#lancer-docedit)
- [Utiliser DocEdit sur votre téléphone](#utiliser-docedit-sur-votre-téléphone)
- [Mode d'emploi](#mode-demploi)
- [Questions fréquentes](#questions-fréquentes)
- [Pour les curieux : comment ça marche](#pour-les-curieux--comment-ça-marche)

---

## Installation sur Windows

À faire **une seule fois**.

1. **Installer Python**
   - Allez sur <https://www.python.org/downloads/> et cliquez sur le gros bouton jaune **« Download Python »**.
   - Ouvrez le fichier téléchargé.
   - ⚠️ **Cochez la case « Add python.exe to PATH »** en bas de la première fenêtre, puis cliquez sur **« Install Now »**.
2. **Installer Tesseract** (pour lire le texte des scans et des photos) : voir [Installer Tesseract](#installer-tesseract) ci-dessous.
3. **Récupérer DocEdit** : téléchargez le dossier DocEdit (bouton vert **Code → Download ZIP** sur GitHub), puis faites un clic droit sur le fichier ZIP → **« Extraire tout… »**.
4. *(Facultatif)* Installer **LibreOffice** (<https://fr.libreoffice.org/download/telecharger-libreoffice/>) : les exports PDF des fichiers Word et Excel seront alors identiques à l'original. Sans LibreOffice, l'export PDF fonctionne aussi, avec une mise en page simplifiée.

## Installation sur Mac

À faire **une seule fois**.

1. **Installer Python** : allez sur <https://www.python.org/downloads/>, cliquez sur **« Download Python »**, ouvrez le fichier `.pkg` et suivez les étapes.
   À la fin, une fenêtre du Finder s'ouvre : double-cliquez sur **« Install Certificates.command »**.
2. **Installer Tesseract** : voir [Installer Tesseract](#installer-tesseract) ci-dessous.
3. **Récupérer DocEdit** : téléchargez le dossier DocEdit (bouton vert **Code → Download ZIP** sur GitHub) et double-cliquez sur le ZIP pour l'extraire.
4. *(Facultatif)* Installer **LibreOffice** (<https://fr.libreoffice.org/download/telecharger-libreoffice/>) pour des exports PDF de Word/Excel identiques à l'original.

## Installer Tesseract

Tesseract est un logiciel **gratuit** qui lit le texte des images. Il est nécessaire pour les **photos, scans et PDF scannés**.
Sans lui, DocEdit fonctionne quand même pour les PDF « numériques », Word et Excel, et vous prévient simplement que le texte des images ne peut pas être lu.

### Sur Windows

1. Allez sur <https://github.com/UB-Mannheim/tesseract/wiki> et téléchargez l'installateur **« tesseract-ocr-w64-setup-….exe »** (la version la plus récente).
2. Lancez-le. À l'étape **« Choose Components »**, dépliez **« Additional language data (download) »** et cochez **« French »**.
3. Gardez le dossier d'installation proposé (`C:\Program Files\Tesseract-OCR`) : DocEdit le trouvera tout seul.

### Sur Mac

1. Ouvrez l'application **Terminal** (Applications → Utilitaires → Terminal).
2. Si vous n'avez pas encore **Homebrew**, copiez-collez cette ligne, appuyez sur Entrée et suivez les instructions :
   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
3. Puis installez Tesseract avec le français :
   ```
   brew install tesseract tesseract-lang
   ```

### Sur Linux (Debian / Ubuntu)

```
sudo apt install tesseract-ocr tesseract-ocr-fra
```

## Lancer DocEdit

- **Windows** : double-cliquez sur **`start.bat`**.
  Si Windows affiche « Windows a protégé votre ordinateur », cliquez sur **Informations complémentaires → Exécuter quand même**.
  Si le pare-feu demande l'autorisation, cochez **Réseaux privés** et cliquez sur **Autoriser** (nécessaire pour le téléphone).
- **Mac** : double-cliquez sur **`start.command`**.
  La première fois, si le Mac refuse de l'ouvrir : clic droit (ou Ctrl+clic) sur `start.command` → **Ouvrir** → **Ouvrir**.
  Vous pouvez aussi, dans le Terminal : taper `cd ` (avec un espace), glisser le dossier DocEdit dans la fenêtre, appuyer sur Entrée, puis taper `bash start.sh`.
- **Linux** : `./start.sh`

**La première fois**, l'installation des composants prend 1 à 3 minutes (connexion Internet nécessaire). Les fois suivantes, DocEdit démarre en quelques secondes.

Une fenêtre noire affiche alors :

```
  DocEdit est lancé !
  Sur cet ordinateur :   http://localhost:8000
  Sur votre téléphone :  http://192.168.1.23:8000
  Adresse sécurisée :    https://192.168.1.23:8443
  Scannez ce QR code avec l'appareil photo de votre téléphone :
  (QR code)
```

Votre navigateur s'ouvre automatiquement sur DocEdit. **Laissez la fenêtre noire ouverte** tant que vous utilisez DocEdit ; fermez-la (ou appuyez sur Ctrl+C) pour l'arrêter.

## Utiliser DocEdit sur votre téléphone

1. Le téléphone doit être connecté **au même Wi-Fi** que l'ordinateur où DocEdit est lancé.
2. **Scannez le QR code** affiché dans la fenêtre noire (ou cliquez sur **« Ouvrir sur mon téléphone »** dans DocEdit) avec l'appareil photo du téléphone, puis touchez le lien.
3. Pour l'avoir comme une vraie application : touchez **« Ajouter à l'écran d'accueil »** dans DocEdit et suivez les indications
   (iPhone : dans Safari, bouton **Partager** → **« Sur l'écran d'accueil »** ; Android : menu **⋮** → **« Ajouter à l'écran d'accueil »**).

> 💡 **Caméra en direct** : avec l'adresse `http://`, le bouton « Scanner » ouvre l'appareil photo du téléphone ; la feuille est détectée après la photo, ce qui marche très bien.
> Pour voir la feuille détectée **en direct** dans DocEdit, ouvrez plutôt l'**adresse sécurisée** `https://…:8443`. Le téléphone affiche un avertissement
> (« connexion non privée ») car le certificat est créé par votre ordinateur : touchez **Paramètres avancés → Continuer** (Android) ou **Afficher les détails → visiter ce site** (iPhone). C'est sans risque : c'est votre propre ordinateur.

## Mode d'emploi

### 1. Importer un fichier
Touchez **« Importer un fichier »** et choisissez votre document, ou (sur ordinateur) **glissez-déposez** le fichier sur la page.
Formats acceptés : **PDF**, **Word (.docx)**, **Excel (.xlsx)**, **images (JPG, PNG, HEIC)**.

### 2. Scanner un document
1. Touchez **« Scanner un document »** et autorisez l'accès à la caméra.
2. Cadrez la feuille : quand elle est détectée, un contour vert apparaît. Touchez le **bouton rond** (ou prenez la photo).
3. Vérifiez les **4 coins** (déplacez-les du doigt si besoin) et choisissez le rendu : **Couleur**, **Gris**, **Noir & blanc** ou **Original**.
4. Touchez **« Valider la page »**. Scannez les pages suivantes de la même façon.
5. Touchez **« Terminer »** : DocEdit lit le texte de toutes les pages.

### 3. Modifier
- Chaque page s'affiche telle quelle ; les zones de texte modifiables sont encadrées en bleu clair.
- **Touchez un texte** : une fenêtre s'ouvre avec le texte lu. Modifiez-le puis touchez **« Valider »** (ou Entrée).
  « ↺ Texte d'origine » remet le texte de départ.
- Pour les scans et photos, une case **« Gras »** permet de corriger la graisse si elle a mal été devinée.
- Les textes modifiés sont encadrés en **vert**.
- **🔍 Remplacer** : rechercher un mot, un nombre ou une date et le remplacer **partout dans le document** (options : majuscules/minuscules, mot entier).
- **↶ Annuler / ↷ Rétablir** (ou Ctrl+Z / Ctrl+Y sur ordinateur).

Comment DocEdit modifie le document :
- **PDF « numérique »** : l'ancien texte est réellement effacé du PDF, puis le nouveau est écrit au même endroit, en gardant la police d'origine si possible (sinon la plus proche), la taille et la couleur.
- **Scan, photo, PDF scanné** : la zone est recouverte avec la couleur du fond détectée autour, puis le nouveau texte est écrit avec une taille, une couleur et une graisse estimées.
- **Word** : seuls les caractères changés sont remplacés, la mise en forme (gras, couleur, taille…) est conservée.
- **Excel** : les nombres restent des nombres, les dates restent des dates, les formules (commençant par `=`) restent des formules.
- Si le nouveau texte est plus long, DocEdit utilise la place libre à côté ; s'il n'y en a pas assez, la taille est légèrement réduite pour qu'il tienne. Les montants alignés à droite le restent.

### 4. Télécharger
Touchez **« ⬇ Télécharger »** et choisissez :
- le **format d'origine** (PDF, Word, Excel, JPG/PNG/HEIC),
- ou **PDF**,
- ou, pour les scans et photos, **« PDF avec texte sélectionnable »** (on peut ensuite copier et rechercher le texte dans le PDF).

Sur téléphone, le menu de partage s'ouvre : choisissez **« Enregistrer dans Fichiers »**, Photos, ou l'application de votre choix.

## Questions fréquentes

**Le téléphone n'arrive pas à ouvrir l'adresse.**
Vérifiez que le téléphone est sur le **même Wi-Fi** (pas en 4G/5G) et que la fenêtre noire de DocEdit est toujours ouverte.
Sur Windows, autorisez DocEdit dans le pare-feu (Panneau de configuration → Pare-feu Windows Defender → Autoriser une application → cochez « Python » pour les réseaux privés).
Certains Wi-Fi publics ou « invités » empêchent les appareils de communiquer entre eux : utilisez votre Wi-Fi personnel.

**« Tesseract n'est pas installé »**
Suivez [Installer Tesseract](#installer-tesseract), puis fermez et relancez DocEdit.

**Le texte d'un scan est mal lu.**
Reprenez la photo bien à plat, de face, avec une bonne lumière et sans reflet ; vous pouvez aussi corriger le texte lu directement dans la fenêtre de modification.

**Mon fichier .doc / .xls n'est pas accepté.**
Ouvrez-le dans Word ou Excel et faites **Fichier → Enregistrer sous** au format `.docx` / `.xlsx`.

**Le PDF est protégé par un mot de passe.**
Ouvrez-le avec votre lecteur PDF, enregistrez-en une copie sans mot de passe, puis importez cette copie.

**Le port 8000 est déjà utilisé.**
DocEdit choisit automatiquement le port libre suivant (8001, 8002…) : utilisez l'adresse affichée dans la fenêtre noire.

**Où sont mes documents ?**
Les copies de travail sont dans le dossier `data/` de DocEdit et sont supprimées automatiquement après 3 jours. Vos fichiers d'origine ne sont jamais touchés.

## Pour les curieux : comment ça marche

- Serveur : **Python + FastAPI** (`docedit/server.py`), lancé par `run.py` en HTTP (port 8000) et HTTPS auto-signé (port 8443) sur toutes les interfaces réseau.
- Interface : **HTML / CSS / JavaScript** sans dépendance (`static/`), installable comme application (**PWA** : `manifest.webmanifest` + `sw.js`).
- PDF : **PyMuPDF** (lecture du texte, effacement par *redaction*, réécriture) ; scans : **Tesseract** (`fra+eng`, orientation automatique), **OpenCV** (bords, perspective, éclairage) et **Pillow** (réécriture) ; Word : **python-docx** ; Excel : **openpyxl**.
- Polices de remplacement : **Liberation Sans / Serif / Mono** (licence SIL OFL, dans `docedit/fonts/`), aux dimensions identiques à Arial, Times New Roman et Courier New.
- Les modifications sont une liste d'opérations appliquées à la copie de l'original : c'est ce qui rend **Annuler / Rétablir** fiables et garantit que l'original n'est jamais écrasé.

Lancer les tests automatiques (après un premier démarrage) :

```
# Mac / Linux
.venv/bin/python -m pip install pytest && .venv/bin/python -m pytest tests
# Windows
.venv\Scripts\python -m pip install pytest && .venv\Scripts\python -m pytest tests
```

Options avancées (variables d'environnement) : `DOCEDIT_PORT` (port HTTP, défaut 8000), `DOCEDIT_HTTPS_PORT` (défaut 8443), `DOCEDIT_NO_HTTPS=1`, `DOCEDIT_NO_BROWSER=1`, `DOCEDIT_DATA` (dossier de travail).
