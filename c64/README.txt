==========================================================================
 SID JUKEBOX v1.5 for the C64 Ultimate / pour le C64 Ultimate
 https://github.com/Stephan83c/jukebox-sid-c64
==========================================================================
 English first, francais plus bas (section "FRANCAIS").

 Contents of this zip / Contenu du zip:
   jukebox-sid.prg   the client program / le programme client
   README.txt        this file / ce fichier

##########################################################################
 ENGLISH
##########################################################################

WHAT IS IT?
-----------
A SID music radio. Your C64 Ultimate asks a server (boombass.net, TCP port
6474) for a random tune from the HVSC (more than 44,000 tunes), receives
it over the network and PLAYS IT ITSELF: the C64's own 6510 runs the tune's
code. Every C64 gets its own random pick; there is no synchronisation
between listeners.

WHAT YOU NEED
-------------
 - a C64 Ultimate (Ultimate 64, or Ultimate-II+ in a C64) connected to the
   Internet by Ethernet (or WiFi) with a working network setup (DHCP is fine);
 - the "Command Interface" switched on (step 1 below). Without it the
   program cannot open network connections;
 - this file: jukebox-sid.prg.

SETUP (do it once)
------------------
1. Enable the Command Interface
     Press F2 on the Ultimate to open its menu, then:
        Memory & ROMs   ->   Command Interface   ->   Enabled
     (menu names can differ slightly between firmware versions; the
     setting is called "Command Interface"). Save the setting with
     "Save to Flash" if you want to keep it after a power cycle.

2. Check the network
     In the same menu, the Network settings must give the Ultimate an IP
     address (DHCP) and a working Internet access. You can check the
     address in the Ultimate's network status page.

3. Copy jukebox-sid.prg to a USB stick or the SD card of the Ultimate.

4. Run it
     In the Ultimate's file browser (F5 menu), go to the file, select
     jukebox-sid.prg and choose "Run" (or press RETURN on it).
   Alternative, from a computer on the same network:
     curl -X POST --data-binary @jukebox-sid.prg \
          http://YOUR-ULTIMATE-IP/v1/runners:run_prg
   (needs the Ultimate's REST API / web access enabled and reachable)

5. The program connects to boombass.net:6474 by itself and plays a random
   tune. Give it a few seconds: it downloads the tune first.

KEYS
----
   SPACE   next random tune
   S       search by artist or title (RETURN confirms, RUN/STOP cancels,
           empty RETURN clears the filter = everything again)
   L       loop on/off: replays the same tune when it ends (key turns green)
   V       VU meters on/off (key turns green; applies from the next tune)
   Q       quit, back to BASIC

THE PLAY SCREEN
---------------
Giant logo, title / artist / year of the tune, elapsed time, level meters
(one per SID voice, rainbow colours), the version in the top right corner,
a scroller at the bottom and the key legend. A tune stops after at most
about 1000 seconds, then the next one is drawn.

THE SCROLLER AND ITS WEB PAGE
-----------------------------
The scroller text does NOT come from your C64: it comes from the server,
and anybody can change it on this web page:

        http://boombass.net:6475/

 - Type a message and submit. The text is converted to UPPER CASE.
 - Allowed characters: A-Z 0-9 * . , ! ? - / ' :   (accents are removed,
   anything else becomes a space). 150 characters at most.
 - A banned-words list is applied.
 - To keep it fair: one change every 3 minutes for everybody (global
   pause), and one change every 3 minutes per IP address. The page tells
   you how long to wait.
 - A message you send stays for 1 hour, then the server goes back to its
   default text.
 - IMPORTANT: your C64 does not talk to the server while a tune is
   playing. It reads the scroller text together with each new tune, so the
   new message appears with the NEXT tune (press SPACE to get it at once).
 - Changes are logged (time, IP address, text).

HOW IT WORKS (short)
--------------------
 - Server (server.py): a small text protocol over TCP. The C64 sends a
   command such as "RANDOM2 AEFF" or "RANDOM2 AEFF pattern" and gets back
   one header line (title, author, year, load/init/play addresses,
   scroller text) followed by the raw tune code (PSID header stripped).
   Only tunes that fit in the C64's free memory are offered.
 - Client (this PRG): the network part uses the Ultimate's command
   interface (UCI) to open the TCP socket. The tune is loaded at its own
   address in $0800-$AEFF; the program itself lives in $AF00-$CFFF; the
   display uses $F400-$FFFF. A raster interrupt calls the tune's play
   routine every frame, so the 6510 really plays the music.
 - The connection is closed before the tune starts and not reopened until
   the next tune: no network traffic while you listen.
 - Web page (web.py): a separate small web server. It only writes the
   scroller text file that server.py reads at every request.

IF SOMETHING GOES WRONG
-----------------------
 - Network error message: check step 1 (Command Interface Enabled) and
   step 2 (Internet access, firewall). The server must be reachable on
   TCP port 6474 (outgoing).
 - NEVER reset or re-run a program on the Ultimate while the C64 is in the
   middle of a download: the Ultimate's command interface can stay blocked
   until you cut the power. Wait for a tune to be playing first.
 - A few tunes may fail or sound odd: not every SID tune is playable by
   this player. Press SPACE for another one.
 - Source code, issues and updates: see the GitHub page above.

COPYRIGHT
---------
The code is MIT-licensed. The tunes come from the High Voltage SID
Collection (https://hvsc.c64.org/); they remain the property of their
composers and are not included in this zip. Any use beyond private
listening is subject to copyright (see the HVSC copyright notice). The
HVSC team replied to this project on 2026-11-19: "It's all ok for us,
please go on with your project." This is their approval, not a licence.

##########################################################################
 FRANCAIS
##########################################################################

C'EST QUOI ?
------------
Une radio de musiques SID. Ton C64 Ultimate demande a un serveur
(boombass.net, port TCP 6474) un morceau au hasard de la HVSC (plus de
44 000 morceaux), le recoit par le reseau et le JOUE LUI-MEME : c'est le
6510 du C64 qui execute le code du morceau. Chaque C64 a son propre tirage ;
il n'y a pas de synchronisation entre les auditeurs.

CE QU'IL TE FAUT
----------------
 - un C64 Ultimate (Ultimate 64, ou Ultimate-II+ dans un C64) relie a
   Internet par Ethernet (ou WiFi), reseau configure (DHCP possible) ;
 - la "Command Interface" activee (etape 1 ci-dessous). Sans elle, le
   programme ne peut pas ouvrir de connexion reseau ;
 - ce fichier : jukebox-sid.prg.

MISE EN PLACE (une seule fois)
------------------------------
1. Activer la Command Interface
     Appuie sur F2 sur l'Ultimate pour ouvrir son menu, puis :
        Memory & ROMs   ->   Command Interface   ->   Enabled
     (les noms de menu peuvent varier un peu selon la version du
     firmware ; le reglage s'appelle "Command Interface"). Enregistre avec
     "Save to Flash" pour le garder apres une coupure de courant.

2. Verifier le reseau
     Dans le meme menu, les reglages reseau doivent donner une adresse IP
     a l'Ultimate (DHCP) et un acces Internet. Tu peux voir l'adresse dans
     la page d'etat reseau de l'Ultimate.

3. Copie jukebox-sid.prg sur une cle USB ou la carte SD de l'Ultimate.

4. Lance-le
     Dans l'explorateur de fichiers de l'Ultimate (menu F5), va sur le
     fichier, selectionne jukebox-sid.prg et choisis "Run" (ou RETURN).
   Autre methode, depuis un ordinateur du meme reseau :
     curl -X POST --data-binary @jukebox-sid.prg \
          http://IP-DE-TON-ULTIMATE/v1/runners:run_prg
   (il faut que l'API REST / l'acces web de l'Ultimate soit active et
   joignable)

5. Le programme se connecte tout seul a boombass.net:6474 et joue un
   morceau au hasard. Patiente quelques secondes : il telecharge d'abord
   le morceau.

LES TOUCHES
-----------
   ESPACE  morceau suivant au hasard
   S       recherche par artiste ou titre (RETURN valide, RUN/STOP annule,
           RETURN seul efface le filtre = tout le catalogue)
   L       boucle on/off : rejoue le meme morceau a la fin (touche verte)
   V       vu-metres on/off (touche verte ; effet au morceau suivant)
   Q       quitter, retour au BASIC

L'ECRAN DE LECTURE
------------------
Logo geant, titre / artiste / annee du morceau, temps ecoule, vu-metres
(un par voix du SID, couleurs arc-en-ciel), la version en haut a droite, un
scroller en bas et la legende des touches. Un morceau s'arrete au bout
d'environ 1000 secondes au plus, puis le suivant est tire.

LE SCROLLER ET SA PAGE WEB
--------------------------
Le texte du scroller ne vient PAS de ton C64 : il vient du serveur, et
n'importe qui peut le changer sur cette page web :

        http://boombass.net:6475/

 - Ecris un message et valide. Le texte est converti en MAJUSCULES.
 - Caracteres autorises : A-Z 0-9 * . , ! ? - / ' :   (les accents sont
   retires, tout le reste devient une espace). 150 caracteres au plus.
 - Une liste de mots interdits est appliquee.
 - Pour rester equitable : une modification toutes les 3 minutes pour tout
   le monde (pause globale), et une toutes les 3 minutes par adresse IP. La
   page indique le temps d'attente.
 - Un message envoye reste 1 heure, puis le serveur revient a son texte par
   defaut.
 - IMPORTANT : ton C64 ne parle pas au serveur pendant qu'un morceau
   joue. Il lit le texte du scroller avec chaque nouveau morceau : le
   nouveau message apparait donc avec le morceau SUIVANT (appuie sur ESPACE
   pour l'avoir tout de suite).
 - Les modifications sont journalisees (heure, adresse IP, texte).

COMMENT CA MARCHE (en bref)
---------------------------
 - Serveur (server.py) : un petit protocole texte sur TCP. Le C64 envoie
   une commande comme "RANDOM2 AEFF" ou "RANDOM2 AEFF motif" et recoit une
   ligne d'en-tete (titre, auteur, annee, adresses load/init/play, texte du
   scroller) suivie du code brut du morceau (en-tete PSID retire). Seuls
   les morceaux qui tiennent dans la memoire libre du C64 sont proposes.
 - Client (ce PRG) : la partie reseau utilise la Command Interface (UCI)
   de l'Ultimate pour ouvrir la connexion TCP. Le morceau est charge a sa
   propre adresse dans $0800-$AEFF ; le programme vit en $AF00-$CFFF ;
   l'affichage utilise $F400-$FFFF. Une interruption raster appelle la
   routine de lecture du morceau a chaque image : c'est bien le 6510 qui
   joue la musique.
 - La connexion est fermee avant le debut du morceau et rouverte
   seulement au suivant : aucun trafic reseau pendant l'ecoute.
 - Page web (web.py) : un petit serveur web separe. Il ne fait qu'ecrire
   le fichier texte du scroller que server.py relit a chaque requete.

EN CAS DE PROBLEME
------------------
 - Message d'erreur reseau : verifie l'etape 1 (Command Interface activee)
   et l'etape 2 (acces Internet, pare-feu). Le serveur doit etre joignable
   sur le port TCP 6474 (sortant).
 - Ne JAMAIS reinitialiser ni relancer un programme sur l'Ultimate pendant
   que le C64 telecharge un morceau : la Command Interface peut rester
   bloquee jusqu'a une coupure de courant. Attends qu'un morceau joue.
 - Quelques morceaux peuvent echouer ou sonner bizarrement : tous les
   morceaux SID ne sont pas jouables par ce lecteur. Appuie sur ESPACE.
 - Code source, problemes et mises a jour : voir la page GitHub ci-dessus.

DROIT D'AUTEUR
--------------
Le code est sous licence MIT. Les morceaux viennent de la High Voltage SID
Collection (https://hvsc.c64.org/) ; ils restent la propriete de leurs
compositeurs et ne sont pas inclus dans ce zip. Tout usage autre que
l'ecoute privee releve du droit d'auteur (voir l'avis de la HVSC). L'equipe
HVSC a repondu a ce projet le 2026-11-19 : "It's all ok for us, please go
on with your project." C'est leur accord, pas une licence.
