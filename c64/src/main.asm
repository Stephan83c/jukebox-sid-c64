// SIDBox2 : client v2.0 du jukebox SID (SPEC-v2.md). Fichier chargé en $0801 ; le chargeur recopie le lecteur en $C000
// et le client juste après ses variables (HISTART), puis lance le client (la zone $0800..HISTART-1 est ensuite libre pour les morceaux).
// Serveur : make SERVER=nom-ou-adresse [PORT=6474] (jamais écrit dans les fichiers du dépôt).
#import "memmap.asm"
#import "zp.asm"
#import "big_size.inc"

        .const VERSION = cmdLineVars.containsKey("VERSION") ? cmdLineVars.get("VERSION") : "2.0-DEV"   // make VERSION=x.y
        .const PLAYER_ADDR = $C000
        .const SERVER_HOST = cmdLineVars.get("SERVER")
        .const SERVER_PORT = cmdLineVars.containsKey("PORT") ? cmdLineVars.get("PORT").asNumber() : 6474
        .errorif SERVER_HOST == null, "serveur manquant : make SERVER=nom-ou-adresse"

:BasicUpstart2(start)

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

        * = $0810 "Loader"
start:  sei
        cld
        lda     #$36            // ROM BASIC coupée : $A000-$BFFF devient de la RAM
        sta     $01
        :copy(player_img, player_start, player_end - player_start)
        lda     #0              // variables du client à zéro AVANT la copie du code, qui les suit (la RAM garde ce
        tax                     // qu'y a laissé le programme précédent)
!:      sta     HISTART,x
        sta     HISTART + $100,x
        sta     HISTART + $200,x
        inx
        bne     !-
        .errorif client_bss_end > HISTART + $300, "variables du client : agrandir la mise à zéro"
        :copy(client_img, client_code, client_end - client_code)
        jsr     intro
        cli
        jmp     client_start

// ---------------------------------------------------------------- écran d'accueil de la v2.0
// Dans le chargeur : exécuté une seule fois, avant la première connexion, puis écrasé par les morceaux (aucune place
// résidente). 20 s ou une touche. Même thème que l'appli : fond noir, titre géant dans le style du logo (police du C64
// agrandie 2 x 3, tools/mkbig.py) avec son arc-en-ciel qui défile, textes bleu clair, touches en gris.
        .const ISCR = $0400
        .const INTRO_FRAMES = 1000            // 20 s en PAL (17 s en NTSC) : le temps de lire ; une touche abrège
        .const TITLE_ROW = 3
        .const TITLE_COL = (40 - BIG_W) / 2
        .const ICHR = $3800             // jeu de caractères de l'écran d'accueil (banque VIC 0), libre après le chargement

        .macro center(row, color, text) {
        ldx     #text.size() - 1
l:      lda     str,x
        sta     ISCR + row * 40 + (40 - text.size()) / 2,x
        lda     #color
        sta     $D800 + row * 40 + (40 - text.size()) / 2,x
        dex
        bpl     l
        jmp     over
str:    .encoding "screencode_upper"
        .text   text
over:
        }

intro: {
        lda     #0
        sta     $D020
        sta     $D021
        lda     #$33            // jeu de caractères de la ROM recopié en ICHR ($3800), puis le titre géant (codes 128+)
        sta     $01
        ldx     #0
l_ch:   .for (var k = 0; k < 8; k++) {
        lda     $D000 + k * $100,x
        sta     ICHR + k * $100,x
        }
        inx
        bne     l_ch
        lda     #$36
        sta     $01
        ldx     #0              // formes du titre : deux pages (BIG_N x 8 octets, 512 au plus)
l_bc:   lda     big_chars,x
        sta     ICHR + 128 * 8,x
        lda     big_chars + $100,x
        sta     ICHR + 128 * 8 + $100,x
        inx
        bne     l_bc
        .errorif BIG_N > 64, "titre : plus de 64 caractères, agrandir la copie"
        lda     #0              // $3FFF : octet que le VIC montre là où il n'affiche rien (bordure) : à zéro
        sta     $3FFF
        lda     #$1E            // écran $0400, caractères $3800
        sta     $D018
        lda     #$FF            // clavier : directions des ports du CIA 1
        sta     $DC02
        lda     #0
        sta     $DC03
        ldx     #0
l_cl:   lda     #32
        sta     ISCR,x
        sta     ISCR + $100,x
        sta     ISCR + $200,x
        sta     ISCR + $2E8,x
        lda     #1
        sta     $D800,x
        sta     $D800 + $100,x
        sta     $D800 + $200,x
        sta     $D800 + $2E8,x
        inx
        bne     l_cl
        ldx     #0              // titre géant « SID JUKEBOX 2.0 », style du logo (lignes 3 à 5)
l_big:  .for (var r = 0; r < BIG_H; r++) {
        lda     big_map + r * BIG_W,x
        sta     ISCR + (TITLE_ROW + r) * 40 + TITLE_COL,x
        }
        inx
        cpx     #BIG_W
        bne     l_big
        :center(9, 14, "EXACT SOUND, EVERY TUNE")
        :center(11, 14, "NEW PLAYER, 100% ASSEMBLY")
        :center(13, 14, "PAL AND NTSC AT THE RIGHT SPEED")
        :center(15, 14, "OVER 44000 TUNES FROM THE HVSC")
        :center(18, 14, "EDIT THE SCROLLER TEXT ON")       // page web publique du scroller (demandée par l'utilisateur)
        :center(19, 1, "HTTPS://SIDBOX.BOOMBASS.NET")
        :center(22, 12, "PRESS ANY KEY")
        lda     #0
        sta     ifr
        sta     ifr + 1
        sta     irel

l_frame: bit    $D011           // une image : passer la ligne 256 puis revenir en haut
        bpl     l_frame
l_f2:   bit     $D011
        bmi     l_f2
        lda     ifr             // couleurs du titre : arc-en-ciel de l'appli qui défile (logocolor : tous les 4 images)
        lsr
        lsr
        sta     itmp
        ldx     #BIG_W - 1
l_co:   txa
        lsr                     // une couleur par lettre (2 colonnes)
        clc
        adc     itmp
        and     #7
        tay
        lda     rainbow,y
        .for (var r = 0; r < BIG_H; r++) {
        sta     $D800 + (TITLE_ROW + r) * 40 + TITLE_COL,x
        }
        dex
        bpl     l_co
        lda     #0              // clavier : une touche, après avoir vu toutes les touches relâchées
        sta     $DC00
        lda     $DC01
        ldx     #$FF
        stx     $DC00
        cmp     #$FF
        bne     l_down
        sta     irel            // (Z = 1, laissé par le cmp : sta ne touche pas aux drapeaux)
        beq     l_cnt
l_down: lda     irel
        bne     l_out
l_cnt:  inc     ifr
        bne     l_c1
        inc     ifr + 1
l_c1:   lda     ifr + 1
        cmp     #>INTRO_FRAMES
        bcc     l_more
        lda     ifr
        cmp     #<INTRO_FRAMES
        bcs     l_out
l_more: jmp     l_frame
l_out:  lda     #$15            // jeu de caractères de la ROM
        sta     $D018
        rts
}
ifr:    .word 0
irel:   .byte 0
itmp:   .byte 0
#import "big.inc"

player_img:
        .pseudopc PLAYER_ADDR {
#import "player.asm"
        }
client_img:
        // variables du client d'abord (en HISTART) : Kick Assembler n'accepte pas une variable définie plus loin en
        // argument de macro ; le code suit les variables
        * = HISTART "ClientBss" virtual
#import "client_bss.asm"
client_bss_end:
        * = client_img "ClientImg"
        .pseudopc client_bss_end {
client_code:
#import "net.asm"
#import "client.asm"
        }

        * = bss_start "PlayerBss" virtual
#import "player_bss.asm"
player_bss_end:

        // §8 : la construction échoue si une zone déborde
        .errorif player_bss_end > $D000, "lecteur trop grand : " + toHexString(player_bss_end)
        .errorif client_end > PLAYER_ADDR, "client trop grand : " + toHexString(client_end)
        .errorif ICHR < client_img + (client_end - client_code), "jeu de caractères de l'écran d'accueil recouvert par le fichier"
