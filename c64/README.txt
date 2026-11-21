==========================================================================
 SID JUKEBOX v1.8 for the C64 Ultimate / pour le C64 Ultimate
 https://github.com/Stephan83c/jukebox-sid-c64
==========================================================================
 Each section: English first, then francais.
 Chaque section : anglais d'abord, puis francais.

 Contents / Contenu :
   jukebox-sid.prg   the client program / le programme client
   README.txt        this file / ce fichier

WHAT IS IT? / C'EST QUOI ?
--------------------------
EN  A SID music radio. Your C64 Ultimate asks a server (boombass.net, TCP
    port 6474) for a random tune from the HVSC (more than 44,000 tunes),
    receives it over the network and PLAYS IT ITSELF: the C64's own 6510
    runs the tune's code. Every C64 gets its own random pick; there is no
    synchronisation between listeners.
FR  Une radio de musiques SID. Ton C64 Ultimate demande a un serveur
    (boombass.net, port TCP 6474) un morceau au hasard de la HVSC (plus de
    44 000 morceaux), le recoit par le reseau et le JOUE LUI-MEME : c'est
    le 6510 du C64 qui execute le code du morceau. Chaque C64 a son propre
    tirage ; il n'y a pas de synchronisation entre les auditeurs.

WHAT YOU NEED / CE QU'IL TE FAUT
--------------------------------
EN  - a C64 Ultimate (Ultimate 64, or Ultimate-II+ in a C64) connected to
      the Internet, network configured (DHCP is fine);
    - the "Command Interface" switched on (step 1 below): without it the
      program cannot open network connections;
    - this file: jukebox-sid.prg.
FR  - un C64 Ultimate (Ultimate 64, ou Ultimate-II+ dans un C64) relie a
      Internet, reseau configure (DHCP possible) ;
    - la "Command Interface" activee (etape 1 ci-dessous) : sans elle, le
      programme ne peut pas ouvrir de connexion reseau ;
    - ce fichier : jukebox-sid.prg.

SETUP (once) / MISE EN PLACE (une seule fois)
---------------------------------------------
1.  EN  Enable the Command Interface. Open the Ultimate menu with
        C= + RESTORE, then:
           Memory & ROMs  ->  Command Interface  ->  Enabled
        (menu names can differ slightly between firmware versions). Use
        "Save to Flash" to keep the setting after a power cycle.
    FR  Active la Command Interface. Ouvre le menu de l'Ultimate avec
        C= + RESTORE, puis :
           Memory & ROMs  ->  Command Interface  ->  Enabled
        (les noms de menu peuvent varier un peu selon le firmware).
        "Save to Flash" garde le reglage apres une coupure de courant.

2.  EN  Check the network: the Ultimate needs an IP address (DHCP) and
        Internet access (outgoing TCP port 6474 must be allowed).
    FR  Verifie le reseau : l'Ultimate doit avoir une adresse IP (DHCP) et
        un acces Internet (le port TCP 6474 sortant doit etre autorise).

3.  EN  Copy jukebox-sid.prg to a USB stick or the SD card of the Ultimate.
    FR  Copie jukebox-sid.prg sur une cle USB ou la carte SD de l'Ultimate.

4.  EN  Run it: in the Ultimate menu's file browser, select
        jukebox-sid.prg and choose "Run".
        Or from a computer on the same network (REST API reachable):
    FR  Lance-le : dans l'explorateur de fichiers du menu de l'Ultimate,
        selectionne jukebox-sid.prg et choisis "Run".
        Ou depuis un ordinateur du meme reseau (API REST joignable) :
          curl -X POST --data-binary @jukebox-sid.prg \
               http://IP-OF-YOUR-ULTIMATE/v1/runners:run_prg

5.  EN  It connects to boombass.net:6474 by itself and plays a random tune.
        Give it a few seconds: it downloads the tune first.
    FR  Il se connecte tout seul a boombass.net:6474 et joue un morceau au
        hasard. Patiente quelques secondes : il telecharge d'abord le
        morceau.

KEYS / TOUCHES
--------------
    SPACE / ESPACE
        EN next random tune             FR morceau suivant au hasard
    S   EN search by artist or title: the next tunes are picked at random
           among the matches (RETURN confirms, RUN/STOP cancels, empty
           RETURN clears the search; no match = NO MATCH, any tune plays)
        FR recherche par artiste ou titre : les morceaux suivants sont tires
           au hasard parmi les resultats (RETURN valide, RUN/STOP annule,
           RETURN seul efface la recherche ; rien trouve = NO MATCH, un
           morceau au hasard est joue)
    L   EN loop on/off: replays the same tune when it ends (key turns green)
        FR boucle on/off : rejoue le meme morceau a la fin (touche verte)
    V   EN VU meters on/off (green; restarts the same tune from 0:00)
        FR vu-metres on/off (vert ; rejoue le meme morceau depuis 0:00)
    Q   EN quit, back to BASIC      FR quitter, retour au BASIC

THE PLAY SCREEN / L'ECRAN DE LECTURE
------------------------------------
EN  Giant logo, title / artist / year, elapsed time, level meters (one per
    SID voice, rainbow colours), version in the top right corner, a
    scroller at the bottom and the key legend. A tune lasts about 1000
    seconds at most, then the next one is drawn.
FR  Logo geant, titre / artiste / annee, temps ecoule, vu-metres (un par
    voix du SID, couleurs arc-en-ciel), version en haut a droite, un
    scroller en bas et la legende des touches. Un morceau dure environ
    1000 secondes au plus, puis le suivant est tire.

THE SCROLLER AND ITS WEB PAGE / LE SCROLLER ET SA PAGE WEB
----------------------------------------------------------
        https://sidbox.boombass.net/

EN  The scroller text does NOT come from your C64: it comes from the
    server, and anybody can change it on the web page above.
    - Type a message and submit; it is converted to UPPER CASE.
    - Allowed: A-Z 0-9 * . , ! ? - / ' :   (accents removed, anything else
      becomes a space). 150 characters at most. Banned words are refused.
    - One change every 3 minutes for everybody (global pause) and one every
      3 minutes per IP address; the page tells you how long to wait.
    - Your message stays 1 hour, then the server goes back to its default
      text. Changes are logged (time, IP address, text).
    - Your C64 does not talk to the server while a tune plays: it reads the
      scroller text with each new tune, so the new message shows up with
      the NEXT tune (press SPACE to get it at once).
FR  Le texte du scroller ne vient PAS de ton C64 : il vient du serveur, et
    n'importe qui peut le changer sur la page web ci-dessus.
    - Ecris un message et valide ; il est converti en MAJUSCULES.
    - Autorise : A-Z 0-9 * . , ! ? - / ' :   (accents retires, tout le
      reste devient une espace). 150 caracteres au plus. Les mots interdits
      sont refuses.
    - Une modification toutes les 3 minutes pour tout le monde (pause
      globale) et une toutes les 3 minutes par adresse IP ; la page indique
      le temps d'attente.
    - Ton message reste 1 heure, puis le serveur revient a son texte par
      defaut. Les modifications sont journalisees (heure, IP, texte).
    - Ton C64 ne parle pas au serveur pendant qu'un morceau joue : il lit
      le texte du scroller avec chaque nouveau morceau, donc le nouveau
      message apparait avec le morceau SUIVANT (ESPACE pour l'avoir tout
      de suite).

HOW IT WORKS / COMMENT CA MARCHE
--------------------------------
EN  - Server (server.py): a small text protocol over TCP. The C64 sends a
      command such as "RANDOM2 AEFF [pattern]" and gets one header line
      (title, author, year, load/init/play addresses, scroller text) then
      the raw tune code. Only tunes that fit in the C64's free memory are
      offered.
    - Client (this PRG): opens the TCP socket through the Ultimate's
      Command Interface. The tune is loaded at its own address in
      $0800-$AEFF; the program lives in $AF00-$CFFF; the display uses
      $F400-$FFFF. A raster interrupt calls the tune's play routine every
      frame: the 6510 really plays the music.
    - PAL and NTSC: the tune is played at its own rate (50 or 60 Hz, sent by
      the server), so the tempo is the same on a PAL or NTSC machine (the
      machine is measured when each tune starts). The pitch still follows
      the SID clock: about 4 % higher on NTSC.
    - The connection is closed before the tune starts and reopened only for
      the next one: no network traffic while you listen.
    - Web page (web.py): a separate small web server; it only writes the
      scroller text file that server.py reads at every request.
FR  - Serveur (server.py) : un petit protocole texte sur TCP. Le C64 envoie
      une commande comme "RANDOM2 AEFF [motif]" et recoit une ligne
      d'en-tete (titre, auteur, annee, adresses load/init/play, texte du
      scroller) puis le code brut du morceau. Seuls les morceaux qui
      tiennent dans la memoire libre du C64 sont proposes.
    - Client (ce PRG) : ouvre la connexion TCP via la Command Interface de
      l'Ultimate. Le morceau est charge a sa propre adresse dans
      $0800-$AEFF ; le programme vit en $AF00-$CFFF ; l'affichage utilise
      $F400-$FFFF. Une interruption raster appelle la routine de lecture
      du morceau a chaque image : c'est bien le 6510 qui joue.
    - PAL et NTSC : le morceau est joue a sa propre cadence (50 ou 60 Hz,
      envoyee par le serveur), donc le tempo est le meme sur une machine PAL
      ou NTSC (la machine est mesuree au debut de chaque morceau). La
      hauteur suit toujours l'horloge du SID : environ 4 % plus aigue en NTSC.
    - La connexion est fermee avant le debut du morceau et rouverte
      seulement pour le suivant : aucun trafic reseau pendant l'ecoute.
    - Page web (web.py) : un petit serveur web separe ; il ne fait
      qu'ecrire le fichier texte du scroller que server.py relit a chaque
      requete.

IF SOMETHING GOES WRONG / EN CAS DE PROBLEME
--------------------------------------------
EN  - Network error: check step 1 (Command Interface Enabled) and step 2.
    - NEVER reset or re-run a program on the Ultimate while the C64 is
      downloading a tune: the command interface can stay blocked until you
      cut the power. Wait until a tune is playing.
    - Some tunes may fail or sound odd: not every SID tune is playable by
      this player. Press SPACE for another one.
FR  - Erreur reseau : verifie l'etape 1 (Command Interface activee) et 2.
    - Ne JAMAIS reinitialiser ni relancer un programme sur l'Ultimate
      pendant que le C64 telecharge un morceau : la Command Interface peut
      rester bloquee jusqu'a une coupure de courant. Attends qu'un morceau
      joue.
    - Quelques morceaux peuvent echouer ou sonner bizarrement : tous les
      morceaux SID ne sont pas jouables par ce lecteur. ESPACE pour un
      autre.

COPYRIGHT / DROIT D'AUTEUR
--------------------------
EN  The code is MIT-licensed. The tunes come from the High Voltage SID
    Collection (https://hvsc.c64.org/); they remain the property of their
    composers and are not in this zip. Any use beyond private listening is
    subject to copyright. The HVSC team replied on 2026-11-19: "It's all ok
    for us, please go on with your project." This is their approval, not a
    licence.
FR  Le code est sous licence MIT. Les morceaux viennent de la High Voltage
    SID Collection (https://hvsc.c64.org/) ; ils restent la propriete de
    leurs compositeurs et ne sont pas dans ce zip. Tout usage autre que
    l'ecoute privee releve du droit d'auteur. L'equipe HVSC a repondu le
    2026-11-19 : "It's all ok for us, please go on with your project."
    C'est leur accord, pas une licence.

Source code / code source : https://github.com/Stephan83c/jukebox-sid-c64
