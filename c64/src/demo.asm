// SIDBox2 : version démo (étape 3 de SPEC-v2.md) : un morceau intégré, avec son bloc de relais, sans réseau.
// Préparer le morceau : tools/mktune.py ID (code modifié par les relais, comme le servirait RANDOM3). Disposition du fichier :
//   $0801 BASIC · $0810 programme · $3000 image du lecteur (liée en $C000, recopiée au démarrage) · $4000 morceau puis bloc de relais
// Le banc VICE (tools/banc.py) n'utilise que bench_setup et bench, et charge lui-même le morceau.
#import "../build/tune.inc"

        .const VERSION = cmdLineVars.containsKey("VERSION") ? cmdLineVars.get("VERSION") : "2.0-DEV"   // make VERSION=x.y
        .const PLAYER_ADDR = $C000                 // lecteur entier en $C000-$CFFF (SPEC-v2.md §7.1)
        .const PLAYER_SRC = $3000
        .const TUNE_SRC   = $4000
        .const SCR        = $0400
        .const COL        = $D800

:BasicUpstart2(main)

// copie len octets de src vers dst (len constant), par la page zéro $FB-$FE (la page zéro est sauvée par le lecteur)
        .macro copy(src, dst, len) {
        lda     #<src
        sta     $FB
        lda     #>src
        sta     $FC
        lda     #<dst
        sta     $FD
        lda     #>dst
        sta     $FE
        ldx     #>len
        beq     rest
pg:     ldy     #0
l1:     lda     ($FB),y
        sta     ($FD),y
        iny
        bne     l1
        inc     $FC
        inc     $FE
        dex
        bne     pg
rest:   lda     #<len
        beq     done
        ldy     #0
l2:     lda     ($FB),y
        sta     ($FD),y
        iny
        cpy     #<len
        bne     l2
done:
        }

// écrit un texte (déjà converti en codes écran) à la ligne row, colonne col
        .macro put(row, col, text) {
        ldx     #0
l:      lda     str,x
        sta     SCR + row * 40 + col,x
        inx
        cpx     #text.size()
        bne     l
        jmp     over
str:    .encoding "screencode_upper"
        .text text
over:
        }

        * = $0810 "Main"
main:
        jsr     setup
        :put(5, 0, "TITLE: " + TUNE_TITLE)
        :put(6, 0, "ARTIST: " + TUNE_AUTHOR)
        :put(7, 0, "RELEASED: " + TUNE_RELEASED)
again:
        :copy(TUNE_SRC, TUNE_LOAD, TUNE_SIZE)
        .if (RELAY_LEN > 0) {
        :copy(TUNE_SRC + TUNE_SIZE, RELAY_ADDR, RELAY_LEN)
        }
        lda     #<TUNE_INIT
        sta     _init_addr
        lda     #>TUNE_INIT
        sta     _init_addr + 1
        lda     #<TUNE_PLAY
        sta     _play_addr
        lda     #>TUNE_PLAY
        sta     _play_addr + 1
        lda     #<(TUNE_SECS * TUNE_FPS)
        sta     _frames_max
        lda     #>(TUNE_SECS * TUNE_FPS)
        sta     _frames_max + 1
        lda     #TUNE_SONG
        sta     _song_nr
        lda     #TUNE_FPS
        sta     _fps
        lda     #<RELAY_ADDR
        sta     _relay
        lda     #>RELAY_ADDR
        sta     _relay + 1
        lda     #RELAY_COMPLET
        sta     _complet
        lda     #1
        sta     _vis_on
        lda     #0
        sta     _scr_ok
        jsr     _play_run
        cmp     #2              // Q : retour au BASIC
        beq     quit
        jmp     again
quit:   lda     #$37            // ROM BASIC visible avant de lui rendre la main
        sta     $01
        rts

// Lecteur recopié en $C000, écran d'information (lu par le lecteur à son démarrage). Rend $01 = $36.
setup:
        sei
        cld
        lda     #$36
        sta     $01
        lda     #0
        sta     $D020
        sta     $D021
        :copy(PLAYER_SRC, player_start, player_end - player_start)
        ldx     #0
        lda     #32
!clr:   sta     SCR,x
        sta     SCR + $100,x
        sta     SCR + $200,x
        sta     SCR + $300,x
        inx
        bne     !clr-
        ldx     #0
        lda     #1
!col:   sta     COL,x
        sta     COL + $100,x
        sta     COL + $200,x
        sta     COL + $300,x
        inx
        bne     !col-
        :put(10, 0, "TIME: 00:00 / 01:00")
        :put(12, 0, "SEARCH: ALL")
        :put(24, 0, " SPC=NEXT S=SEARCH L=LOOP V=VIS Q=QUIT  ")
        cli
        rts

// Banc VICE : bench_setup prépare puis attend ; le banc charge le morceau, remplit les paramètres et lance bench
// (dans le lecteur, en $C000 : un morceau chargé en $0800 écrase ce programme).
bench_setup:
        jsr     setup
        jmp     bench_wait

        * = PLAYER_SRC "Player"
        .pseudopc PLAYER_ADDR {
#import "player.asm"
        }

        * = bss_start "Bss" virtual
#import "player_bss.asm"
bss_end:
        // §8 : tout le lecteur (code exécuté autour des appels du morceau, données, variables) en $C000-$CFFF
        .errorif bss_end > $D000, "lecteur trop grand : fin des variables en " + toHexString(bss_end)
        .errorif PLAYER_SRC + (player_end - player_start) > TUNE_SRC, "image du lecteur trop grande pour la démo"

        * = TUNE_SRC "Tune"
        .import binary "../build/tune.bin"
        .if (RELAY_LEN > 0) {
        .import binary "../build/relay.bin"
        }
