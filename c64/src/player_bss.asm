// variables du lecteur (BSS), incluses par le programme principal
_init_addr: .fill 2, 0
_play_addr: .fill 2, 0
_frames_max: .fill 2, 0
_song_nr: .fill 1, 0
_fps: .fill 1, 0
_vis_on: .fill 1, 0
next: .fill 2, 0
digits: .fill 4, 0         // minutes dizaines/unités, secondes dizaines/unités
frames: .fill 2, 0         // images vidéo de la machine (effets visuels)
tframes: .fill 2, 0         // appels du morceau (temps écoulé, durée)
acc: .fill 1, 0         // accumulateur de cadence : morceau (fps) contre machine (mfps)
mfps: .fill 1, 0         // cadence vidéo de la machine : 50 (PAL) ou 60 (NTSC)
seen: .fill 1, 0
result: .fill 1, 0
shadow: .fill 25, 0        // copie des registres $D400-$D418
prevg: .fill 3, 0         // gate précédent de chaque voix
state: .fill 3, 0         // 0 relâchement, 1 attaque, 2 déclin/maintien
level: .fill 3, 0         // niveau d'enveloppe simulé 0-255
vh: .fill 3, 0         // longueur de barre 0-255 (pixels)
vi: .fill 1, 0
vo: .fill 1, 0
tmp: .fill 1, 0
tmp2: .fill 1, 0
xs: .fill 1, 0         // décalage fin du scroller (0-7)
stage: .fill 1, 0         // 0 = avant le scroller, 1 = après, 2 = le morceau
tpos: .fill 2, 0         // prochain caractère du texte
sbuf: .fill 40, 0        // texte visible du scroller, ligne du haut (la RAM sous le KERNAL ne peut pas être relue)
sbufb: .fill 40, 0        // ligne du bas
_scr_ok: .fill 1, 0         // 1 = texte du serveur à scr_ptr, 0 = texte intégré
_scr_ptr: .fill 2, 0         // texte du scroller reçu : indices de glyphes, $FF = fin (dans l'en-tête de main.c)
nbot: .fill 1, 0         // code de la case du bas du caractère suivant

// v2.0
_relay: .fill 2, 0         // adresse du bloc de relais (sa copie de 32 octets en tête) ; 0 = pas de relais
_complet: .fill 1, 0         // 1 = toutes les écritures SID relayées : correction de hauteur permise (§5.5)
port_init: .fill 1, 0         // $01 laissé par init (journal, lu par le banc)
port_play: .fill 1, 0         // dernier $01 != $36 laissé par play (0 = jamais)
spsave: .fill 1, 0         // pointeur de pile à l'entrée de _play_run
vsave: .fill 6, 0         // registres du VIC (liste vregs)
dd00save: .fill 1, 0
dd02save: .fill 1, 0
hasrel: .fill 1, 0         // 1 = bloc de relais présent
dofix: .fill 1, 0         // 1 = corriger la hauteur après chaque appel
incall: .fill 1, 0         // 1 = un appel du morceau est en cours (IRQ à ignorer)
fp1: .fill 1, 0         // variables de fixpitch (IRQ)
fp2: .fill 1, 0
